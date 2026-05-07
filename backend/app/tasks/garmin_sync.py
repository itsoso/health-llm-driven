"""
Garmin 数据同步任务
"""
import asyncio
import json
import logging
import os
import tempfile
from datetime import UTC, date, datetime, timedelta
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.daily_health import WorkoutRecord, WorkoutAnalysisResult

logger = logging.getLogger(__name__)


# 教练文案 helper 已抽到 services.workout_coach_copy.
# 保留别名以兼容既有 tests/test_workout_push_copy.py.
from app.services.workout_coach_copy import (
    coach_oneliner as _coach_oneliner,
    first_paragraph as _first_paragraph,
)


@celery_app.task(bind=True, max_retries=3)
def sync_user_garmin_data(self, user_id: int, days: int = 1):
    """
    同步单个用户的 Garmin 数据（健康数据 + 运动活动）
    """
    logger.info(f"开始同步用户 {user_id} 的 Garmin 数据 (最近 {days} 天)")

    try:
        with SessionLocal() as db:
            # 使用 GarminCredential 获取凭据（与 scheduler/auth 保持一致）
            from app.models.user import GarminCredential
            from app.services.auth import garmin_credential_service

            credential = db.query(GarminCredential).filter(
                GarminCredential.user_id == user_id,
                GarminCredential.sync_enabled == True,
                GarminCredential.credentials_valid == True
            ).first()

            if not credential:
                logger.warning(f"用户 {user_id} 没有有效的 Garmin 凭据")
                return {"status": "skipped", "reason": "no_credentials"}

            # 解密密码
            try:
                password = garmin_credential_service.decrypt_password(credential.encrypted_password)
            except Exception as e:
                logger.error(f"用户 {user_id} Garmin 凭据解密失败: {e}")
                return {"status": "error", "reason": "decrypt_failed"}

            email = credential.garmin_email
            is_cn = credential.is_cn if hasattr(credential, 'is_cn') else True

            # 创建服务并同步健康数据
            from app.services.data_collection.garmin_connect import GarminConnectService

            service = GarminConnectService(
                email=email,
                password=password,
                is_cn=is_cn,
                user_id=user_id
            )

            from app.utils.timezone import get_china_today
            end_date = get_china_today()
            start_date = end_date - timedelta(days=days - 1)
            sync_result = service.sync_date_range(db, user_id, start_date, end_date)

            success_count = sync_result.get("success_count", 0)
            error_count = sync_result.get("error_count", 0)
            logger.info(f"用户 {user_id} 健康数据同步完成: 成功 {success_count} 天, 失败 {error_count} 天")

            # 同步运动活动数据（复用已认证的 client）
            synced_activities = 0
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

                # 单次 event loop 完成所有 async 操作
                async def _async_sync():
                    return await workout_sync_service.sync_activities(db, user_id, days)

                workout_result = asyncio.run(_async_sync())
                synced_activities = workout_result.get("synced_count", 0)
                logger.info(f"用户 {user_id} 运动活动同步完成: {synced_activities} 条")

                # 从运动记录中提取 VO2Max 更新到每日数据
                try:
                    from app.scheduler import _update_vo2max_from_workouts
                    _update_vo2max_from_workouts(db, user_id, days)
                except Exception as e:
                    logger.warning(f"用户 {user_id} VO2Max 更新失败: {e}")
            except Exception as e:
                logger.warning(f"用户 {user_id} 运动活动同步失败: {e}", exc_info=True)

            # 检测新同步的运动并触发自动分析
            try:
                twelve_hours_ago = datetime.now(UTC) - timedelta(hours=12)
                analyzed_workout_ids = {
                    r.workout_id for r in db.query(WorkoutAnalysisResult.workout_id).filter(
                        WorkoutAnalysisResult.user_id == user_id
                    ).all()
                }
                new_workouts_query = db.query(WorkoutRecord).filter(
                    WorkoutRecord.user_id == user_id,
                    WorkoutRecord.created_at >= twelve_hours_ago,
                )
                if analyzed_workout_ids:
                    new_workouts_query = new_workouts_query.filter(
                        ~WorkoutRecord.id.in_(analyzed_workout_ids)
                    )
                new_workouts = new_workouts_query.all()
                for w in new_workouts:
                    logger.info(f"触发自动分析: user={user_id} workout={w.id} ({w.workout_type})")
                    auto_analyze_workout.delay(user_id, w.id)
            except Exception as e:
                logger.warning(f"检测新运动触发分析失败: {e}")

            # 触发健康异常检测（含趋势检测器）
            alerts = []
            try:
                from app.services.anomaly_detection_service import AnomalyDetectionService
                anomaly_svc = AnomalyDetectionService(db)
                alerts = anomaly_svc.detect_anomalies(user_id)
                if alerts:
                    logger.info(f"用户 {user_id} 检测到 {len(alerts)} 个健康异常")

                    async def _send_alerts():
                        await anomaly_svc.send_alerts(user_id, alerts)

                    asyncio.run(_send_alerts())
            except Exception as e:
                logger.warning(f"健康异常检测失败: {e}")

            # 构建 Twin + Safety 评估（Agent Loop 和 Safety 推送共用）
            twin = None
            safety_report = None
            try:
                from app.twin.builder import build_twin
                from app.agents.safety_guardian import evaluate_safety
                twin = build_twin(db, user_id, use_cache=False)
                safety_report = evaluate_safety(twin)
            except Exception as e:
                logger.warning(f"Post-sync Twin/Safety 构建失败: {e}")

            # Safety Guardian 推送 critical 告警（仅在 anomaly 无告警时）
            if not alerts and safety_report:
                try:
                    critical_alerts = [a for a in safety_report.alerts if int(a.severity) >= 3]
                    if critical_alerts:
                        from app.services.notification.push_service import PushService
                        push_svc = PushService(db)
                        for sa in critical_alerts[:3]:
                            async def _push_safety(alert=sa):
                                await push_svc.send_notification(
                                    user_id=user_id,
                                    notification_type="health_alert",
                                    title=f"[{alert.severity.label_zh}] {alert.title}",
                                    content=alert.message,
                                    # 用户反馈 (2026-05-07): 凌晨 1 点推 3 条同样 SpO2 告警 — 两个 bug:
                                    # 1) 缺 data={"rule_id":...} 导致 push_service rule-id 去重失效, 同 rule 反复推
                                    # 2) respect_quiet_hours=False 直接穿透免打扰, SpO2 异常并非急救场景, 可等天亮
                                    data={"rule_id": alert.rule_id},
                                    respect_quiet_hours=True,
                                )
                            asyncio.run(_push_safety())
                        logger.info(f"用户 {user_id} Safety Guardian 发现 {len(critical_alerts)} 条 critical 告警，已推送")
                except Exception as e:
                    logger.warning(f"Safety Guardian 推送失败: {e}")

            # Agent Planning Loop（自主推理，决定是否主动干预）
            if twin:
                try:
                    from app.services.agent_loop import post_sync_reasoning

                    async def _agent_loop():
                        return await post_sync_reasoning(db, user_id, twin, alerts, safety_report)

                    loop_result = asyncio.run(_agent_loop())
                    if loop_result.get("action") == "notify":
                        logger.info(f"用户 {user_id} Agent Loop 主动推送: {loop_result.get('title')}")
                    else:
                        logger.debug(f"用户 {user_id} Agent Loop: {loop_result.get('action')}")
                except Exception as e:
                    logger.warning(f"Agent Planning Loop 失败（不影响同步）: {e}")

            # 更新同步状态
            garmin_credential_service.update_sync_status(db, user_id)

            # 同步完成后重新生成今日简报（确保简报包含最新数据）
            try:
                from app.tasks.notifications import regenerate_briefing_for_user
                regenerate_briefing_for_user.delay(user_id)
                logger.info(f"用户 {user_id} Garmin 同步完成，已触发简报重新生成")
            except Exception as e:
                logger.warning(f"触发简报重新生成失败（不影响同步结果）: {e}")

            return {
                "status": "success",
                "success_count": success_count,
                "error_count": error_count,
                "activities_count": synced_activities
            }

    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}", exc_info=True)
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task
def sync_all_users_garmin():
    """
    同步所有用户的 Garmin 数据（定时任务，每 4 小时运行）
    如果用户 3 小时内已同步过，则跳过（避免 Garmin API 限流）。
    """
    from app.utils.timezone import get_china_now

    logger.info("开始批量同步所有用户 Garmin 数据")
    now = get_china_now()
    min_interval = timedelta(hours=1, minutes=30)

    with SessionLocal() as db:
        from app.models.user import GarminCredential

        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.credentials_valid == True
        ).all()

        dispatched = []
        skipped = []
        for c in credentials:
            # 如果 3 小时内已同步过，跳过
            if c.last_sync_at and (now - c.last_sync_at.replace(tzinfo=now.tzinfo) if c.last_sync_at.tzinfo is None else now - c.last_sync_at) < min_interval:
                skipped.append(c.user_id)
                logger.info(f"用户 {c.user_id} 近期已同步({c.last_sync_at})，跳过")
            else:
                dispatched.append(c.user_id)

    logger.info(f"发现 {len(dispatched) + len(skipped)} 个活跃账户，派发 {len(dispatched)} 个，跳过 {len(skipped)} 个")

    for user_id in dispatched:
        sync_user_garmin_data.delay(user_id)

    return {"status": "dispatched", "count": len(dispatched), "skipped": len(skipped)}


