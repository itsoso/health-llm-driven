"""
健康分析任务
"""
import logging
from datetime import date, timedelta
from sqlalchemy import func as sa_func
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
from app.models.daily_health import GarminData
from app.services.ai_scheduler import AIScheduler
from app.utils.timezone import get_china_today

logger = logging.getLogger(__name__)


@celery_app.task
def generate_daily_plan_for_all():
    """
    为所有用户生成今日健康计划（每日6:00执行）
    """
    logger.info("开始生成每日健康计划")
    
    with SessionLocal() as db:
        # 获取所有活跃用户
        users = db.query(User).filter(User.is_active == True).all()
        
        scheduler = AIScheduler(db)
        success_count = 0
        
        for user in users:
            try:
                # 生成早间简报
                briefing = scheduler.generate_morning_briefing(user.id)
                
                if briefing.get("success"):
                    success_count += 1
                    logger.info(f"用户 {user.id} 每日计划生成成功")
                else:
                    logger.warning(f"用户 {user.id} 每日计划生成失败: {briefing.get('error')}")
                    
            except Exception as e:
                logger.error(f"用户 {user.id} 每日计划生成异常: {e}")
    
    logger.info(f"每日健康计划生成完成，成功 {success_count}/{len(users)} 用户")
    return {"success_count": success_count, "total": len(users)}


@celery_app.task
def generate_weekly_reports():
    """
    生成升级版周报 (每周日 20:30 北京时间执行)

    v2 升级: 跨实体反馈引擎
    - 基础数据聚合 (来自 health_report_service)
    - Cross-reference active supplement_audits 和 health_consultations
    - Predictions 中期校验 (consultation.verify_predictions)
    - 基因对齐度评分 (FADS1/IL-6/ALDH2/KCNJ11/PPARGC1A/MTHFR 等)
    - 落 health_reports 表, ai_analysis 含完整 markdown
    """
    logger.info("开始生成升级版周报 (Sunday 20:30)")

    with SessionLocal() as db:
        users = db.query(User).filter(User.is_active == True).all()

        today = get_china_today()
        # 本周 = 最近过去的周一 ~ 今天(周日)
        # today.weekday() 周一=0, 周日=6
        days_since_monday = today.weekday()  # 周日 = 6
        week_start = today - timedelta(days=days_since_monday)
        week_end = today

        generated_count = 0
        failed_count = 0

        for user in users:
            try:
                from app.services.weekly_report_service import weekly_report_service
                report = weekly_report_service.build_enhanced_review(
                    db, user.id, week_start, week_end
                )
                if report:
                    generated_count += 1
                    logger.info(
                        f"用户 {user.id} 升级周报生成成功: report_id={report.id} "
                        f"score={report.health_score}"
                    )
                else:
                    logger.info(f"用户 {user.id} 本周无数据, 跳过")
            except Exception as e:
                failed_count += 1
                logger.error(f"用户 {user.id} 周报生成失败: {e}", exc_info=True)

    logger.info(f"升级周报生成完成: {generated_count} 成功 / {failed_count} 失败")
    return {"generated_count": generated_count, "failed_count": failed_count}


@celery_app.task
def analyze_health_trends(user_id: int, days: int = 30):
    """
    分析用户健康趋势
    """
    logger.info(f"分析用户 {user_id} 最近 {days} 天的健康趋势")

    with SessionLocal() as db:
        today = get_china_today()
        metrics = {
            "steps": GarminData.steps,
            "sleep_score": GarminData.sleep_score,
            "resting_heart_rate": GarminData.resting_heart_rate,
        }

        trends = {}
        for metric_name, metric_col in metrics.items():
            # 7-day average
            seven_days_ago = today - timedelta(days=7)
            avg_7d_row = db.query(sa_func.avg(metric_col)).filter(
                GarminData.user_id == user_id,
                GarminData.record_date > seven_days_ago,
                GarminData.record_date <= today,
                metric_col.isnot(None)
            ).scalar()

            # 30-day average
            thirty_days_ago = today - timedelta(days=30)
            avg_30d_row = db.query(sa_func.avg(metric_col)).filter(
                GarminData.user_id == user_id,
                GarminData.record_date > thirty_days_ago,
                GarminData.record_date <= today,
                metric_col.isnot(None)
            ).scalar()

            if avg_7d_row is not None and avg_30d_row is not None and avg_30d_row != 0:
                avg_7d = float(avg_7d_row)
                avg_30d = float(avg_30d_row)
                change_pct = (avg_7d - avg_30d) / abs(avg_30d) * 100

                # For resting_heart_rate, lower is better (invert direction)
                if metric_name == "resting_heart_rate":
                    direction = "improving" if change_pct < -15 else ("declining" if change_pct > 15 else "stable")
                else:
                    direction = "improving" if change_pct > 15 else ("declining" if change_pct < -15 else "stable")

                trends[metric_name] = {
                    "avg_7d": round(avg_7d, 1),
                    "avg_30d": round(avg_30d, 1),
                    "change_pct": round(change_pct, 1),
                    "direction": direction,
                }
            else:
                trends[metric_name] = {
                    "avg_7d": round(float(avg_7d_row), 1) if avg_7d_row is not None else None,
                    "avg_30d": round(float(avg_30d_row), 1) if avg_30d_row is not None else None,
                    "change_pct": None,
                    "direction": "insufficient_data",
                }

        flagged = [name for name, t in trends.items() if t["direction"] in ("improving", "declining")]
        logger.info(f"用户 {user_id} 趋势分析完成，标记指标: {flagged}")

    return {"user_id": user_id, "days": days, "status": "completed", "trends": trends}
