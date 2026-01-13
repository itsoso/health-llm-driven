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
    # 查询所有启用同步的用户（包括需要MFA的）
    all_credentials = db.query(GarminCredential).filter(
        GarminCredential.sync_enabled == True,
        GarminCredential.credentials_valid == True
    ).all()
    
    # 统计需要MFA的用户
    mfa_users = [cred for cred in all_credentials if cred.requires_mfa == True]
    if mfa_users:
        mfa_user_ids = [cred.user_id for cred in mfa_users]
        logger.info(f"🔐 检测到 {len(mfa_users)} 个需要MFA验证的用户，已跳过自动同步: {mfa_user_ids}")
    
    # 只获取不需要MFA的用户
    credentials = [cred for cred in all_credentials if cred.requires_mfa == False]
    
    logger.info(f"📊 同步用户统计: 总启用同步用户={len(all_credentials)}, 需要MFA(已跳过)={len(mfa_users)}, 可同步用户={len(credentials)}")
    
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
                logger.debug(f"✅ 用户 {cred.user_id} ({decrypted['email']}) 已加入同步队列")
        except Exception as e:
            logger.error(f"❌ 解密用户 {cred.user_id} 的Garmin凭证失败: {e}")
    
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
        "is_auth_error": False,
        "requires_mfa": False  # 是否需要MFA验证
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
        
        # 检测是否需要MFA验证
        requires_mfa = any(keyword in error_str for keyword in [
            'mfa', 'two-factor', '两步验证', 'two factor', 'verification'
        ])
        
        if requires_mfa:
            # 需要MFA验证的用户，跳过同步，不标记为失败
            result["requires_mfa"] = True
            result["message"] = "需要两步验证，跳过自动同步"
            logger.info(f"用户 {user_id} 需要MFA两步验证，跳过后台自动同步")
            # 不更新错误状态，保持凭证有效
            return result
        
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
    logger.info(f"🚀 开始执行全部用户 Garmin 数据同步任务: {get_china_now()}")
    logger.info(f"📅 同步天数: {days} 天")
    
    db = SessionLocal()
    results = {
        "total_users": 0,
        "success_users": 0,
        "failed_users": 0,
        "mfa_users": 0,  # 需要MFA验证的用户数
        "details": []
    }
    
    try:
        # 获取所有启用同步的用户（已过滤MFA用户）
        users = get_all_sync_enabled_users(db)
        results["total_users"] = len(users)
        
        if not users:
            logger.warning("⚠️ 没有找到可同步的用户（所有用户都需要MFA或未启用同步）")
            return results
        
        logger.info(f"✅ 找到 {len(users)} 个可同步的用户，开始逐个同步...")
        for idx, user_info in enumerate(users, 1):
            logger.info(f"📌 [{idx}/{len(users)}] 开始同步用户 {user_info['user_id']} ({user_info['email']})")
        
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
            elif user_result.get("requires_mfa"):
                results["mfa_users"] += 1
            else:
                results["failed_users"] += 1
            
            # 每个用户之间稍微间隔，避免太频繁请求
            await asyncio.sleep(2)
        
        logger.info(
            f"✅ 全部用户同步完成: 总计 {results['total_users']} 用户, "
            f"成功 {results['success_users']}, 失败 {results['failed_users']}, "
            f"需要MFA验证(已跳过) {results['mfa_users']}"
        )
        
        # 详细日志
        if results['success_users'] > 0:
            logger.info(f"   ✓ 成功同步: {results['success_users']} 个用户")
        if results['failed_users'] > 0:
            logger.warning(f"   ✗ 同步失败: {results['failed_users']} 个用户")
        if results['mfa_users'] > 0:
            logger.info(f"   🔐 需要MFA(已跳过): {results['mfa_users']} 个用户")
        
    except Exception as e:
        logger.error(f"全部用户同步过程中出现错误: {str(e)}", exc_info=True)
    finally:
        db.close()
    
    return results


def get_seconds_until_next_sync(target_hour: int = 8, target_minute: int = 1) -> int:
    """
    计算到下一个指定时间（北京时间）的秒数
    
    Args:
        target_hour: 目标小时（0-23），默认8点
        target_minute: 目标分钟（0-59），默认1分
    
    Returns:
        到下一个目标时间的秒数
    """
    now = get_china_now()
    
    # 构造今天的目标时间
    target_today = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # 如果今天的目标时间已过，则计算到明天的目标时间
    if now >= target_today:
        target_time = target_today + timedelta(days=1)
    else:
        target_time = target_today
    
    # 计算差值（秒）
    delta = target_time - now
    return int(delta.total_seconds())