@celery_app.task(bind=True, max_retries=2, time_limit=300)
def auto_analyze_workout(self, user_id: int, workout_id: int):
    """
    自动分析单次运动（Garmin 同步后触发）
    """
    logger.info(f"[自动分析] 开始: user={user_id} workout={workout_id}")

    try:
        with SessionLocal() as db:
            # 检查是否已有分析结果
            existing = db.query(WorkoutAnalysisResult).filter(
                WorkoutAnalysisResult.workout_id == workout_id
            ).first()
            if existing:
                logger.info(f"[自动分析] 跳过已分析的运动 {workout_id}")
                return {"status": "skipped", "reason": "already_analyzed"}

            workout = db.query(WorkoutRecord).filter(
                WorkoutRecord.id == workout_id,
                WorkoutRecord.user_id == user_id
            ).first()
            if not workout:
                logger.warning(f"[自动分析] 运动记录不存在: {workout_id}")
                return {"status": "skipped", "reason": "not_found"}

            # 使用 PostRunAnalyzeService 的内部方法
            from app.services.post_run_analyze import PostRunAnalyzeService
            service = PostRunAnalyzeService(db)
            workout_data = service._build_workout_data(workout)
            prompt = service._build_prompt(user_id, workout, workout_data)

            # 单次 event loop 完成分析 + 推送通知
            async def _analyze_and_notify():
                result = await service.openclaw.analyze(prompt)
                service._save_analysis_result(user_id, workout_id, prompt, result)

                # 构造推送: 标题用运动类型 + 一行概况, 正文取 aggregation 的第一段 (跳过 markdown 标题行).
                # 运动名走 WorkoutAnalysisService 的中文映射, 保持 push 和 app 内展示一致.
                from app.services.workout_analysis import WorkoutAnalysisService
                _wa = WorkoutAnalysisService()
                activity = _wa._get_workout_type_name(workout.workout_type or "other")
                summary_bits = []
                if workout.distance_meters:
                    summary_bits.append(f"{workout.distance_meters / 1000:.1f}km")
                if workout.duration_seconds:
                    summary_bits.append(f"{workout.duration_seconds // 60}分钟")
                summary = " · ".join(summary_bits)
                title = f"跑后教练: {activity}" + (f" ({summary})" if summary else "")

                body = _coach_oneliner(result.get("aggregation") or "")
                if not body:
                    body = "你的运动数据已分析完成，点击查看详情"

                try:
                    from app.services.notification.push_service import PushService
                    push_svc = PushService(db)
                    await push_svc.send_notification(
                        user_id=user_id,
                        notification_type="workout_analysis",
                        title=title,
                        content=body,
                        data={
                            # 点推送跳 workout-detail (deep_link 已在 mobile/hooks/useNotifications.ts 处理)
                            "deep_link": f"/workout-detail?id={workout_id}",
                            # rule_id 保证同一 workout 只推一次 — 避免重试/重新分析重复推送
                            "rule_id": f"workout_{workout_id}",
                            "kind": "workout_analysis",
                            "workout_id": workout_id,
                        },
                        # 7 天窗口内同一 workout_id 不重推
                        dedup_window_hours=168,
                    )
                except Exception as push_err:
                    logger.warning(f"[自动分析] 推送通知失败: {push_err}")
                return result

            analysis = asyncio.run(_analyze_and_notify())

            logger.info(f"[自动分析] 完成: user={user_id} workout={workout_id} status={analysis.get('status')}")
            return {"status": "success", "workout_id": workout_id}

    except Exception as e:
        logger.error(f"[自动分析] 失败: user={user_id} workout={workout_id} error={e}")
        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=1, time_limit=600)
