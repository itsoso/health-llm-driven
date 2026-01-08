"""后台任务调度器 - 自动同步所有用户的Garmin数据"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from app.services.data_collection.garmin_connect import GarminConnectService, GarminAuthenticationError
from app.services.auth import garmin_credential_service
from app.models.user import GarminCredential
from app.database import SessionLocal
from app.utils.timezone import get_china_today, get_china_now
import threading

logger = logging.getLogger(__name__)


def get_all_sync_enabled_users(db) -> List[Dict[str, Any]]:
    """获取所有启用同步且凭证有效的用户及其解密后的凭证"""
    # 只获取启用同步且凭证有效的用户
    credentials = db.query(GarminCredential).filter(
        GarminCredential.sync_enabled == True,
        GarminCredential.credentials_valid == True  # 只同步凭证有效的用户
    ).all()
    
    users_with_credentials = []
    for cred in credentials:
        try:
            decrypted = garmin_credential_service.get_decrypted_credentials(db, cred.user_id)
            if decrypted:
                users_with_credentials.append({
                    "user_id": cred.user_id,
                    "email": decrypted["email"],
                    "password": decrypted["password"],
                    "is_cn": decrypted.get("is_cn", False),
                    "last_sync_at": cred.last_sync_at
                })
        except Exception as e:
            logger.error(f"解密用户 {cred.user_id} 的Garmin凭证失败: {e}")
    
    return users_with_credentials


async def sync_user_garmin_data(
    db, 
    user_id: int, 
    email: str, 
    password: str, 
    days: int = 3,
    is_cn: bool = False
) -> Dict[str, Any]:
    """同步单个用户的Garmin数据（包括健康数据和运动活动）"""
    result = {
        "user_id": user_id,
        "success": False,
        "success_count": 0,
        "error_count": 0,
        "activities_count": 0,
        "message": "",
        "is_auth_error": False
    }
    
    try:
        server_type = "中国版" if is_cn else "国际版"
        logger.info(f"用户 {user_id} 使用 {server_type} Garmin服务器")
        service = GarminConnectService(email, password, is_cn=is_cn, user_id=user_id)
        
        # 计算日期范围
        end_date = get_china_today()
        start_date = end_date - timedelta(days=days - 1)
        
        # 执行健康数据同步
        sync_result = service.sync_date_range(db, user_id, start_date, end_date)
        
        result["success"] = True
        result["success_count"] = sync_result.get("success_count", 0)
        result["error_count"] = sync_result.get("error_count", 0)
        
        # 同步运动活动数据
        try:
            from app.services.workout_sync import WorkoutSyncService
            workout_sync_service = WorkoutSyncService(
                email=email,
                password=password,
                is_cn=is_cn,
                user_id=user_id
            )
            workout_result = await workout_sync_service.sync_activities(db, user_id, days)
            result["activities_count"] = workout_result.get("synced_count", 0)
            logger.info(f"用户 {user_id} 运动活动同步完成: {result['activities_count']} 条")
        except Exception as e:
            logger.warning(f"用户 {user_id} 运动活动同步失败: {e}")
        
        result["message"] = f"同步完成: 健康数据 {result['success_count']} 天"
        if result["activities_count"] > 0:
            result["message"] += f", 运动活动 {result['activities_count']} 条"
        if result["error_count"] > 0:
            result["message"] += f", 失败 {result['error_count']} 天"
        
        # 更新最后同步时间（会重置错误状态）
        garmin_credential_service.update_sync_status(db, user_id)
        
        logger.info(f"用户 {user_id} Garmin数据同步成功: {result['message']}")
        
    except GarminAuthenticationError as e:
        # 明确的认证错误
        error_message = str(e)
        result["message"] = error_message
        result["is_auth_error"] = True
        
        # 更新错误状态，标记凭证无效
        garmin_credential_service.update_sync_error(db, user_id, error_message, is_auth_error=True)
        logger.warning(f"用户 {user_id} Garmin认证失败，已标记凭证无效: {error_message}")
        
    except Exception as e:
        error_str = str(e).lower()
        error_message = str(e)
        
        # 检测是否为认证错误
        is_auth_error = any(keyword in error_str for keyword in [
            '401', 'unauthorized', 'authentication', 'login failed', 
            'invalid credentials', 'password', '认证失败', '登录失败', 'oauth'
        ])
        
        result["message"] = error_message
        result["is_auth_error"] = is_auth_error
        
        # 更新错误状态
        garmin_credential_service.update_sync_error(db, user_id, error_message, is_auth_error)
        
        if is_auth_error:
            logger.warning(f"用户 {user_id} Garmin认证失败，已标记凭证无效: {error_message}")
        else:
            logger.error(f"用户 {user_id} Garmin数据同步失败: {e}")
    
    return result


async def sync_all_users_garmin_task(days: int = 3) -> Dict[str, Any]:
    """同步所有启用同步的用户的Garmin数据"""
    logger.info(f"开始执行全部用户 Garmin 数据同步: {get_china_now()}")
    
    db = SessionLocal()
    results = {
        "total_users": 0,
        "success_users": 0,
        "failed_users": 0,
        "details": []
    }
    
    try:
        # 获取所有启用同步的用户
        users = get_all_sync_enabled_users(db)
        results["total_users"] = len(users)
        
        if not users:
            logger.warning("没有找到启用同步的用户")
            return results
        
        logger.info(f"找到 {len(users)} 个启用同步的用户")
        
        # 逐个同步用户数据
        for user_info in users:
            user_result = await sync_user_garmin_data(
                db,
                user_info["user_id"],
                user_info["email"],
                user_info["password"],
                days,
                is_cn=user_info.get("is_cn", False)
            )
            
            results["details"].append(user_result)
            
            if user_result["success"]:
                results["success_users"] += 1
            else:
                results["failed_users"] += 1
            
            # 每个用户之间稍微间隔，避免太频繁请求
            await asyncio.sleep(2)
        
        logger.info(
            f"全部用户同步完成: 总计 {results['total_users']} 用户, "
            f"成功 {results['success_users']}, 失败 {results['failed_users']}"
        )
        
    except Exception as e:
        logger.error(f"全部用户同步过程中出现错误: {str(e)}", exc_info=True)
    finally:
        db.close()
    
    return results


async def scheduler_loop(interval_minutes: int = 60):
    """
    无限循环的任务调度器
    
    Args:
        interval_minutes: 同步间隔（分钟），默认60分钟
    """
    logger.info(f"Garmin 后台同步调度器已启动，间隔: {interval_minutes} 分钟")
    
    # 第一次运行前先等待2分钟，确保系统完全启动
    await asyncio.sleep(120)
    
    while True:
        try:
            await sync_all_users_garmin_task(days=3)
        except Exception as e:
            logger.error(f"调度器循环出错: {e}")
        
        logger.info(f"下一次同步将在 {interval_minutes} 分钟后执行")
        await asyncio.sleep(interval_minutes * 60)


def start_scheduler(app, interval_minutes: int = 60):
    """
    在后台线程中启动异步调度器
    
    Args:
        app: FastAPI应用实例
        interval_minutes: 同步间隔（分钟），默认60分钟
    """
    def run_async_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(scheduler_loop(interval_minutes))
        loop.close()

    # 使用守护线程，确保主程序退出时线程也退出
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()
    logger.info("后台同步调度器线程已启动")
    return thread
