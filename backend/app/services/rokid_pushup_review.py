"""赛后复盘 (post-session exercise review) for the Rokid push-up flow.

R4 boundary: this is OBSERVATIONAL COACHING — the session's own quality metrics
+ the user's existing training-load context (from MovementCoachSpecialist) +
teaching links. It NEVER emits imperative medical/rehab commands.

Allowed   : "本组 12 个,平均质量分 78;今日训练负荷 ACWR 1.1(适中)"
Forbidden : "你必须做满 3 组" / "立刻放慢" / 康复处方

Defense-in-depth (same ordering as ``meal_analysis.build_finish_summary``):
  1. Build the candidate free text (observations + MovementCoach summary).
  2. Run the SafetyGuardian guidance red-line rule over the PRE-sanitization text
     so any imperative phrase becomes an auditable HIGH alert.
  3. Return the sanitized text to the client (imperatives softened / stripped).

The MovementCoach summary itself is observational, but its actions can be
imperative ("强制 deload"/"完全休息 2-3 天"). We only surface its *summary* and
*status* fields as free text (already observational), and we still pass every
returned string through ``sanitize_guidance`` so an imperative leaking in is
softened + alerted rather than shipped raw.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents import audit
from app.models.rokid_pushup import RokidPushupEvent, RokidPushupSession
from app.services.exercise_guide import get_exercise
from app.services.guidance_validator import sanitize_guidance

logger = logging.getLogger(__name__)

# 这套复盘只复盘俯卧撑 (Rokid pushup flow), teaching link 锚定 exercise_guide 的 pushup 条目。
_PUSHUP_EXERCISE_KEY = "pushup"

_DISCLAIMER = (
    "以上为观察性复盘与一般性训练参考, 非诊断/处方/康复医嘱。"
    "训练负荷数据来自可穿戴设备估算; 是否调整强度请结合自身感受, "
    "有伤痛或慢病请咨询医生或康复师。相关非因果。"
)


def compute_session_quality(events: List[RokidPushupEvent]) -> Dict[str, Any]:
    """本组质量指标 —— 纯数据聚合, 无判定/无处方。

    - reps           : 最大上报 rep 数 (rep 事件携带累计 reps; 取最大值)
    - avg_quality_score: 携带 quality_score 的事件均值 (None if 无)
    - event_count    : 该 session 的事件总数
    """
    event_count = len(events)

    rep_values = [e.reps for e in events if e.reps is not None]
    reps = max(rep_values) if rep_values else 0

    quality_values = [e.quality_score for e in events if e.quality_score is not None]
    avg_quality_score = (
        round(sum(quality_values) / len(quality_values), 1) if quality_values else None
    )

    return {
        "reps": reps,
        "avg_quality_score": avg_quality_score,
        "event_count": event_count,
    }


def _movement_context(db: Session, user_id: int) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Build the user's twin and run MovementCoach (with RecoveryCoach readiness).

    Mirrors ``orchestrator.orchestrator`` wiring: RecoveryCoach runs first and its
    ``zone`` is passed to MovementCoach via context["readiness_zone"].

    Returns ``(training_context, movement_summary)``. Both are ``None`` when the
    twin / MovementCoach can't produce a usable finding (no training data) — the
    caller degrades gracefully, it never fakes success.
    """
    try:
        from app.agents.movement_coach import MovementCoachSpecialist
        from app.agents.recovery_coach import RecoveryCoachSpecialist
        from app.twin.builder import build_twin

        twin = build_twin(db, user_id)

        ctx: Dict[str, Any] = {}
        try:
            recovery_finding = RecoveryCoachSpecialist().run(twin, ctx)
            zone = (recovery_finding.raw or {}).get("zone")
            if zone and zone != "unknown":
                ctx["readiness_zone"] = zone
        except Exception as e:  # noqa: BLE001
            # Readiness is optional context for MovementCoach; record and continue.
            # WARNING, not INFO: a silently-INFO'd degradation is how this feature
            # quietly died before — make degradations visible in prod logs.
            logger.warning(f"[rokid_review] recovery readiness skipped: {e}")

        finding = MovementCoachSpecialist().run(twin, ctx)
    except Exception as e:  # noqa: BLE001
        # Twin build / specialist failure → degrade, do NOT pretend success.
        # WARNING, not INFO: silent INFO is how this feature died (matches the
        # meal_analysis fix). Degradation must be loud in prod logs.
        logger.warning(f"[rokid_review] movement context unavailable: {e}")
        return None, None

    raw = finding.raw or {}
    status = raw.get("status")
    # status == "unknown" means MovementCoach saw no usable training-load data.
    if not status or status == "unknown":
        return None, None

    acwr = raw.get("acwr")
    today_intensity = raw.get("intensity")
    readiness_zone = raw.get("readiness_used")

    training_context = {
        "acwr": acwr,
        "training_status": status,
        "readiness_zone": readiness_zone,
        "today_intensity": today_intensity,
    }
    return training_context, finding.summary


