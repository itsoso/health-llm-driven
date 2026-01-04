#!/usr/bin/env python3
"""
批量更新历史数据的 HRV 值

该脚本会检查数据库中所有缺少 HRV 数据的记录，
然后从 Garmin Connect 重新同步这些日期的数据以获取 HRV 值。
"""
import sys
import os
from datetime import date, timedelta
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.daily_health import GarminData
from app.services.data_collection.garmin_connect import GarminConnectService
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def find_missing_hrv_dates(db: Session, user_id: int) -> list:
    """查找所有缺少 HRV 数据的日期"""
    records = db.query(GarminData).filter(
        GarminData.user_id == user_id,
        GarminData.hrv.is_(None)
    ).order_by(GarminData.record_date.desc()).all()
    
    dates = [record.record_date for record in records]
    logger.info(f"找到 {len(dates)} 条缺少 HRV 数据的记录")
    return dates


def update_hrv_for_date(
    db: Session,
    service: GarminConnectService,
    user_id: int,
    target_date: date
) -> bool:
    """更新指定日期的 HRV 数据"""
    try:
        # 获取该日期的所有数据
        raw_data = service.get_all_daily_data(target_date)
        
        if not raw_data:
            logger.warning(f"{target_date}: 无数据")
            return False
        
        # 解析数据
        garmin_data_create = service.parse_to_garmin_data_create(
            raw_data, user_id, target_date
        )
        
        # 只更新 HRV 字段
        existing_record = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.record_date == target_date
        ).first()
        
        if existing_record:
            if garmin_data_create.hrv is not None:
                existing_record.hrv = garmin_data_create.hrv
                db.commit()
                logger.info(f"{target_date}: HRV 更新为 {garmin_data_create.hrv}")
                return True
            else:
                logger.warning(f"{target_date}: Garmin 数据中也没有 HRV")
                return False
        else:
            logger.warning(f"{target_date}: 数据库中没有该日期的记录")
            return False
            
    except Exception as e:
        logger.error(f"{target_date}: 更新失败 - {e}")
        db.rollback()
        return False


def main():
    if len(sys.argv) < 4:
        print("用法: python update_hrv_data.py <email> <password> <user_id> [--days N]")
        print("示例: python update_hrv_data.py itsoso@126.com Sisi1124 1")
        print("      python update_hrv_data.py itsoso@126.com Sisi1124 1 --days 30")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    user_id = int(sys.argv[3])
    
    # 检查是否限制天数
    days_limit = None
    if '--days' in sys.argv:
        idx = sys.argv.index('--days')
        if idx + 1 < len(sys.argv):
            days_limit = int(sys.argv[idx + 1])
    
    db = SessionLocal()
    try:
        # 初始化 Garmin 服务（会自动登录）
        logger.info("正在连接 Garmin Connect...")
        service = GarminConnectService(email, password)
        logger.info("✅ 服务初始化成功（首次调用时会自动登录）")
        
        # 查找缺少 HRV 的日期
        missing_dates = find_missing_hrv_dates(db, user_id)
        
        if not missing_dates:
            logger.info("所有记录都已包含 HRV 数据")
            return
        
        # 如果指定了天数限制，只处理最近 N 天
        if days_limit:
            cutoff_date = date.today() - timedelta(days=days_limit)
            missing_dates = [d for d in missing_dates if d >= cutoff_date]
            logger.info(f"限制为最近 {days_limit} 天，剩余 {len(missing_dates)} 条记录")
        
        if not missing_dates:
            logger.info("指定时间范围内没有缺少 HRV 的记录")
            return
        
        # 批量更新
        logger.info(f"\n开始更新 {len(missing_dates)} 条记录的 HRV 数据...")
        logger.info("=" * 60)
        
        success_count = 0
        fail_count = 0
        
        for i, target_date in enumerate(missing_dates, 1):
            logger.info(f"[{i}/{len(missing_dates)}] 处理 {target_date}...")
            if update_hrv_for_date(db, service, user_id, target_date):
                success_count += 1
            else:
                fail_count += 1
            
            # 每10条记录提交一次，避免数据库锁定
            if i % 10 == 0:
                db.commit()
                logger.info(f"已处理 {i} 条记录，成功 {success_count}，失败 {fail_count}")
        
        db.commit()
        
        logger.info("=" * 60)
        logger.info(f"更新完成!")
        logger.info(f"✅ 成功: {success_count} 条")
        logger.info(f"❌ 失败: {fail_count} 条")
        
        # 验证结果
        remaining = db.query(GarminData).filter(
            GarminData.user_id == user_id,
            GarminData.hrv.is_(None)
        ).count()
        logger.info(f"仍缺少 HRV 的记录: {remaining} 条")
        
    except KeyboardInterrupt:
        logger.info("\n用户中断")
        db.rollback()
    except Exception as e:
        logger.error(f"发生错误: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

