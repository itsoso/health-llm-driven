"""
调试心率区间数据脚本
用于检查Garmin API返回的心率区间数据格式
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import logging
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models.user import User
from app.services.workout_sync import WorkoutSyncService

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    db = SessionLocal()
    try:
        # 获取第一个用户（或指定用户ID）
        user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
        user = db.query(User).filter_by(id=user_id).first()
        
        if not user:
            logger.error(f"用户 {user_id} 不存在")
            return
        
        logger.info(f"开始调试用户 {user.email} 的心率区间数据")
        
        # 创建同步服务
        sync_service = WorkoutSyncService(db, user_id)
        
        # 获取最近的活动
        logger.info("获取最近的Garmin活动...")
        activities = await sync_service.get_activities(limit=5)
        
        if not activities:
            logger.warning("没有找到活动数据")
            return
        
        logger.info(f"找到 {len(activities)} 个活动")
        
        # 检查每个活动的心率区间数据
        for i, activity in enumerate(activities):
            activity_id = activity.get("activityId")
            activity_name = activity.get("activityName", "未命名")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"活动 {i+1}: {activity_name} (ID: {activity_id})")
            logger.info(f"{'='*60}")
            
            # 检查活动基本信息中的心率区间
            hr_zones = activity.get("hrTimeInZones")
            logger.info(f"hrTimeInZones 字段: {hr_zones}")
            logger.info(f"hrTimeInZones 类型: {type(hr_zones)}")
            
            # 检查其他可能包含心率区间的字段
            for key in activity.keys():
                if 'hr' in key.lower() or 'zone' in key.lower() or 'heart' in key.lower():
                    logger.info(f"  {key}: {activity[key]}")
            
            # 获取活动详细信息
            logger.info("\n获取活动详细信息...")
            details_result = await sync_service.get_activity_details(activity_id)
            
            if details_result:
                details = details_result.get("details", {})
                hr_data = details_result.get("heart_rate_data", {})
                
                # 检查详细信息中的心率区间
                logger.info("\n活动详细信息中的心率相关字段:")
                for key in details.keys():
                    if 'hr' in key.lower() or 'zone' in key.lower() or 'heart' in key.lower():
                        logger.info(f"  {key}: {details[key]}")
                
                # 检查心率数据
                if hr_data:
                    logger.info("\n心率数据结构:")
                    logger.info(f"  类型: {type(hr_data)}")
                    if isinstance(hr_data, dict):
                        logger.info(f"  键: {list(hr_data.keys())}")
                        for key in hr_data.keys():
                            if 'zone' in key.lower():
                                logger.info(f"    {key}: {hr_data[key]}")
            
            logger.info("\n")
        
    except Exception as e:
        logger.error(f"调试失败: {e}", exc_info=True)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
