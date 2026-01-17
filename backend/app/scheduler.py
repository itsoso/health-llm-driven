"""后台任务调度器 - 自动同步所有用户的Garmin数据

优化措施（防止账户锁定）：
1. OAuth令牌缓存 - 复用已登录的会话，避免每次都重新登录
2. 用户间随机延迟 - 避免同一时间大量请求
3. 指数退避重试 - 遇到限流时智能等待
4. 账户状态监控 - 检测到锁定风险时自动暂停
"""
import asyncio
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Any
from app.services.data_collection.garmin_connect import GarminConnectService, GarminAuthenticationError
from app.services.auth import garmin_credential_service
from app.services.garmin_session_manager import get_session_manager, AccountStatus
from app.models.user import GarminCredential
from app.database import SessionLocal
from app.utils.timezone import get_china_today, get_china_now
import threading

logger = logging.getLogger(__name__)

# 获取全局会话管理器
session_manager = get_session_manager()


def _update_vo2max_from_workouts(db, user_id: int, days: int = 7):
    """
    从运动记录中提取最新的 VO2Max 并更新到每日健康数据
    
    VO2Max 通常来自跑步活动，Garmin 会在每次跑步后更新这个值
    """
    from app.models.daily_health import WorkoutRecord, GarminDailyData
    from datetime import date, timedelta
    
    try:
        end_date = get_china_today()
        start_date = end_date - timedelta(days=days)
        
        # 查找最近有 VO2Max 数据的跑步记录
        workout_with_vo2max = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_date,
            WorkoutRecord.vo2max.isnot(None),
            WorkoutRecord.workout_type.in_(['running', 'trail_running', 'treadmill_running'])
        ).order_by(WorkoutRecord.workout_date.desc()).first()
        
        if workout_with_vo2max and workout_with_vo2max.vo2max:
            latest_vo2max = workout_with_vo2max.vo2max
            logger.info(f"用户 {user_id} 从跑步记录获取到 VO2Max: {latest_vo2max}")
            
            # 更新最近的 Garmin 每日数据（如果 vo2max_running 为空）
            garmin_records = db.query(GarminDailyData).filter(
                GarminDailyData.user_id == user_id,
                GarminDailyData.record_date >= start_date
            ).all()
            
            updated_count = 0
            for record in garmin_records:
                if record.vo2max_running is None:
                    record.vo2max_running = latest_vo2max
                    updated_count += 1
            
            if updated_count > 0:
                db.commit()
                logger.info(f"用户 {user_id} 更新了 {updated_count} 条 Garmin 记录的 VO2Max")
    except Exception as e:
        logger.warning(f"用户 {user_id} 更新 VO2Max 失败: {e}")


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
    is_cn: bool = False,
    retry_count: int = 0
) -> Dict[str, Any]:
    """
    同步单个用户的Garmin数据（包括健康数据和运动活动）
    
    集成会话管理器功能：
    - OAuth令牌缓存复用
    - 指数退避重试
    - 账户状态监控
    """
    result = {
        "user_id": user_id,
        "success": False,
        "success_count": 0,
        "error_count": 0,
        "activities_count": 0,
        "message": "",
        "is_auth_error": False,
        "requires_mfa": False,
        "skipped": False,  # 是否因保护机制被跳过
        "retried": retry_count  # 重试次数
    }
    
    # 1. 检查账户状态（账户保护机制）
    can_sync, reason = session_manager.can_sync(user_id, email)
    if not can_sync:
        result["skipped"] = True
        result["message"] = f"跳过同步: {reason}"
        logger.warning(f"⏸️ 用户 {user_id} 跳过同步: {reason}")
        return result
    
    try:
        server_type = "中国版" if is_cn else "国际版"
        
        # 2. 尝试复用缓存的会话（OAuth令牌缓存）
        cached_client = session_manager.get_cached_session(email)
        if cached_client:
            logger.info(f"♻️ 用户 {user_id} 复用缓存会话")
            service = GarminConnectService(email, password, is_cn=is_cn, user_id=user_id)
            service.client = cached_client
            service._authenticated = True
        else:
            logger.info(f"🔐 用户 {user_id} 创建新会话 ({server_type})")
            service = GarminConnectService(email, password, is_cn=is_cn, user_id=user_id)
        
        # 计算日期范围
        end_date = get_china_today()
        start_date = end_date - timedelta(days=days - 1)
        
        # 执行健康数据同步
        sync_result = service.sync_date_range(db, user_id, start_date, end_date)
        
        # 3. 缓存成功的会话
        if service.client and service._authenticated:
            session_manager.cache_session(email, service.client, is_cn)
        
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
            
            # 从运动记录中提取最新的 VO2Max 并更新到每日数据
            _update_vo2max_from_workouts(db, user_id, days)
        except Exception as e:
            logger.warning(f"用户 {user_id} 运动活动同步失败: {e}")
        
        result["message"] = f"同步完成: 健康数据 {result['success_count']} 天"
        if result["activities_count"] > 0:
            result["message"] += f", 运动活动 {result['activities_count']} 条"
        if result["error_count"] > 0:
            result["message"] += f", 失败 {result['error_count']} 天"
        
        # 更新最后同步时间（会重置错误状态）
        garmin_credential_service.update_sync_status(db, user_id)
        
        # 4. 记录成功
        session_manager.record_success(user_id, email)
        
        logger.info(f"✅ 用户 {user_id} Garmin数据同步成功: {result['message']}")
        
    except GarminAuthenticationError as e:
        # 明确的认证错误
        error_message = str(e)
        result["message"] = error_message
        result["is_auth_error"] = True
        
        # 记录错误并检查是否应该重试
        should_retry, retry_delay = session_manager.record_error(user_id, email, error_message)
        
        # 更新错误状态，标记凭证无效
        garmin_credential_service.update_sync_error(db, user_id, error_message, is_auth_error=True)
        logger.warning(f"🔑 用户 {user_id} Garmin认证失败: {error_message}")
        
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
            logger.info(f"🔐 用户 {user_id} 需要MFA两步验证，跳过后台自动同步")
            return result
        
        # 5. 记录错误并检查是否应该重试（指数退避）
        should_retry, retry_delay = session_manager.record_error(user_id, email, error_message)
        
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
            logger.warning(f"🔑 用户 {user_id} Garmin认证失败: {error_message}")
        else:
            logger.error(f"❌ 用户 {user_id} Garmin数据同步失败: {e}")
        
        # 6. 指数退避重试
        if should_retry and retry_delay > 0:
            logger.info(f"⏳ 用户 {user_id} 将在 {retry_delay} 秒后重试 (第 {retry_count + 1} 次)")
            await asyncio.sleep(retry_delay)
            # 清除缓存的会话，强制重新登录
            session_manager.invalidate_session(email)
            return await sync_user_garmin_data(
                db, user_id, email, password, days, is_cn, retry_count + 1
            )
    
    return result