def renew_garmin_sessions(self):
    """
    续期所有用户的 Garmin OAuth session（每 12 小时运行一次）

    改为分派子任务：每个用户一个 renew_single_garmin_session task，
    用 countdown 错开 30 秒，避免阻塞 worker。
    """
    logger.info("[session-renew] 开始分派续期任务")

    from app.models.user import GarminCredential

    with SessionLocal() as db:
        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
            GarminCredential.garth_session.isnot(None),
        ).all()
        user_ids = [c.user_id for c in credentials]

    logger.info(f"[session-renew] 发现 {len(user_ids)} 个需要检查的 session，分派子任务")

    for i, user_id in enumerate(user_ids):
        renew_single_garmin_session.apply_async(
            args=[user_id],
            countdown=i * 30,  # 每个用户错开 30 秒
        )

    return {"dispatched": len(user_ids)}


@celery_app.task(bind=True, max_retries=1, time_limit=120)
def renew_single_garmin_session(self, user_id: int):
    """续期单个用户的 Garmin session（由 renew_garmin_sessions 分派）"""
    from app.models.user import GarminCredential

    prefix = f"[session-renew][user={user_id}]"

    with SessionLocal() as db:
        cred = db.query(GarminCredential).filter(
            GarminCredential.user_id == user_id,
            GarminCredential.sync_enabled == True,
            GarminCredential.garth_session.isnot(None),
        ).first()

        if not cred:
            logger.info(f"{prefix} 凭据不存在或已禁用，跳过")
            return {"status": "skipped"}

        try:
            result = _renew_single_session(db, cred, prefix)
            return {"status": result}
        except Exception as e:
            logger.error(f"{prefix} 续期异常: {e}", exc_info=True)
            return {"status": "failed", "error": str(e)}