def _teaching_links() -> List[Dict[str, Any]]:
    """Teaching link → the existing exercise-guide pushup entry. Omit if absent."""
    entry = get_exercise(_PUSHUP_EXERCISE_KEY)
    if not entry:
        return []
    return [
        {
            "key": _PUSHUP_EXERCISE_KEY,
            "title": f"{entry['name']}动作要领",
            "url": f"/fitness/exercise-guide/{_PUSHUP_EXERCISE_KEY}",
        }
    ]


_STATUS_ZH = {
    "optimal": "负荷适中",
    "peaking": "接近峰值",
    "overload": "负荷偏高",
    "undertrained": "负荷偏低",
    "detraining": "脱训阶段",
    "building": "负荷构建中",
}


def _build_observations(
    quality: Dict[str, Any],
    training_context: Optional[Dict[str, Any]],
) -> List[str]:
    """观察性叙述 —— suggest/consider 措辞, 无命令式, 无医学处方。"""
    obs: List[str] = []

    reps = quality["reps"]
    avg_q = quality["avg_quality_score"]
    if avg_q is not None:
        obs.append(f"本组完成 {reps} 个,平均动作质量分约 {avg_q}。")
    else:
        obs.append(f"本组完成 {reps} 个(本次未采集到动作质量分)。")

    if training_context is None:
        obs.append("暂无足够训练负荷数据做趋势复盘,可在多同步几次活动后再看负荷走势。")
        return obs

    acwr = training_context.get("acwr")
    status = training_context.get("training_status")
    status_zh = _STATUS_ZH.get(status or "", status or "未知")
    if acwr is not None:
        obs.append(f"今日训练负荷 ACWR 约 {acwr:.2f}({status_zh})。相关非因果。")
    else:
        obs.append(f"今日训练负荷状态:{status_zh}。相关非因果。")

    return obs


def build_review(
    db: Session,
    user_id: int,
    session: RokidPushupSession,
    events: List[RokidPushupEvent],
) -> Dict[str, Any]:
    """Assemble the R4-safe post-session review for one push-up session.

    Free text (``observations`` + MovementCoach summary) is run through
    ``sanitize_guidance``; ``movement_imperative_red_line`` is evaluated over the
    PRE-sanitization text and any alert is surfaced in ``guidance_alerts``.
    Sanitized text is returned to the client.
    """
    quality = compute_session_quality(events)
    training_context, movement_summary = _movement_context(db, user_id)

    raw_observations = _build_observations(quality, training_context)
    if movement_summary:
        raw_observations.append(movement_summary)

    # ── R4 guard: rules on PRE-sanitization text, sanitized text to client ──
    sanitized_observations: List[str] = []
    flagged = False
    violations: List[str] = []
    for text in raw_observations:
        result = sanitize_guidance(text)
        sanitized_observations.append(result.text)
        if result.flagged:
            flagged = True
            violations.extend(result.violations)

    guidance_alerts = _run_guidance_rules(db, user_id, raw_observations)

    return {
        "session_id": session.id,
        "session_quality": quality,
        "training_context": training_context,
        "observations": sanitized_observations,
        "teaching_links": _teaching_links(),
        "guidance_alerts": guidance_alerts,
        "guidance_sanitized": flagged,
        "guidance_violations": violations,
        "disclaimer": _DISCLAIMER,
    }


def _run_guidance_rules(
    db: Session,
    user_id: int,
    candidate_texts: List[str],
) -> List[Dict[str, Any]]:
    """Run the movement-imperative red-line rule over the PRE-sanitization text.

    Mirrors ``meal_analysis.run_guidance_rules`` but scoped to the movement rule —
    this review only emits movement-flavored guidance, never diet prescriptions.
    Any hit is logged to the agent audit bypass (fail-open audit, never blocks).
    """
    from app.agents.safety_guardian.rules.guidance_red_lines import (
        movement_imperative_red_line,
    )
    from app.twin.schema import HealthTwin, TwinMeta

    blob = "\n".join(t for t in candidate_texts if t)
    if not blob:
        return []

    twin = HealthTwin(
        meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc))
    )
    twin.acute.pending_guidance_texts = [blob]

    alerts: List[Dict[str, Any]] = []
    alert = movement_imperative_red_line(twin)
    if alert is not None:
        alerts.append(alert.model_dump_for_api())

    if alerts:
        audit.log_safety_evaluation(
            db,
            user_id=user_id,
            alerts_count=len(alerts),
            result_summary=f"rokid pushup review guidance red-line: {len(alerts)} alert(s)",
            twin_build_ms=0,
            evaluate_ms=0,
            twin_sources=["rokid_pushup_review_guidance"],
            result_detail={"alerts": alerts},
        )
    return alerts
