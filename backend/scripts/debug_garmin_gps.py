#!/usr/bin/env python3
"""
调试Garmin GPS数据获取
查看Garmin API返回的实际数据结构
"""
import sys
import os
import json
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
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def debug_activity_gps(user_id: int, activity_id: int = None):
    """调试活动GPS数据"""
    db = SessionLocal()
    try:
        # 获取用户
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            logger.error(f"用户 {user_id} 不存在")
            return
        
        # 获取Garmin凭证
        cred_service = GarminCredentialService()
        credentials = cred_service.get_decrypted_credentials(db, user_id)
        
        if not credentials:
            logger.error(f"用户 {user_id} 未配置Garmin账号")
            return
        
        sync_service = WorkoutSyncService(
            email=credentials["email"],
            password=credentials["password"],
            is_cn=credentials.get("is_cn", False),
            user_id=user_id
        )
        
        # 确保已认证
        sync_service._ensure_authenticated()
        
        # 如果没有指定activity_id，使用最新的有external_id的活动
        if not activity_id:
            record = db.query(WorkoutRecord).filter(
                WorkoutRecord.user_id == user_id,
                WorkoutRecord.external_id.isnot(None)
            ).order_by(WorkoutRecord.workout_date.desc()).first()
            
            if not record:
                logger.error("没有找到有external_id的活动")
                return
            
            activity_id = int(record.external_id)
            logger.info(f"使用活动: {record.workout_name or record.workout_type} (ID: {activity_id}, 日期: {record.workout_date})")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"调试活动 {activity_id} 的GPS数据")
        logger.info(f"{'='*60}\n")
        
        # 获取活动详情
        details = sync_service.client.get_activity(activity_id)
        
        logger.info("1. get_activity() 返回的字段:")
        if isinstance(details, dict):
            logger.info(f"   字段列表: {list(details.keys())[:20]}...")  # 只显示前20个
            # 查找GPS相关字段
            gps_keys = [k for k in details.keys() if any(keyword in k.lower() for keyword in ['gps', 'geo', 'polyline', 'route', 'track', 'location', 'lat', 'lng', 'lon'])]
            if gps_keys:
                logger.info(f"   GPS相关字段: {gps_keys}")
                for key in gps_keys:
                    value = details[key]
                    logger.info(f"   {key}: {type(value)} = {str(value)[:100]}")
            else:
                logger.info("   未找到GPS相关字段")
        else:
            logger.info(f"   返回类型: {type(details)}")
        
        # 尝试获取活动详情
        try:
            activity_details = sync_service.client.get_activity_details(activity_id)
            logger.info("\n2. get_activity_details() 返回:")
            if isinstance(activity_details, dict):
                logger.info(f"   字段列表: {list(activity_details.keys())[:20]}...")
                gps_keys = [k for k in activity_details.keys() if any(keyword in k.lower() for keyword in ['gps', 'geo', 'polyline', 'route', 'track', 'location', 'lat', 'lng', 'lon'])]
                if gps_keys:
                    logger.info(f"   GPS相关字段: {gps_keys}")
                    for key in gps_keys:
                        value = activity_details[key]
                        if key == 'geoPolylineDTO' and isinstance(value, dict):
                            logger.info(f"   {key}: {type(value)}")
                            logger.info(f"   完整内容: {json.dumps(value, indent=2, ensure_ascii=False)}")
                        else:
                            logger.info(f"   {key}: {type(value)} = {str(value)[:200]}")
                else:
                    logger.info("   未找到GPS相关字段")
            else:
                logger.info(f"   返回类型: {type(activity_details)}")
        except Exception as e:
            logger.error(f"   get_activity_details 失败: {e}")
        
        # 尝试获取GPS数据
        try:
            gps_data = sync_service.client.get_activity_gps(activity_id)
            logger.info("\n3. get_activity_gps() 返回:")
            if gps_data:
                logger.info(f"   类型: {type(gps_data)}")
                if isinstance(gps_data, dict):
                    logger.info(f"   字段: {list(gps_data.keys())}")
                elif isinstance(gps_data, list):
                    logger.info(f"   列表长度: {len(gps_data)}")
                    if len(gps_data) > 0:
                        logger.info(f"   第一个元素: {gps_data[0]}")
                else:
                    logger.info(f"   值: {str(gps_data)[:200]}")
            else:
                logger.info("   返回 None")
        except Exception as e:
            logger.error(f"   get_activity_gps 失败: {e}")
        
        # 尝试使用我们的方法获取
        logger.info("\n4. 使用 get_activity_details() 方法:")
        details_data = await sync_service.get_activity_details(activity_id)
        if details_data:
            logger.info(f"   返回的键: {list(details_data.keys())}")
            if details_data.get("gps_data"):
                logger.info(f"   GPS数据存在: {type(details_data['gps_data'])}")
                if isinstance(details_data['gps_data'], dict):
                    logger.info(f"   GPS数据字段: {list(details_data['gps_data'].keys())}")
            else:
                logger.info("   GPS数据不存在")
        
    finally:
        db.close()


async def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python debug_garmin_gps.py <user_id> [activity_id]")
        sys.exit(1)
    
    user_id = int(sys.argv[1])
    activity_id = int(sys.argv[2]) if len(sys.argv) > 2 else None
    
    await debug_activity_gps(user_id, activity_id)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
