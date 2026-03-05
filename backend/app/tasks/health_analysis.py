"""
健康分析任务
"""
import logging
from datetime import date, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.user import User
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
    生成周报（每周一9:00执行）
    """
    logger.info("开始生成周报")
    
    with SessionLocal() as db:
        users = db.query(User).filter(User.is_active == True).all()
        
        today = get_china_today()
        week_start = today - timedelta(days=7)
        
        generated_count = 0
        
        for user in users:
            try:
                from app.services.weekly_report_service import weekly_report_service
                report = weekly_report_service.generate_report(db, user.id, week_start, today)
                if report.get("days_with_data", 0) > 0:
                    generated_count += 1
                    logger.info(f"用户 {user.id} 周报生成成功: {report.get('days_with_data')}天数据")
                else:
                    logger.info(f"用户 {user.id} 本周无数据，跳过")
            except Exception as e:
                logger.error(f"用户 {user.id} 周报生成失败: {e}")
    
    logger.info(f"周报生成完成，共 {generated_count} 份")
    return {"generated_count": generated_count}


@celery_app.task
def analyze_health_trends(user_id: int, days: int = 30):
    """
    分析用户健康趋势
    """
    logger.info(f"分析用户 {user_id} 最近 {days} 天的健康趋势")
    
    with SessionLocal() as db:
        # TODO: 实现趋势分析逻辑
        pass
    
    return {"user_id": user_id, "days": days, "status": "completed"}