async def sync_all_users_garmin_task(days: int = 3) -> Dict[str, Any]:
    """
    同步所有启用同步的用户的Garmin数据
    
    集成会话管理器功能：
    - 用户间随机延迟（分散请求）
    - 账户状态检查（跳过风险账户）
    - 同步结束后清理过期会话
    """
    logger.info(f"🚀 开始执行全部用户 Garmin 数据同步任务: {get_china_now()}")
    logger.info(f"📅 同步天数: {days} 天")
    
    # 打印会话管理器状态
    stats = session_manager.get_stats()
    logger.info(f"📊 会话管理器状态: 缓存会话={stats['cached_sessions']}, 监控账户={stats['monitored_accounts']}")
    
    db = SessionLocal()
    results = {
        "total_users": 0,
        "success_users": 0,
        "failed_users": 0,
        "mfa_users": 0,
        "skipped_users": 0,  # 因保护机制被跳过的用户
        "retried_count": 0,  # 总重试次数
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
        logger.info(f"⏱️ 用户间延迟: {session_manager.MIN_DELAY_SECONDS}-{session_manager.MAX_DELAY_SECONDS} 秒随机")
        
        for idx, user_info in enumerate(users, 1):
            logger.info(f"📌 [{idx}/{len(users)}] 开始同步用户 {user_info['user_id']} ({user_info['email']})")
        
        # 逐个同步用户数据
        for idx, user_info in enumerate(users):
            user_result = await sync_user_garmin_data(
                db,
                user_info["user_id"],
                user_info["email"],
                user_info["password"],
                days,
                is_cn=user_info.get("is_cn", False)
            )
            
            results["details"].append(user_result)
            results["retried_count"] += user_result.get("retried", 0)
            
            if user_result.get("skipped"):
                results["skipped_users"] += 1
            elif user_result["success"]:
                results["success_users"] += 1
            elif user_result.get("requires_mfa"):
                results["mfa_users"] += 1
            else:
                results["failed_users"] += 1
            
            # 用户间随机延迟（最后一个用户不需要延迟）
            if idx < len(users) - 1:
                delay = await session_manager.get_random_delay()
                logger.debug(f"⏳ 下一个用户延迟 {delay:.1f} 秒")
                await asyncio.sleep(delay)
        
        # 清理过期会话
        session_manager.cleanup_expired()
        
        logger.info(
            f"✅ 全部用户同步完成: 总计 {results['total_users']} 用户, "
            f"成功 {results['success_users']}, 失败 {results['failed_users']}, "
            f"跳过(保护) {results['skipped_users']}, MFA {results['mfa_users']}, "
            f"总重试 {results['retried_count']} 次"
        )
        
        # 详细日志
        if results['success_users'] > 0:
            logger.info(f"   ✓ 成功同步: {results['success_users']} 个用户")
        if results['failed_users'] > 0:
            logger.warning(f"   ✗ 同步失败: {results['failed_users']} 个用户")
        if results['skipped_users'] > 0:
            logger.info(f"   ⏸️ 跳过(保护): {results['skipped_users']} 个用户")
        if results['mfa_users'] > 0:
            logger.info(f"   🔐 需要MFA(已跳过): {results['mfa_users']} 个用户")
        
        # 打印最终会话状态
        final_stats = session_manager.get_stats()
        logger.info(f"📊 同步后会话状态: 缓存会话={final_stats['cached_sessions']}")
        if final_stats['accounts_by_status'].get('rate_limited', 0) > 0:
            logger.warning(f"   ⚠️ 被限流账户: {final_stats['accounts_by_status']['rate_limited']}")
        if final_stats['accounts_by_status'].get('locked', 0) > 0:
            logger.warning(f"   🔒 被锁定账户: {final_stats['accounts_by_status']['locked']}")
        
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
    
    集成会话管理器功能：
    - OAuth令牌缓存复用
    - 用户间随机延迟
    - 指数退避重试
    - 账户状态监控
    
    注意：每天只同步一次，避免频繁登录导致Garmin账户被锁定
    """
    logger.info(f"🚀 Garmin 每日定时同步调度器已启动")
    logger.info(f"⏰ 每日同步时间: {target_hour:02d}:{target_minute:02d} (北京时间)")
    logger.info(f"🛡️ 账户保护机制已启用:")
    logger.info(f"   - OAuth令牌缓存: 会话有效期 {session_manager.SESSION_TTL_HOURS} 小时")
    logger.info(f"   - 用户间延迟: {session_manager.MIN_DELAY_SECONDS}-{session_manager.MAX_DELAY_SECONDS} 秒随机")
    logger.info(f"   - 指数退避重试: 最多 {session_manager.MAX_RETRIES} 次，最大延迟 {session_manager.MAX_RETRY_DELAY} 秒")
    logger.info(f"   - 每日请求限制: {session_manager.MAX_REQUESTS_PER_DAY} 次/账户")
    logger.info(f"   - 限流暂停: {session_manager.RATE_LIMIT_DURATION_HOURS} 小时")
    logger.info(f"   - 锁定暂停: {session_manager.LOCK_DURATION_HOURS} 小时")
    logger.info(f"🔐 需要MFA验证的用户将被自动跳过")
    
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