def _renew_single_session(db, cred, prefix: str) -> str:
    """
    对单个用户尝试续期 session。

    Returns:
        "valid" - session 仍然有效
        "renewed" - 成功续期
        "failed" - 所有续期手段均失败
    """
    from app.models.user import GarminCredential
    from app.services.auth import garmin_credential_service

    user_id = cred.user_id

    # ---- Step 1: 加载 garth session 并尝试轻量 API 调用 ----
    try:
        import garth

        session_data = json.loads(cred.garth_session)
        client = garth.Client()

        if getattr(cred, "is_cn", False):
            client.configure(domain="garmin.cn")

        with tempfile.TemporaryDirectory() as tmpdir:
            for filename, data in session_data.items():
                filepath = os.path.join(tmpdir, filename)
                with open(filepath, "w") as f:
                    json.dump(data, f)
            client.load(tmpdir)

        # 尝试轻量 API 调用测试 session 有效性
        try:
            client.connectapi("/userprofile-service/userdisplayname")
            logger.info(f"{prefix} session 仍然有效")
            return "valid"
        except Exception as e:
            logger.info(f"{prefix} session 已失效 ({e})，尝试续期...")

    except Exception as e:
        logger.warning(f"{prefix} 加载 session 失败: {e}")
        client = None

    # ---- Step 2: 尝试 garth token refresh ----
    if client and hasattr(client, "oauth2_token") and client.oauth2_token:
        try:
            client.oauth2_token.refresh(
                client=client,
            )
            # 验证 refresh 后的 token
            client.connectapi("/userprofile-service/userdisplayname")
            logger.info(f"{prefix} garth token refresh 成功")

            # 保存续期后的 session
            _save_session_to_db(db, cred, client)
            return "renewed"
        except Exception as e:
            logger.warning(f"{prefix} garth token refresh 失败: {e}")

    # ---- Step 3: curl_cffi 最后手段 ----
    try:
        password = garmin_credential_service.decrypt_password(cred.encrypted_password)
    except Exception as e:
        logger.error(f"{prefix} 密码解密失败，无法尝试 cffi 登录: {e}")
        cred.last_error = f"密码解密失败: {e}"
        db.commit()
        return "failed"

    try:
        from app.services.garmin_cffi_login import cffi_login_and_get_session

        is_cn = getattr(cred, "is_cn", False)
        session_data = cffi_login_and_get_session(cred.garmin_email, password, is_cn=is_cn)

        cred.garth_session = json.dumps(session_data)
        cred.session_expires_at = datetime.now(UTC) + timedelta(hours=23)
        cred.login_locked_until = None
        cred.credentials_valid = True
        cred.last_error = None
        cred.error_count = 0
        db.commit()

        logger.info(f"{prefix} curl_cffi 重新登录成功，session 已更新")
        return "renewed"

    except ImportError:
        logger.warning(f"{prefix} curl_cffi 未安装，跳过最后手段登录")
        cred.last_error = "garth refresh 失败且 curl_cffi 未安装"
        db.commit()
        return "failed"
    except Exception as e:
        logger.error(f"{prefix} curl_cffi 登录失败: {e}")
        cred.last_error = f"session 续期失败: {e}"
        cred.error_count = (cred.error_count or 0) + 1
        db.commit()
        return "failed"


def _save_session_to_db(db, cred, garth_client):
    """将 garth client 的 session 保存到数据库"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            garth_client.dump(tmpdir)
            session_data = {}
            for filename in ["oauth1_token.json", "oauth2_token.json"]:
                filepath = os.path.join(tmpdir, filename)
                if os.path.exists(filepath):
                    with open(filepath, "r") as f:
                        session_data[filename] = json.load(f)

        cred.garth_session = json.dumps(session_data)
        cred.session_expires_at = datetime.now(UTC) + timedelta(hours=23)
        cred.last_error = None
        cred.error_count = 0
        db.commit()
    except Exception as e:
        logger.warning(f"[session-renew] 保存 session 失败: {e}")
        db.rollback()
