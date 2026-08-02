"""
Garmin 数据同步任务
"""
import asyncio
import logging
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


def _notify_garmin_sync_failed(user_id: int, reason: str = "sync_error") -> None:
    """Agent 触发的后台同步终态失败 → 推送告知用户(fail-loud)。best-effort,不抛。

    仅当调用方(agent 的 _trigger_garmin_sync)传 notify_on_failure=True 时才发 ——
    定时 fan-out 静默 skip 无用户等待,不打扰;用户主动"帮我同步"后失败必须知会,
    否则"已在后台同步"变成静默谎报(silent-green)。
    """
    try:
        from app.services.notification.push_service import PushService
        with SessionLocal() as db:
            push_svc = PushService(db)

            async def _send():
                await push_svc.send_notification(
                    user_id=user_id,
                    notification_type="garmin_sync_failed",
                    title="Garmin 同步未成功",
                    content="刚才的后台同步没有完成。请稍后重试，或到「设置 → 设备」检查 Garmin 账号。",
                    data={"reason": reason},
                    respect_quiet_hours=True,
                )

            asyncio.run(_send())
    except Exception as e:
        logger.warning(f"[garmin_sync] 失败推送发送失败 user={user_id}: {e}")


@celery_app.task(bind=True, max_retries=3)
def sync_user_garmin_data(self, user_id: int, days: int = 1, notify_on_failure: bool = False):
    """
    同步单个用户的 Garmin 数据（健康数据 + 运动活动）

    notify_on_failure: agent 主动触发(用户"帮我同步")时置 True —— 终态失败时推送
    告知用户,兑现 fail-loud;定时 fan-out 保持 False(静默 skip,无人等待)。
    """
    logger.info(f"开始同步用户 {user_id} 的 Garmin 数据 (最近 {days} 天)")

    try:
        with SessionLocal() as db:
            # 使用 GarminCredential 获取凭据（与 scheduler/auth 保持一致）
            from app.models.user import GarminCredential
            from app.services.auth import garmin_credential_service
            from app.services.data_collection.garmin_native_auth import credential_can_sync

            credential = db.query(GarminCredential).filter(
                GarminCredential.user_id == user_id,
                GarminCredential.sync_enabled == True,
            ).first()

            if not credential or not credential_can_sync(credential):
                logger.warning(f"用户 {user_id} 没有有效的 Garmin 凭据")
                if notify_on_failure:
                    _notify_garmin_sync_failed(user_id, reason="no_credentials")
                return {"status": "skipped", "reason": "no_credentials"}

            # 解密密码
            try:
                password = garmin_credential_service.decrypt_password(credential.encrypted_password)
            except Exception as e:
                logger.error(f"用户 {user_id} Garmin 凭据解密失败: {e}")
                if notify_on_failure:
                    _notify_garmin_sync_failed(user_id, reason="decrypt_failed")
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
            if error_count:
                from app.services.data_collection.garmin_errors import GarminSyncError

                raise GarminSyncError("Garmin partial date range failure")
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

            # rank7: passive Garmin sync just wrote daily health + workout data →
            # drop the stale twin cache (also fixes the pre-existing ≤60s staleness
            # on passive syncs) and any pre-generated starter answers. Fail-soft.
            if success_count or synced_activities:
                try:
                    from app.twin.cache import invalidate_twin
                    invalidate_twin(user_id)
                except Exception:  # noqa: BLE001 — never fail the sync task
                    pass

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
                        from app.services.notification.push_privacy import safety_alert_push_text
                        from app.services.notification.push_service import PushService
                        push_svc = PushService(db)
                        for sa in critical_alerts[:3]:
                            async def _push_safety(alert=sa):
                                # §5 推送隐私:敏感类别(ddi/dsi/pgx/labs/…)锁屏泛化
                                push_title, push_content = safety_alert_push_text(alert)
                                await push_svc.send_notification(
                                    user_id=user_id,
                                    notification_type="health_alert",
                                    title=push_title,
                                    content=push_content,
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

            # fail-loud 补缝(safety-review N2):非 auth 的软错误可能整批失败
            # (success_count==0 & error_count>0)却走到这里返回 success —— agent 触发
            # 路径承诺过"万一没成功我也会告诉你",此路径必须通知,否则窄 silent-green。
            if notify_on_failure and success_count == 0 and error_count > 0:
                _notify_garmin_sync_failed(user_id, reason="no_data_synced")

            return {
                "status": "success",
                "success_count": success_count,
                "error_count": error_count,
                "activities_count": synced_activities
            }

    except Exception as e:
        logger.error(f"用户 {user_id} Garmin 同步失败: {e}", exc_info=True)
        # 已到最大重试:agent 触发的同步必须 fail-loud 告知用户,否则"已在后台同步"
        # 之后所有重试静默耗尽 = 静默谎报。retries 从 0 计,>= max_retries 即终态。
        if self.request.retries >= self.max_retries:
            if notify_on_failure:
                _notify_garmin_sync_failed(user_id, reason="sync_error")
            return {"status": "error", "reason": str(e)[:200]}
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
        from app.services.data_collection.garmin_native_auth import credential_can_sync

        credentials = db.query(GarminCredential).filter(
            GarminCredential.sync_enabled == True,
        ).all()
        credentials = [credential for credential in credentials if credential_can_sync(credential)]

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
                result = await service.analyzer.analyze(prompt)
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

            # Agent-Native v3 — 跑步类 workout 自动建 Episode + ActionGraph.
            # 失败不影响主流程 (post-run analysis 已成功), 只记 warning.
            try:
                _maybe_create_run_episode(db, user_id, workout)
            except Exception as ep_err:
                logger.warning(
                    f"[自动分析] Episode 创建失败 user={user_id} workout={workout_id}: {ep_err}",
                    exc_info=True,
                )

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
        "renewed" - 原生 token 有效或已刷新并重新加密保存
        "mfa_required" - 需要用户完成 MFA
        "failed" - 原生认证失败
    """
    from app.services.auth import garmin_credential_service
    from app.services.data_collection.garmin_connect import (
        GarminConnectService,
        GarminMFARequiredError,
    )
    from app.services.data_collection.garmin_native_auth import safe_garmin_error_message

    user_id = cred.user_id

    try:
        password = garmin_credential_service.decrypt_password(cred.encrypted_password)
    except Exception as e:
        logger.error(f"{prefix} Garmin 密码解密失败 ({type(e).__name__})")
        cred.last_error = "Garmin 凭证无法解密，请重新连接"
        cred.credentials_valid = False
        db.commit()
        return "failed"

    try:
        service = GarminConnectService(
            cred.garmin_email,
            password,
            is_cn=bool(getattr(cred, "is_cn", False)),
            user_id=user_id,
        )
        service._ensure_authenticated(db)
        cred.login_locked_until = None
        cred.credentials_valid = True
        cred.requires_mfa = False
        cred.last_error = None
        cred.error_count = 0
        db.commit()
        logger.info(f"{prefix} Garmin 原生 token 已检查并更新")
        return "renewed"
    except GarminMFARequiredError:
        cred.requires_mfa = True
        cred.last_error = "Garmin 需要两步验证，请在设置中完成验证"
        db.commit()
        logger.info(f"{prefix} Garmin token 更新需要 MFA")
        return "mfa_required"
    except Exception as e:
        safe_message = safe_garmin_error_message(e)
        logger.warning(f"{prefix} Garmin token 更新失败 ({type(e).__name__})")
        cred.last_error = safe_message
        cred.error_count = (cred.error_count or 0) + 1
        db.commit()
        return "failed"


# ─────────────────────────────────────────────────────────
# Episode hook (Agent-Native v3) — 跑步 workout 自动建 Episode
# ─────────────────────────────────────────────────────────

# 跑步 workout_type 集合 (workout_sync.py 标准化后的值).
_RUN_TYPES = {"running"}


def _maybe_create_run_episode(db, user_id: int, workout: WorkoutRecord):
    """跑步 workout 同步完成后建一个 Episode + ActionGraph.

    幂等: 同一 workout_id 只建一个 Episode (用 source_type/source_id 防重).
    非跑步 / 时长不足 5 分钟 / 距离 < 1km 不触发.
    """
    if (workout.workout_type or "").lower() not in _RUN_TYPES:
        return
    if not workout.duration_seconds or workout.duration_seconds < 300:
        return
    if not workout.distance_meters or workout.distance_meters < 1000:
        return

    # 幂等检查
    from app.models.episode import HealthEpisode
    existing = db.query(HealthEpisode).filter(
        HealthEpisode.user_id == user_id,
        HealthEpisode.source_type == "workout",
        HealthEpisode.source_id == workout.id,
    ).first()
    if existing:
        logger.info(
            f"[Episode] 已存在, 跳过: user={user_id} workout={workout.id} ep={existing.id}"
        )
        return

    from app.services.episode import (
        parse_run_episode,
        plan_run_recovery,
        persist_action_graph,
    )

    episode_input = parse_run_episode(db, user_id, workout, weather=None)
    graph = plan_run_recovery(episode_input.occurred_at, episode_input.context)

    episode = persist_action_graph(
        db,
        user_id=user_id,
        episode_type="run_recovery",
        occurred_at=episode_input.occurred_at,
        graph=graph,
        source_type="workout",
        source_id=workout.id,
        context_snapshot=episode_input.context,
        baseline_snapshot=episode_input.baseline,
    )
    logger.info(
        f"[Episode] 建好 user={user_id} workout={workout.id} ep={episode.id} "
        f"protocol={graph.protocol_slug}@{graph.protocol_version} "
        f"risk={graph.risk.level} actions={len(graph.actions)}"
    )

    # Increment 3 §2: Episode 创建后发推送, 点 deep_link 直进详情页.
    # 失败只 warning, 不影响主流程 (Episode 已落库, mobile 下次开 app 还能拉到).
    try:
        _push_episode_created(user_id, episode, graph)
    except Exception as push_err:
        logger.warning(
            f"[Episode] 推送失败 user={user_id} ep={episode.id}: {push_err}",
            exc_info=True,
        )


def _push_episode_created(user_id: int, episode, graph) -> None:
    """Episode 创建推送 — 跑后/L1+/L4 都走同一通道, 区分 severity.

    Title 走 headline (Planner 已经做了一句话教练话), 没 headline 时 fallback 到通用文案.
    deep_link 指向 mobile /episode/{id}, 由 useNotifications.ts 路由.
    rule_id = episode_{id} 保证同一 Episode 只推一次.
    """
    risk = graph.risk.level if graph and graph.risk else "L0"
    severity_map = {
        "L0": "info",
        "L1": "low",
        "L2": "warning",
        "L3": "high",
        "L4": "critical",
    }
    severity = severity_map.get(risk, "info")

    title_prefix = "跑后恢复"
    if risk in ("L3", "L4"):
        title_prefix = "⚠️ 健康警示"
    elif risk in ("L1", "L2"):
        title_prefix = "跑后教练"

    title = title_prefix
    body = (graph.headline if graph and graph.headline else
            "刚刚的跑步已生成恢复方案, 点开查看 4 步引导.")

    # 用一个新 SQLAlchemy session 跑推送, 避免和外层 transaction 状态纠缠.
    with SessionLocal() as push_db:
        from app.services.notification.push_service import PushService

        push_svc = PushService(push_db)
        asyncio.run(push_svc.send_notification(
            user_id=user_id,
            notification_type="episode_created",
            title=title,
            content=body,
            data={
                "deep_link": f"/episode/{episode.id}",
                "kind": "episode_created",
                "episode_id": episode.id,
                "episode_type": episode.episode_type,
                "risk_level": risk,
                # rule_id 让 push_service 在 24h 窗口内只推一次同 Episode
                "rule_id": f"episode_{episode.id}",
            },
            severity=severity,
            dedup_window_hours=168,
        ))
