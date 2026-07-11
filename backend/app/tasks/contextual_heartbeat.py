# -*- coding: utf-8 -*-
"""情境心跳 celery 任务(Slice 2) —— 白天每 30min 的确定性触发器 tick。

beat 时区是 Asia/Shanghai,每 30min 无条件 fire;**白天窗判定按用户时区**在任务内收口
(`get_user_now` → `is_daytime`),让不同时区用户各自在 08–22 本地白天被 tick,夜间跳过。

一 tick 做四件事(纯读 + 提示,R4:绝不写健康数据):
1. 圈定候选用户(有在服药/在飞周期/今日饮水/今日步数的用户,不打扰空账号);
2. 逐用户:白天门 → 读 Twin(``use_cache=True``,绝不重建)→ 组装规则原语 → 跑 4 条确定性规则;
3. 每个候选提示过既有 `proactive_coordinator` 打扰预算**硬闸**:
   - allowed → APNs 推送 + `log_proactive_trigger(notified=True)`(计入全局周预算,下 tick 生效);
   - 被全局/tier 预算挡 → `suppressed_by_budget`,不推;
   - 被静默/忙碌窗挡 → `deferred`(折进下次简报的 fallback_surface),不推;
   预算耗尽 = 0 push,绝不绕。
4. 写一条 `heartbeat_tick` 审计快照(steps_today + 遥测计数),既是遥测可查面,
   也是**久坐规则**下一 tick 的 ~2h 参照步数来源(无需新表)。

fail-loud:单条规则抛错由 `evaluate_heartbeat` 计入 failed_rules 并 logger.error;
单用户处理失败 rollback + 记 user_id,不连累整批。
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.agent_audit_log import AgentAuditLog
from app.models.daily_health import GarminData, WaterIntake
from app.models.intervention_cycle import InterventionCycle
from app.models.medication import Medication
from app.services import contextual_heartbeat as chb
from app.services.notification.push_service import PushService
from app.services.proactive_coordinator import proactive_notification_decision
from app.twin.builder import build_twin
from app.utils.async_helpers import run_async
from app.utils.timezone import get_china_today, get_user_now

logger = logging.getLogger(__name__)

# ends with `_watch` → 推送计入 proactive_coordinator 的全局周预算(与 *_watch 共享一个硬闸)。
_AGENT_TYPE = "contextual_heartbeat_watch"
_TICK_ACTION = "heartbeat_tick"          # 每 tick 每用户一条审计快照(遥测 + 久坐参照步数)
_FALLBACK_SURFACE = "daily_briefing"     # 被静默/忙碌窗延后时的次优出口(折进下次简报)
_PRIOR_TICK_SCAN = 12                    # 找 ~2h 前参照时最多回看多少条快照


def _candidate_user_ids(db, today: date) -> List[int]:
    """圈定值得 tick 的用户:有在服药 / 在飞干预周期 / 今日饮水 / 今日步数。

    并集去重。空账号(四项皆无)不进候选,避免为无提示可发的用户白建 Twin。
    """
    ids: set[int] = set()
    ids.update(
        uid for (uid,) in db.query(Medication.user_id)
        .filter(Medication.is_active.is_(True)).distinct().all()
    )
    ids.update(
        uid for (uid,) in db.query(InterventionCycle.user_id)
        .filter(InterventionCycle.status == "active").distinct().all()
    )
    ids.update(
        uid for (uid,) in db.query(WaterIntake.user_id)
        .filter(WaterIntake.record_date == today).distinct().all()
    )
    ids.update(
        uid for (uid,) in db.query(GarminData.user_id)
        .filter(GarminData.record_date == today, GarminData.steps.isnot(None))
        .distinct().all()
    )
    return sorted(ids)


def _active_cycles(db, user_id: int) -> List[Dict]:
    rows = (
        db.query(
            InterventionCycle.id,
            InterventionCycle.cycle_type,
            InterventionCycle.planned_end_date,
        )
        .filter(
            InterventionCycle.user_id == user_id,
            InterventionCycle.status == "active",
        )
        .all()
    )
    return [
        {"id": r[0], "cycle_type": r[1], "planned_end_date": r[2]} for r in rows
    ]


def _read_prior_steps(db, user_id: int, now_utc: datetime) -> Tuple[Optional[int], Optional[float]]:
    """从本用户最近的 heartbeat_tick 快照里,取一个年龄落在 [1.5h, 3h] 的 steps_today 作 ~2h 参照。

    年龄从快照 result_detail 里的 ISO ``snapshot_at`` 算(tz-safe,不依赖 created_at 列时区语义)。
    无合适样本 → (None, None) → 久坐规则不触发(冷启动/新用户不误报)。
    """
    rows = (
        db.query(AgentAuditLog.result_detail)
        .filter(
            AgentAuditLog.user_id == user_id,
            AgentAuditLog.action == _TICK_ACTION,
        )
        .order_by(AgentAuditLog.id.desc())
        .limit(_PRIOR_TICK_SCAN)
        .all()
    )
    for (detail,) in rows:
        detail = detail or {}
        steps = detail.get("steps_today")
        snap = detail.get("snapshot_at")
        if steps is None or not snap:
            continue
        try:
            snap_dt = datetime.fromisoformat(str(snap))
        except ValueError:
            continue
        if snap_dt.tzinfo is None:
            snap_dt = snap_dt.replace(tzinfo=UTC)
        age_h = (now_utc - snap_dt).total_seconds() / 3600.0
        if chb.SEDENTARY_LOOKBACK_MIN_HOURS <= age_h <= chb.SEDENTARY_LOOKBACK_MAX_HOURS:
            return int(steps), age_h
    return None, None


def _assemble_inputs(db, user_id: int, local_now: datetime) -> chb.HeartbeatInputs:
    """从 Twin(缓存)+ DB 摘出规则所需原语。绝不重建 Twin(use_cache=True)。"""
    twin = build_twin(db, user_id, use_cache=True)
    beh = twin.behavioral
    now_utc = local_now.astimezone(UTC)
    steps_now = twin.physiological.steps_today
    steps_prior, prior_age = _read_prior_steps(db, user_id, now_utc)
    return chb.HeartbeatInputs(
        hour=local_now.hour,
        today=local_now.date(),
        now_minutes=local_now.hour * 60 + local_now.minute,
        water_ml_today=int(beh.water_ml_today or 0),
        water_goal_ml=int(beh.water_goal_ml or 0),
        water_progress_pct=float(beh.water_progress_pct or 0.0),
        active_meds=twin.medication.active_meds or [],
        active_cycles=_active_cycles(db, user_id),
        steps_now=steps_now,
        steps_prior=steps_prior,
        prior_age_hours=prior_age,
    )


def _write_tick_snapshot(db, user_id: int, now_utc: datetime, steps_now: Optional[int],
                         counts: Dict[str, int]) -> None:
    """写一条 heartbeat_tick 审计快照(遥测 + 久坐参照步数)。旁路,写失败记 error 不挂 tick。"""
    detail = {
        "steps_today": steps_now,
        "snapshot_at": now_utc.isoformat(),
        "considered": counts.get("considered", 0),
        "emitted": counts.get("emitted", 0),
        "suppressed_by_budget": counts.get("suppressed_by_budget", 0),
        "deferred": counts.get("deferred", 0),
        "failed_rules": counts.get("failed_rules", 0),
    }
    try:
        db.add(AgentAuditLog(
            user_id=user_id,
            agent_type=_AGENT_TYPE,
            action=_TICK_ACTION,
            result_summary=(
                f"heartbeat considered={detail['considered']} emitted={detail['emitted']} "
                f"suppressed_by_budget={detail['suppressed_by_budget']} "
                f"deferred={detail['deferred']} failed_rules={detail['failed_rules']}"
            ),
            result_detail=detail,
        ))
        db.commit()
    except Exception as e:  # noqa: BLE001 — 遥测写失败可观测但不挂 tick
        logger.error("[heartbeat] tick 快照写入失败 user=%s: %s", user_id, e)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _emit_candidate(db, push_service: PushService, user_id: int,
                    cand: chb.HeartbeatCandidate) -> str:
    """过打扰预算硬闸 → 推送 / 抑制 / 延后。返回 'emitted' | 'suppressed_by_budget' | 'deferred'。"""
    from app.agents.audit import log_proactive_trigger

    decision = proactive_notification_decision(
        db, user_id, tier=cand.tier,
        reason=cand.reason, action=cand.action, fallback_surface=_FALLBACK_SURFACE,
    )
    if decision["allowed"]:
        run_async(push_service.send_notification(
            user_id=user_id,
            notification_type="reminder",
            title=cand.title,
            content=cand.body,
            data={"kind": "heartbeat", "rule_id": cand.rule_id},
            severity="info",
        ))
        log_proactive_trigger(
            db, user_id, agent_type=_AGENT_TYPE, metric=cand.metric,
            kind=cand.rule_id, delta=0.0, notable=True, notified=True, tier=cand.tier,
        )
        return "emitted"

    # 被挡:全局/tier 预算 = 硬压制;静默/忙碌窗 = 延后折进简报。两种都不推,都记 notified=False。
    log_proactive_trigger(
        db, user_id, agent_type=_AGENT_TYPE, metric=cand.metric,
        kind=cand.rule_id, delta=0.0, notable=True, notified=False, tier=cand.tier,
    )
    if decision.get("blocked_reason") in {"global_budget", "tier_budget"}:
        return "suppressed_by_budget"
    return "deferred"


def run_contextual_heartbeat(db) -> Dict[str, int]:
    """核心逻辑(接受 db,便于测试)。celery 包装 `contextual_heartbeat` 开 SessionLocal 调它。"""
    totals = {
        "users_scanned": 0,
        "considered": 0,
        "emitted": 0,
        "suppressed_by_budget": 0,
        "deferred": 0,
        "failed_rules": 0,
    }
    today_cn = get_china_today()
    user_ids = _candidate_user_ids(db, today_cn)
    push_service = PushService(db)

    for user_id in user_ids:
        try:
            local_now = get_user_now(db, user_id)
            if not chb.is_daytime(local_now.hour):
                continue  # 夜间(22–08 用户时区)不 tick
            totals["users_scanned"] += 1

            inp = _assemble_inputs(db, user_id, local_now)
            result = chb.evaluate_heartbeat(inp)
            totals["considered"] += result.considered
            totals["failed_rules"] += result.failed_rules

            per_user = {
                "considered": result.considered,
                "emitted": 0,
                "suppressed_by_budget": 0,
                "deferred": 0,
                "failed_rules": result.failed_rules,
            }
            for cand in result.candidates:
                outcome = _emit_candidate(db, push_service, user_id, cand)
                per_user[outcome] += 1
                totals[outcome] += 1

            _write_tick_snapshot(
                db, user_id, local_now.astimezone(UTC), inp.steps_now, per_user,
            )
        except Exception as e:  # noqa: BLE001 — 单用户失败不拖累整批
            logger.warning("[heartbeat] user=%s 处理失败(跳过): %s", user_id, e)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass

    logger.info(
        "[heartbeat] 完成:扫描 %s 人,考量 %s,推送 %s,预算压制 %s,延后 %s,规则异常 %s",
        totals["users_scanned"], totals["considered"], totals["emitted"],
        totals["suppressed_by_budget"], totals["deferred"], totals["failed_rules"],
    )
    return totals


@celery_app.task
def contextual_heartbeat() -> Dict[str, int]:
    """白天每 30min 的确定性触发器心跳(v1 零 LLM)。见模块 docstring。"""
    with SessionLocal() as db:
        return run_contextual_heartbeat(db)
