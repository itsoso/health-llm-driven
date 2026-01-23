#!/usr/bin/env python3
"""
重新同步运动记录的 GPS 数据

用法:
    python scripts/resync_workout_gps.py --user-id 3 --workout-ids 50,48
"""
import sys
import os
import asyncio
import json
import argparse

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.database import SessionLocal
from app.services.workout_sync import WorkoutSyncService
from app.models.user import GarminCredential
from app.models.daily_health import WorkoutRecord
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


async def resync_workout_gps(user_id: int, workout_ids: list):
    """重新同步指定运动的 GPS 数据"""
    db = SessionLocal()
    try:
        logger.info(f"开始为用户 {user_id} 重新同步 {len(workout_ids)} 个运动的 GPS 数据")
        
        # 获取用户的 Garmin 凭证
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == user_id
        ).first()
        
        if not cred:
            logger.error(f"用户 {user_id} 没有 Garmin 凭证")
            return
        
        logger.info(f"用户 Garmin 邮箱: {cred.garmin_email}")
        logger.info(f"服务器类型: {'中国版' if cred.is_cn else '国际版'}")
        
        # 解密密码
        from app.services.auth import GarminCredentialService
        password = GarminCredentialService.decrypt_password(cred.encrypted_password)
        
        # 创建同步服务
        sync_service = WorkoutSyncService(
            user_id=user_id,
            email=cred.garmin_email,
            password=password,
            is_cn=cred.is_cn
        )
        
        # 尝试认证（使用缓存的 session）
        logger.info("正在认证 Garmin Connect...")
        try:
            sync_service._ensure_authenticated()
            logger.info("✅ Garmin Connect 认证成功")
        except Exception as e:
            logger.error(f"❌ Garmin Connect 认证失败: {e}")
            logger.error("请确保用户的 Garmin 凭证有效且 session 未过期")
            return
        
        success_count = 0
        failed_count = 0
        
        # 重新同步每个活动
        for workout_id in workout_ids:
            logger.info(f"\n{'='*60}")
            logger.info(f"正在处理活动 ID: {workout_id}")
            logger.info(f"{'='*60}")
            
            # 获取活动记录
            workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.id == workout_id
            ).first()
            
            if not workout:
                logger.error(f"  ❌ 活动 {workout_id} 不存在")
                failed_count += 1
                continue
            
            logger.info(f"  活动信息:")
            logger.info(f"    日期: {workout.workout_date}")
            logger.info(f"    名称: {workout.workout_name}")
            logger.info(f"    类型: {workout.workout_type}")
            logger.info(f"    距离: {workout.distance_meters} 米")
            logger.info(f"    External ID: {workout.external_id}")
            
            if not workout.external_id:
                logger.error(f"  ❌ 活动 {workout_id} 无 external_id")
                failed_count += 1
                continue
            
            # 如果距离为 0，跳过（室内运动）
            if not workout.distance_meters or workout.distance_meters < 10:
                logger.warning(f"  ⚠️  活动 {workout_id} 距离为 0，可能是室内运动，跳过")
                continue
            
            try:
                # 获取活动详细数据
                logger.info(f"  正在从 Garmin Connect 获取详细数据...")
                details = await sync_service.get_activity_details(
                    int(workout.external_id)
                )
                
                if not details:
                    logger.error(f"  ❌ 无法获取活动 {workout_id} 的详细数据")
                    failed_count += 1
                    continue
                
                # 检查 GPS 数据
                gps_data = details.get('gps_data')
                if not gps_data:
                    logger.warning(f"  ⚠️  活动 {workout_id} 没有 GPS 数据")
                    logger.info(f"  可能原因:")
                    logger.info(f"    1. 室内运动（跑步机、室内骑行等）")
                    logger.info(f"    2. GPS 信号差，未记录轨迹")
                    logger.info(f"    3. 设备未开启 GPS")
                    failed_count += 1
                    continue
                
                logger.info(f"  ✅ 获取到 GPS 数据，类型: {type(gps_data)}")
                if isinstance(gps_data, dict):
                    logger.info(f"  GPS 数据键: {list(gps_data.keys())}")
                
                # 解析 GPS 数据
                logger.info(f"  正在解析 GPS 路线...")
                route_points = sync_service._parse_gps_route(
                    gps_data,
                    start_time=workout.start_time
                )
                
                if not route_points:
                    logger.error(f"  ❌ 无法解析 GPS 数据")
                    failed_count += 1
                    continue
                
                logger.info(f"  ✅ 解析成功，得到 {len(route_points)} 个 GPS 点")
                
                # 显示第一个和最后一个点
                if len(route_points) > 0:
                    logger.info(f"  第一个点: {route_points[0]}")
                    logger.info(f"  最后一个点: {route_points[-1]}")
                
                # 更新数据库
                workout.route_data = json.dumps(route_points)
                db.commit()
                
                logger.info(f"  ✅ 活动 {workout_id} GPS 数据已更新到数据库")
                success_count += 1
                
            except Exception as e:
                logger.error(f"  ❌ 处理活动 {workout_id} 时出错: {e}")
                import traceback
                traceback.print_exc()
                failed_count += 1
        
        # 总结
        logger.info(f"\n{'='*60}")
        logger.info(f"同步完成")
        logger.info(f"{'='*60}")
        logger.info(f"成功: {success_count} 个")
        logger.info(f"失败: {failed_count} 个")
        logger.info(f"总计: {len(workout_ids)} 个")
        
    except Exception as e:
        logger.error(f"同步失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='重新同步运动记录的 GPS 数据')
    parser.add_argument('--user-id', type=int, required=True, help='用户 ID')
    parser.add_argument('--workout-ids', type=str, required=True, help='运动记录 ID，逗号分隔')
    
    args = parser.parse_args()
    
    # 解析运动记录 ID
    workout_ids = [int(x.strip()) for x in args.workout_ids.split(',')]
    
    # 运行同步
    asyncio.run(resync_workout_gps(args.user_id, workout_ids))


if __name__ == '__main__':
    main()
