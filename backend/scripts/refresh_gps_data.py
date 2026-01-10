#!/usr/bin/env python3
"""
批量刷新运动记录的GPS路线数据
用法: python scripts/refresh_gps_data.py [user_id] [days]
示例: python scripts/refresh_gps_data.py 1 30  # 刷新用户1最近30天的记录
"""
import sys
import os
import asyncio
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord
from app.models.user import User
from app.services.auth import GarminCredentialService
from app.services.workout_sync import WorkoutSyncService
from app.utils.timezone import get_china_today
from datetime import timedelta
import json
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)
# 设置workout_sync的日志级别
logging.getLogger('app.services.workout_sync').setLevel(logging.DEBUG)


async def refresh_gps_for_user(db: Session, user_id: int, days: int = 30):
    """为指定用户刷新GPS数据"""
    # 获取用户
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        logger.error(f"用户 {user_id} 不存在")
        return {"success": False, "message": f"用户 {user_id} 不存在"}
    
    # 获取Garmin凭证
    cred_service = GarminCredentialService()
    credentials = cred_service.get_decrypted_credentials(db, user_id)
    
    if not credentials:
        logger.error(f"用户 {user_id} 未配置Garmin账号")
        return {"success": False, "message": f"用户 {user_id} 未配置Garmin账号"}
    
    # 查找需要刷新的记录
    today = get_china_today()
    start_date = today - timedelta(days=days)
    
    records = db.query(WorkoutRecord).filter(
        WorkoutRecord.user_id == user_id,
        WorkoutRecord.source == "garmin",
        WorkoutRecord.external_id.isnot(None),
        WorkoutRecord.workout_date >= start_date
    ).all()
    
    if not records:
        logger.info(f"用户 {user_id} 没有需要刷新的记录")
        return {"success": True, "refreshed_count": 0, "total_count": 0}
    
    logger.info(f"用户 {user_id} 找到 {len(records)} 条需要刷新的记录")
    
    try:
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=user_id
        )
        
        refreshed_count = 0
        failed_count = 0
        
        for i, record in enumerate(records, 1):
            try:
                logger.info(f"[{i}/{len(records)}] 处理运动记录 {record.id}: {record.workout_name or record.workout_type} ({record.workout_date})")
                
                # 如果已有GPS数据，跳过
                if record.route_data:
                    logger.debug(f"  记录 {record.id} 已有GPS数据，跳过")
                    continue
                
                # 获取活动详情
                details_data = await sync_service.get_activity_details(int(record.external_id))
                
                if details_data and details_data.get("gps_data"):
                    route_points = sync_service._parse_gps_route(details_data["gps_data"], record.start_time)
                    
                    if route_points:
                        record.route_data = json.dumps(route_points)
                        refreshed_count += 1
                        logger.info(f"  ✓ 获取到 {len(route_points)} 个GPS点")
                    else:
                        logger.warning(f"  ✗ 无法解析GPS数据")
                else:
                    logger.warning(f"  ✗ Garmin未提供GPS数据（可能是室内运动）")
                
                # 添加延迟，避免请求过快
                await asyncio.sleep(0.5)
                
            except Exception as e:
                failed_count += 1
                logger.error(f"  ✗ 刷新记录 {record.id} 失败: {e}")
                continue
        
        db.commit()
        
        result = {
            "success": True,
            "refreshed_count": refreshed_count,
            "failed_count": failed_count,
            "total_count": len(records)
        }
        
        logger.info(f"用户 {user_id} GPS数据刷新完成: 成功 {refreshed_count}, 失败 {failed_count}, 总计 {len(records)}")
        return result
        
    except Exception as e:
        logger.error(f"刷新GPS数据失败: {e}")
        return {"success": False, "message": str(e)}


async def refresh_all_users(days: int = 30):
    """为所有用户刷新GPS数据"""
    db = SessionLocal()
    try:
        # 获取所有配置了Garmin的用户
        users = db.query(User).all()
        cred_service = GarminCredentialService()
        
        total_refreshed = 0
        total_failed = 0
        total_records = 0
        
        for user in users:
            credentials = cred_service.get_decrypted_credentials(db, user.id)
            if credentials:
                logger.info(f"\n{'='*60}")
                logger.info(f"处理用户 {user.id}: {user.email}")
                logger.info(f"{'='*60}")
                
                result = await refresh_gps_for_user(db, user.id, days)
                
                if result.get("success"):
                    total_refreshed += result.get("refreshed_count", 0)
                    total_failed += result.get("failed_count", 0)
                    total_records += result.get("total_count", 0)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"全部完成: 成功 {total_refreshed}, 失败 {total_failed}, 总计 {total_records}")
        logger.info(f"{'='*60}")
        
    finally:
        db.close()


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        # 没有参数，刷新所有用户
        logger.info("未指定用户ID，将刷新所有用户的GPS数据")
        await refresh_all_users(days=30)
    else:
        user_id = int(sys.argv[1])
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        
        db = SessionLocal()
        try:
            result = await refresh_gps_for_user(db, user_id, days)
            if not result.get("success"):
                sys.exit(1)
        finally:
            db.close()


if __name__ == "__main__":
    asyncio.run(main())
