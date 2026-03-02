"""
Garmin 数据同步任务
"""
import asyncio
import logging
from datetime import datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.device_credential import DeviceCredential
from app.models.daily_health import WorkoutRecord, WorkoutAnalysisResult
from app.services.data_collection.garmin_connect import GarminConnectService

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def sync_user_garmin_data(self, user_id: int):
    """
    同步单个用户的 Garmin 数据
    """
    logger.info(f"开始同步用户 {user_id} 的 Garmin 数据")
    
    try:
        with SessionLocal() as db:
            credential = db.query(DeviceCredential).filter(
                DeviceCredential.user_id == user_id,
                DeviceCredential.device_type == "garmin"
            ).first()
            
            if not credential:
                logger.warning(f"用户 {user_id} 没有 Garmin 凭据")
                return {"status": "skipped", "reason": "no_credentials"}
            
            # 获取凭证
            creds = credential.get_credentials()
            
            # 创建服务并同步
            service = GarminConnectService(
                email=creds.get("email"),
                password=creds.get("password"),
                user_id=user_id
            )
            
            result = service.sync_all_data(db, days=1)

            logger.info(f"用户 {user_id} Garmin 同步完成: {result}")

            # 检测最近 12 小时内新同步且未分析的运动，触发自动分析
            try:
                twelve_hours_ago = datetime.utcnow() - timedelta(hours=12)
                analyzed_workout_ids = {
                    r.workout_id for r in db.query(WorkoutAnalysisResult.workout_id).filter(
                        WorkoutAnalysisResult.user_id == user_id
                    ).all()
                }
                new_workouts = db.query(WorkoutRecord).filter(
                    WorkoutRecord.user_id == user_id,
                    WorkoutRecord.created_at >= twelve_hours_ago,
                    ~WorkoutRecord.id.in_(analyzed_workout_ids) if analyzed_workout_ids else True
                ).all()
                for w in new_workouts:
                    logger.info(f"触发自动分析: user={user_id} workout={w.id} ({w.activity_type})")
                    auto_analyze_workout.delay(user_id, w.id)
            except Exception as e:
                logger.warning(f"检测新运动触发分析失败: {e}")

            return {"status": "success", "result": result}
            
    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task
def sync_all_users_garmin():
    """
    同步所有用户的 Garmin 数据（每小时执行）
    """
    logger.info("开始批量同步所有用户 Garmin 数据")
    
    with SessionLocal() as db:
        credentials = db.query(DeviceCredential).filter(
            DeviceCredential.device_type == "garmin",
            DeviceCredential.is_active == True
        ).all()
        
        user_ids = [c.user_id for c in credentials]
    
    logger.info(f"发现 {len(user_ids)} 个活跃的 Garmin 账户")
    
    # 为每个用户创建异步任务
    for user_id in user_ids:
        sync_user_garmin_data.delay(user_id)
    
    return {"status": "dispatched", "count": len(user_ids)}


@celery_app.task(bind=True, max_retries=2, time_limit=300)
def auto_analyze_workout(self, user_id: int, workout_id: int):
    """
    自动分析单次运动（Garmin 同步后触发）
    """
    logger.info(f"[自动分析] 开始: user={user_id} workout={workout_id}")

    try:
        with SessionLocal() as db:
            # 检查是否已有分析结果
            existing = db.query(WorkoutAnalysisResult).filter(
                WorkoutAnalysisResult.workout_id == workout_id
            ).first()
            if existing:
                logger.info(f"[自动分析] 跳过已分析的运动 {workout_id}")
                return {"status": "skipped", "reason": "already_analyzed"}

            workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.id == workout_id,
                WorkoutRecord.user_id == user_id
            ).first()
            if not workout:
                logger.warning(f"[自动分析] 运动记录不存在: {workout_id}")
                return {"status": "skipped", "reason": "not_found"}

            # 使用 PostRunAnalyzeService 的内部方法
            from app.services.post_run_analyze import PostRunAnalyzeService
            service = PostRunAnalyzeService(db)
            workout_data = service._build_workout_data(workout)
            prompt = service._build_prompt(user_id, workout, workout_data)

            # 异步调用 OpenClaw 多模型分析
            analysis = asyncio.get_event_loop().run_until_complete(
                service.openclaw.analyze(prompt)
            )

            # 保存分析结果
            service._save_analysis_result(user_id, workout_id, prompt, analysis)

            # 发送推送通知
            aggregation = (analysis.get("aggregation") or "")[:200]
            activity = workout.activity_type or "运动"
            title = f"运动分析完成: {activity}"
            content = aggregation or "你的运动数据已分析完成，点击查看详情"
            try:
                from app.services.notification.push_service import PushService
                push_service = PushService(db)
                asyncio.get_event_loop().run_until_complete(
                    push_service.send_notification(
                        user_id=user_id,
                        notification_type="workout_analysis",
                        title=title,
                        content=content,
                    )
                )
            except Exception as e:
                logger.warning(f"[自动分析] 推送通知失败: {e}")

            logger.info(f"[自动分析] 完成: user={user_id} workout={workout_id} status={analysis.get('status')}")
            return {"status": "success", "workout_id": workout_id}

    except Exception as e:
        logger.error(f"[自动分析] 失败: user={user_id} workout={workout_id} error={e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
