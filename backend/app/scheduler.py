import asyncio
import logging
from datetime import datetime, timedelta
from app.services.data_collection.garmin_connect import GarminConnectService
from app.config import settings
from app.database import SessionLocal
import threading

logger = logging.getLogger(__name__)

async def sync_garmin_task():
    """定期同步 Garmin 数据的后台任务"""
    if not settings.garmin_email or not settings.garmin_password:
        logger.warning("未配置 GARMIN_EMAIL 或 GARMIN_PASSWORD，后台同步跳过")
        return

    logger.info(f"开始执行后台 Garmin 数据同步: {datetime.now()}")
    
    db = SessionLocal()
    try:
        # 默认同步最近 3 天的数据，确保没有遗漏
        user_id = 1 # 默认用户 ID，生产环境可从数据库获取所有用户
        service = GarminConnectService(settings.garmin_email, settings.garmin_password)
        
        # 计算日期范围（最近3天）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=2)  # 包括今天，共3天
        
        # sync_date_range 会自动处理认证（通过 _ensure_authenticated）
        result = service.sync_date_range(db, user_id, start_date, end_date)
        
        success_count = result.get("success_count", 0)
        fail_count = result.get("error_count", 0)
        
        logger.info(f"后台同步完成: 成功 {success_count} 天, 失败 {fail_count} 天")
            
    except Exception as e:
        logger.error(f"后台同步过程中出现错误: {str(e)}", exc_info=True)
    finally:
        db.close()

async def scheduler_loop(interval_hours: int = 2):
    """无限循环的任务调度器"""
    logger.info(f"Garmin 后台同步调度器已启动，间隔: {interval_hours} 小时")
    
    # 第一次运行前先等待一分钟，确保系统完全启动
    await asyncio.sleep(60)
    
    while True:
        try:
            await sync_garmin_task()
        except Exception as e:
            logger.error(f"调度器循环出错: {e}")
        
        logger.info(f"下一次同步将在 {interval_hours} 小时后执行")
        await asyncio.sleep(interval_hours * 3600)

def start_scheduler(app):
    """在后台线程中启动异步调度器"""
    def run_async_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(scheduler_loop())
        loop.close()

    # 使用守护线程，确保主程序退出时线程也退出
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()
    return thread

