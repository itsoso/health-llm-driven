"""后台任务调度器 - 自动同步所有用户的Garmin数据

优化措施（防止账户锁定）：
1. OAuth令牌缓存 - 复用已登录的会话，避免每次都重新登录
2. 用户间随机延迟 - 避免同一时间大量请求
3. 指数退避重试 - 遇到限流时智能等待
4. 账户状态监控 - 检测到锁定风险时自动暂停
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta, date
from typing import List, Dict, Any
from app.services.data_collection.garmin_connect import GarminConnectService, GarminAuthenticationError, probe_sso_availability
from app.services.data_collection.garmin_native_auth import has_native_token_store
from app.services.auth import garmin_credential_service
from app.services.garmin_session_manager import get_session_manager, AccountStatus
from app.models.user import GarminCredential
from app.database import SessionLocal
from app.utils.timezone import get_china_today, get_china_now
import threading

logger = logging.getLogger(__name__)

# 获取全局会话管理器
session_manager = get_session_manager()


def _update_vo2max_from_workouts(db, user_id: int, days: int = 30):
    """
    从运动记录中提取最新的 VO2Max 并更新到每日健康数据

    VO2Max 通常来自跑步活动，Garmin 会在每次跑步后更新这个值
    """
    from app.models.daily_health import WorkoutRecord, GarminData

    try:
        end_date = get_china_today()
        start_date = end_date - timedelta(days=days)

        # 查找最近有 VO2Max 数据的跑步记录（workout_type 映射后是 'running'）
        workout_with_vo2max = db.query(WorkoutRecord).filter(
            WorkoutRecord.user_id == user_id,
            WorkoutRecord.workout_date >= start_date,
            WorkoutRecord.vo2max.isnot(None)
        ).order_by(WorkoutRecord.workout_date.desc()).first()

        if workout_with_vo2max and workout_with_vo2max.vo2max:
            latest_vo2max = workout_with_vo2max.vo2max
            logger.info(f"用户 {user_id} 从运动记录 (类型: {workout_with_vo2max.workout_type}, 日期: {workout_with_vo2max.workout_date}) 获取到 VO2Max: {latest_vo2max}")

            # 更新最近的 Garmin 每日数据
            garmin_records = db.query(GarminData).filter(
                GarminData.user_id == user_id,
                GarminData.record_date >= start_date
            ).all()

            updated_count = 0
            for record in garmin_records:
                # 无论是否有值，都更新为最新的 VO2Max
                if record.vo2max_running != latest_vo2max:
                    record.vo2max_running = latest_vo2max
                    updated_count += 1

            if updated_count > 0:
                db.commit()
                logger.info(f"用户 {user_id} 更新了 {updated_count} 条 Garmin 记录的 VO2Max 为 {latest_vo2max}")
        else:
            logger.info(f"用户 {user_id} 最近 {days} 天没有找到包含 VO2Max 的运动记录")
    except Exception as e:
        import traceback
        logger.warning(f"用户 {user_id} 更新 VO2Max 失败: {e}")
        logger.debug(traceback.format_exc())


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
            logger.error("❌ 解密用户 %s 的Garmin凭证失败 (%s): %r", cred.user_id, type(e).__name__, e, exc_info=True)

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

    # 1. 检查账户状态（内存级保护机制）
    can_sync, reason = session_manager.can_sync(user_id, email)
    if not can_sync:
        result["skipped"] = True
        result["message"] = f"跳过同步: {reason}"
        logger.warning(f"⏸️ 用户 {user_id} 跳过同步: {reason}")
        return result

    # 1b. 检查 DB 登录锁定（仅在没有缓存 session 时才阻止同步）
    _was_previously_locked = False
    try:
        cred = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
        if cred and cred.login_locked_until:
            now = datetime.now(UTC).replace(tzinfo=None)
            locked_until = cred.login_locked_until
            if locked_until.tzinfo is not None:
                locked_until = locked_until.replace(tzinfo=None)
            if locked_until > now:
                # 有缓存 session 时，忽略锁定继续同步（锁定仅防止 SSO 登录）
                has_valid_session = has_native_token_store(cred.garth_session)
                if has_valid_session:
                    logger.info(f"🔓 用户 {user_id} 虽被锁定但有有效 session，继续同步")
                else:
                    remaining = int((locked_until - now).total_seconds() / 60) + 1
                    result["skipped"] = True
                    result["message"] = f"跳过同步: 登录锁定中，剩余 {remaining} 分钟"
                    logger.warning(f"⏸️ 用户 {user_id} 跳过同步: DB 登录锁定到 {cred.login_locked_until}")
                    return result
            else:
                _was_previously_locked = True
                logger.info(f"🔓 用户 {user_id} DB 登录锁定已到期，将探测 SSO 可用性")
    except Exception as e:
        logger.warning(f"检查用户 {user_id} DB 登录锁定失败: {e}")

    # 1b-probe. 锁定刚到期时，先探测 SSO 是否仍在限流
    if _was_previously_locked:
        if not probe_sso_availability(is_cn=is_cn):
            # SSO 仍在限流，重新锁定但不增加 error_count
            try:
                cred = db.query(GarminCredential).filter(GarminCredential.user_id == user_id).first()
                if cred:
                    # 使用当前 error_count 计算下一次锁定时长（不递增 error_count）
                    from app.services.data_collection.garmin_connect import LOGIN_LOCK_MINUTES_SCHEDULE
                    lock_index = min((cred.error_count or 1) - 1, len(LOGIN_LOCK_MINUTES_SCHEDULE) - 1)
                    lock_minutes = LOGIN_LOCK_MINUTES_SCHEDULE[max(lock_index, 0)]
                    lock_until = datetime.now(UTC) + timedelta(minutes=lock_minutes)
                    cred.login_locked_until = lock_until
                    db.commit()
                    logger.warning(
                        f"⏸️ 用户 {user_id} SSO 探测仍返回 429，"
                        f"重新锁定 {lock_minutes} 分钟到 {lock_until}（不增加 error_count）"
                    )
            except Exception as e:
                logger.warning(f"用户 {user_id} 更新探测锁定状态失败: {e}")

            result["skipped"] = True
            result["message"] = "跳过同步: SSO 探测仍在限流，已重新锁定"
            return result
        else:
            logger.info(f"✅ 用户 {user_id} SSO 探测通过，继续正常同步")

    # 1c. 获取同步锁（防止多入口并发同步同一用户）
    from app.services.sync_lock import acquire_sync_lock, release_sync_lock
    if not acquire_sync_lock(db, user_id):
        result["skipped"] = True
        result["message"] = "跳过同步: 另一个同步正在进行中"
        logger.warning(f"⏸️ 用户 {user_id} 跳过同步: 同步去重")
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

        # 同步运动活动数据（复用已认证的 client，避免重复登录触发限流）
        try:
            from app.services.workout_sync import WorkoutSyncService
            workout_client = service.client if hasattr(service, 'client') and service._authenticated else None
            workout_sync_service = WorkoutSyncService(
                email=email,
                password=password,
                is_cn=is_cn,
                user_id=user_id,
                client=workout_client
            )
            workout_result = await workout_sync_service.sync_activities(db, user_id, days)
            result["activities_count"] = workout_result.get("synced_count", 0)
            logger.info(f"用户 {user_id} 运动活动同步完成: {result['activities_count']} 条")

            # 从运动记录中提取最新的 VO2Max 并更新到每日数据
            _update_vo2max_from_workouts(db, user_id, days)
        except Exception as e:
            logger.warning(f"用户 {user_id} 运动活动同步失败: {e}", exc_info=True)
            result["activities_error"] = str(e)

        result["message"] = f"同步完成: 健康数据 {result['success_count']} 天"
        if result["activities_count"] > 0:
            result["message"] += f", 运动活动 {result['activities_count']} 条"
        if result["error_count"] > 0:
            result["message"] += f", 失败 {result['error_count']} 天"

        # 更新最后同步时间（会重置错误状态）
        garmin_credential_service.update_sync_status(db, user_id)

        # 4. 记录成功
        session_manager.record_success(user_id, email)

        # 如果是从锁定状态恢复的，记录恢复日志
        if _was_previously_locked:
            logger.info(f"🔓✅ 用户 {user_id} 从限流锁定中恢复成功！error_count 已重置为 0")

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
            release_sync_lock(db, user_id)
            return await sync_user_garmin_data(
                db, user_id, email, password, days, is_cn, retry_count + 1
            )
    finally:
        release_sync_lock(db, user_id)

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


async def reminder_check_loop():
    """每分钟检查到期提醒并触发通知"""
    logger.info("Smart Reminder 调度器已启动，每60秒检查一次")
    # 等待系统启动
    await asyncio.sleep(30)

    while True:
        try:
            db = SessionLocal()
            try:
                from app.services.reminder_service import ReminderService
                service = ReminderService(db)
                fired = await service.fire_all_due()
                if fired > 0:
                    logger.info(f"本轮触发了 {fired} 个提醒")
                # 顺便清理过期提醒
                service.expire_old_reminders()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"提醒调度器出错: {e}")

        await asyncio.sleep(60)


async def skill_metrics_aggregation_loop():
    """每天凌晨 02:05（北京时间）聚合前一天的 Skill 性能指标"""
    logger.info("Skill Metrics 每日聚合调度器已启动，每天 02:05 执行")
    await asyncio.sleep(60)  # 等待系统启动

    while True:
        wait_seconds = get_seconds_until_next_sync(2, 5)
        await asyncio.sleep(wait_seconds)

        try:
            db = SessionLocal()
            try:
                from app.services.feedback_service import feedback_service
                feedback_service.aggregate_daily_metrics(db)
                logger.info("Skill Metrics 每日聚合完成")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Skill Metrics 聚合出错: {e}", exc_info=True)

        await asyncio.sleep(60)  # 避免同一分钟重复触发


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
            loop.run_until_complete(scheduler_loop_daily(target_hour=9, target_minute=2))
        else:
            # 使用间隔同步（不推荐，可能导致账户锁定）
            loop.run_until_complete(scheduler_loop(interval_minutes))
        loop.close()

    # 使用守护线程，确保主程序退出时线程也退出
    thread = threading.Thread(target=run_async_loop, daemon=True)
    thread.start()

    if use_daily_schedule:
        logger.info("后台每日定时同步调度器线程已启动（每天09:02北京时间执行）")
    else:
        logger.info(f"后台间隔同步调度器线程已启动（每{interval_minutes}分钟执行）")

    # 启动提醒调度器（独立线程）
    def run_reminder_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(reminder_check_loop())
        loop.close()

    reminder_thread = threading.Thread(target=run_reminder_loop, daemon=True)
    reminder_thread.start()
    logger.info("Smart Reminder 调度器线程已启动（每60秒检查）")

    # 启动 Skill Metrics 每日聚合调度器（凌晨 2:05 北京时间）
    def run_metrics_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(skill_metrics_aggregation_loop())
        loop.close()

    metrics_thread = threading.Thread(target=run_metrics_loop, daemon=True)
    metrics_thread.start()
    logger.info("Skill Metrics 每日聚合调度器线程已启动（每天02:05北京时间）")

    # 启动家庭每日健康巡检调度器（每天 08:30 北京时间）
    def run_family_check_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_family_daily_check_loop())
        loop.close()

    family_thread = threading.Thread(target=run_family_check_loop, daemon=True)
    family_thread.start()
    logger.info("家庭健康巡检调度器线程已启动（每天08:30北京时间）")

    # 启动家庭每周健康周报调度器（每周日 20:00 北京时间）
    def run_family_digest_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_family_weekly_digest_loop())
        loop.close()

    digest_thread = threading.Thread(target=run_family_digest_loop, daemon=True)
    digest_thread.start()
    logger.info("家庭周报调度器线程已启动（每周日20:00北京时间）")


async def _family_weekly_digest_loop():
    """每周日 20:00 北京时间发送家庭健康周报"""
    while True:
        try:
            now = get_china_now()
            # 找到下一个周日 20:00
            days_until_sunday = (6 - now.weekday()) % 7
            if days_until_sunday == 0 and now.hour >= 20:
                days_until_sunday = 7
            target = (now + timedelta(days=days_until_sunday)).replace(hour=20, minute=0, second=0, microsecond=0)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"家庭周报: 下次发送 {target.strftime('%Y-%m-%d %H:%M')}，等待 {wait_seconds/3600:.1f} 小时")
            await asyncio.sleep(wait_seconds)

            db = SessionLocal()
            try:
                from app.models.family import FamilyGroup
                from app.services.family_weekly_digest import send_weekly_digest
                owners = db.query(FamilyGroup.owner_id).distinct().all()
                for (owner_id,) in owners:
                    try:
                        await send_weekly_digest(db, owner_id)
                        logger.info(f"家庭周报已发送: owner_id={owner_id}")
                    except Exception as e:
                        logger.warning(f"家庭周报发送失败 owner_id={owner_id}: {e}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"家庭周报调度异常: {e}", exc_info=True)
            await asyncio.sleep(60)


async def _family_daily_check_loop():
    """每天 08:30 北京时间执行家庭健康巡检"""
    while True:
        try:
            now = get_china_now()
            target = now.replace(hour=8, minute=30, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_seconds = (target - now).total_seconds()
            logger.info(f"家庭巡检: 下次执行 {target.strftime('%Y-%m-%d %H:%M')}，等待 {wait_seconds/3600:.1f} 小时")
            await asyncio.sleep(wait_seconds)

            # 查找所有有家庭组的 owner
            db = SessionLocal()
            try:
                from app.models.family import FamilyGroup
                from app.services.family_daily_check import send_family_daily_brief
                owners = db.query(FamilyGroup.owner_id).distinct().all()
                for (owner_id,) in owners:
                    try:
                        await send_family_daily_brief(db, owner_id)
                        logger.info(f"家庭巡检完成: owner_id={owner_id}")
                    except Exception as e:
                        logger.warning(f"家庭巡检失败 owner_id={owner_id}: {e}")
            finally:
                db.close()

        except Exception as e:
            logger.error(f"家庭巡检调度异常: {e}", exc_info=True)
            await asyncio.sleep(60)
