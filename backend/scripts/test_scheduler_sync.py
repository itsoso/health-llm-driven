#!/usr/bin/env python3
"""
测试后台调度器的同步功能

模拟调度器的同步调用，验证修复后的代码是否正常工作
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.data_collection.garmin_connect import GarminConnectService
from app.config import settings
from app.database import SessionLocal
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def test_sync():
    """测试同步功能"""
    if not settings.garmin_email or not settings.garmin_password:
        logger.error("未配置 GARMIN_EMAIL 或 GARMIN_PASSWORD")
        logger.info("请在 backend/.env 文件中配置:")
        logger.info("GARMIN_EMAIL=your_email@example.com")
        logger.info("GARMIN_PASSWORD=your_password")
        return False

    logger.info("=" * 60)
    logger.info("开始测试后台同步功能")
    logger.info("=" * 60)
    
    db = SessionLocal()
    try:
        # 默认同步最近 3 天的数据，确保没有遗漏
        user_id = 1  # 默认用户 ID
        service = GarminConnectService(settings.garmin_email, settings.garmin_password)
        
        # 计算日期范围（最近3天）
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=2)  # 包括今天，共3天
        
        logger.info(f"同步日期范围: {start_date} 到 {end_date}")
        logger.info(f"用户ID: {user_id}")
        logger.info("-" * 60)
        
        # sync_date_range 会自动处理认证（通过 _ensure_authenticated）
        logger.info("开始同步...")
        result = service.sync_date_range(db, user_id, start_date, end_date)
        
        success_count = result.get("success_count", 0)
        fail_count = result.get("error_count", 0)
        results = result.get("results", [])
        errors = result.get("errors", [])
        
        logger.info("-" * 60)
        logger.info("同步结果:")
        logger.info(f"✅ 成功: {success_count} 天")
        logger.info(f"❌ 失败: {fail_count} 天")
        
        if results:
            logger.info("\n成功同步的日期:")
            for r in results:
                logger.info(f"  - {r.get('date')}: {r.get('status')}")
        
        if errors:
            logger.info("\n失败的日期:")
            for e in errors:
                error_msg = e.get('error', '未知错误')
                logger.info(f"  - {e.get('date')}: {e.get('status')} - {error_msg}")
        
        logger.info("=" * 60)
        
        if fail_count == 0:
            logger.info("✅ 测试通过：所有数据同步成功")
            return True
        elif success_count > 0:
            logger.warning("⚠️ 部分数据同步成功，部分失败（可能是某些日期没有数据）")
            return True
        else:
            logger.error("❌ 测试失败：所有数据同步失败")
            return False
            
    except Exception as e:
        logger.error(f"测试过程中出现错误: {str(e)}", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == "__main__":
    success = test_sync()
    sys.exit(0 if success else 1)

