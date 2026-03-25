"""
Garmin 数据同步任务
"""
import asyncio
import logging
from datetime import date, datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord, WorkoutAnalysisResult

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def sync_user_garmin_data(self, user_id: int, days: int = 1):
    """
    同步单个用户的 Garmin 数据（健康数据 + 运动活动）
    """
    logger.info(f"开始同步用户 {user_id} 的 Garmin 数据 (最近 {days} 天)")

    try:
        with SessionLocal() as db:
            # 使用 GarminCredential 获取凭据（与 scheduler/auth 保持一致）
            from app.models.user import GarminCredential
            from app.services.auth import garmin_credential_service

            credential = db.query(GarminCredential).filter(
                GarminCredential.user_id == user_id,
                GarminCredential.sync_enabled == True,
                GarminCredential.credentials_valid == True
            ).first()

            if not credential:
                logger.warning(f"用户 {user_id} 没有有效的 Garmin 凭据")
                return {"status": "skipped", "reason": "no_credentials"}

            # 解密密码
            try:
                password = garmin_credential_service.decrypt_password(credential.encrypted_password)
            except Exception as e:
                logger.error(f"用户 {user_id} Garmin 凭据解密失败: {e}")
                return {"status": "error", "reason": "decrypt_failed"}

            email = credential.garmin_email
            is_cn = credential.is_cn if hasattr(credential, 'is_cn') else True

            # 创建服务并同步健康数据
            from app.services.data_collection.garmin_connect import GarminConnectService

            service = GarminConnectService(
                email=email,
                password=password,
                is_cn=is_cn,
                user_id=user_id
            )

            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
            sync_result = service.sync_date_range(db, user_id, start_date, end_date)

            success_count = sync_result.get("success_count", 0)
            error_count = sync_result.get("error_count", 0)
            logger.info(f"用户 {user_id} 健康数据同步完成: 成功 {success_count} 天, 失败 {error_count} 天")

            # 同步运动活动数据（复用已认证的 client）
            synced_activities = 0
            try:
                from app.services.workout_sync import WorkoutSyncService

                workout_client = service.client if hasattr(service, 'client') and service._authenticated else None
                workout_sync_service = WorkoutSyncService(
                    email=email,
                    password=password,
                    is_cn=is_cn,
                    user_id=user_id,
                    client=workout_client
                )
                workout_result = asyncio.run(workout_sync_service.sync_activities(db, user_id, days))
                synced_activities = workout_result.get("synced_count", 0)
                logger.info(f"用户 {user_id} 运动活动同步完成: {synced_activities} 条")

                # 从运动记录中提取 VO2Max 更新到每日数据
                try:
                    from app.scheduler import _update_vo2max_from_workouts
                    _update_vo2max_from_workouts(db, user_id, days)
                except Exception as e:
                    logger.warning(f"用户 {user_id} VO2Max 更新失败: {e}")
            except Exception as e:
                logger.warning(f"用户 {user_id} 运动活动同步失败: {e}", exc_info=True)

            # 检测新同步的运动并触发自动分析
            try:
                twelve_hours_ago = datetime.utcnow() - timedelta(hours=12)
                analyzed_workout_ids = {
                    r.workout_id for r in db.query(WorkoutAnalysisResult.workout_id).filter(
                        WorkoutAnalysisResult.user_id == user_id
                    ).all()
                }
                new_workouts_query = db.query(WorkoutRecord).filter(
                    WorkoutRecord.user_id == user_id,
                    WorkoutRecord.created_at >= twelve_hours_ago,
                )
                if analyzed_workout_ids:
                    new_workouts_query = new_workouts_query.filter(
                        ~WorkoutRecord.id.in_(analyzed_workout_ids)
                    )
                new_workouts = new_workouts_query.all()
                for w in new_workouts:
                    logger.info(f"触发自动分析: user={user_id} workout={w.id} ({w.activity_type})")
                    auto_analyze_workout.delay(user_id, w.id)
            except Exception as e:
                logger.warning(f"检测新运动触发分析失败: {e}")

            # 触发健康异常检测
            try:
                from app.services.anomaly_detection_service import AnomalyDetectionService
                anomaly_svc = AnomalyDetectionService(db)
                alerts = anomaly_svc.detect_anomalies(user_id)
                if alerts:
                    logger.info(f"用户 {user_id} 检测到 {len(alerts)} 个健康异常")
                    asyncio.run(anomaly_svc.send_alerts(user_id, alerts))
            except Exception as e:
                logger.warning(f"健康异常检测失败: {e}")

            # 更新同步状态
            garmin_credential_service.update_sync_status(db, user_id)

            return {
                "status": "success",
                "success_count": success_count,
                "error_count": error_count,
                "activities_count": synced_activities
            }

    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task
def sync_all_users_garmin():
    """
    同步所有用户的 Garmin 数据（定时任务）
    """
    logger.info("开始批量同步所有用户 Garmin 数据")

    with SessionLocal() as db:
        from app.models.user import GarminCredential

        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
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
            analysis = asyncio.run(service.openclaw.analyze(prompt))

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
                asyncio.run(
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