async def scheduler_loop_daily(target_hour: int = 8, target_minute: int = 1):
    """
    每日定时任务调度器 - 每天在指定时间（北京时间）执行一次同步
    
    Args:
        target_hour: 同步执行的小时（0-23），默认8点
        target_minute: 同步执行的分钟（0-59），默认1分
    
    注意：每天只同步一次，避免频繁登录导致Garmin账户被锁定
    """
    logger.info(f"🚀 Garmin 每日定时同步调度器已启动")
    logger.info(f"⏰ 每日同步时间: {target_hour:02d}:{target_minute:02d} (北京时间)")
    logger.info(f"🔐 重要: 需要MFA验证的用户将被自动跳过，不会触发自动同步")
    logger.info(f"⚠️  为避免Garmin账户被锁定，系统每天只自动同步一次")
    
    while True:
        # 计算到下一次同步的等待时间
        wait_seconds = get_seconds_until_next_sync(target_hour, target_minute)
        next_sync_time = get_china_now() + timedelta(seconds=wait_seconds)
        
        logger.info(f"⏳ 下一次同步将在 {next_sync_time.strftime('%Y-%m-%d %H:%M:%S')} (北京时间) 执行")
        logger.info(f"   距离下次同步还有: {wait_seconds // 3600}小时{(wait_seconds % 3600) // 60}分钟")
        
        # 等待到目标时间
        await asyncio.sleep(wait_seconds)
        
        # 执行同步任务
        try:
            logger.info(f"🕐 到达定时同步时间: {get_china_now().strftime('%Y-%m-%d %H:%M:%S')}")
            await sync_all_users_garmin_task(days=1)  # 每天只同步1天的数据
        except Exception as e:
            logger.error(f"定时同步任务出错: {e}", exc_info=True)
        
        # 短暂等待，避免在同一分钟内重复触发
        await asyncio.sleep(60)


async def scheduler_loop(interval_minutes: int = 60):
    """
    [已弃用] 间隔同步调度器 - 可能导致账户锁定，请使用 scheduler_loop_daily
    
    Args:
        interval_minutes: 同步间隔（分钟），默认60分钟
    """
    logger.warning("⚠️ 使用间隔同步模式，频繁登录可能导致Garmin账户被锁定！")
    logger.warning("⚠️ 建议使用 scheduler_loop_daily 进行每日定时同步")
    logger.info(f"🚀 Garmin 后台同步调度器已启动")
    logger.info(f"⏰ 同步间隔: {interval_minutes} 分钟")
    logger.info(f"🔐 重要: 需要MFA验证的用户将被自动跳过，不会触发自动同步")
    
    # 第一次运行前先等待2分钟，确保系统完全启动
    logger.info(f"⏳ 等待 2 分钟以确保系统完全启动...")
    await asyncio.sleep(120)
    logger.info(f"✅ 系统启动完成，开始第一次同步任务")
    
    while True:
        try:
            await sync_all_users_garmin_task(days=3)
        except Exception as e:
            logger.error(f"调度器循环出错: {e}")
        
        logger.info(f"下一次同步将在 {interval_minutes} 分钟后执行")
        await asyncio.sleep(interval_minutes * 60)


def start_scheduler(app, interval_minutes: int = 60, use_daily_schedule: bool = True):
    """
    在后台线程中启动异步调度器
    
    Args:
        app: FastAPI应用实例
        interval_minutes: 同步间隔（分钟），仅在 use_daily_schedule=False 时有效
        use_daily_schedule: 是否使用每日定时同步（默认True，每天08:01同步一次）
    """
    def run_async_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if use_daily_schedule:
            # 使用每日定时同步（默认08:01），避免账户锁定
            loop.run_until_complete(scheduler_loop_daily(target_hour=8, target_minute=1))
        else:
            # 使用间隔同步（不推荐，可能导致账户锁定）
            loop.run_until_complete(scheduler_loop(interval_minutes))
        loop.close()

    # 使用守护线程，确保主程序退出时线程也退出
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()
    
    if use_daily_schedule:
        logger.info("✅ 后台每日定时同步调度器线程已启动（每天08:01北京时间执行）")
    else:
        logger.info(f"⚠️ 后台间隔同步调度器线程已启动（每{interval_minutes}分钟执行）")
    
    return thread
