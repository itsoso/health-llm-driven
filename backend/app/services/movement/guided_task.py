"""引导式运动任务装配 (R17 裁决①「Agent 而非闹钟」)。

到点 ≠ 硬推:必经 readiness 门控 ——
  - RED + strength → 不推力量,swap 成基础拉伸(rest_instead)
  - YELLOW        → 减量(reps×0.7 取整 / sets-1)做(modified)
  - GREEN         → 按确定性进阶规则,基于「上次完成」递增(do)
  - UNKNOWN(决策失败)→ 当 YELLOW 保守处理(守 Rule#1:宁可保守,不在 red 推力量)

内容(form cue / voice)来自 exercise_library 循证库,LLM 不参与「能否做 / 做什么」。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.services.movement import exercise_library as lib
from app.services.movement.exercise_library import Exercise, LastCompletion, Plan

logger = logging.getLogger(__name__)

# zone(recovery_decision.light)→ 门控档位。决策失败 / 未知 zone → yellow 保守。
_VALID_ZONES = {"green", "yellow", "red"}


def _readiness_zone(db: Session, user_id: int) -> tuple[str, Optional[int], str]:
    """读 recovery_decision.training_decision → (zone, readiness_score, reason)。

    失败(无数据 / 抛错)降级为 unknown,调用方当 yellow 保守处理。绝不让异常冒泡成 500。
    """
    try:
        from app.services.recovery_decision import training_decision

        td = training_decision(db, user_id) or {}
        light = td.get("light")
        score = td.get("readiness_score")
        if light in _VALID_ZONES:
            reasons = td.get("reasons") or []
            reason = reasons[0] if reasons else f"今日恢复评估:{light}"
            return light, score, reason
        logger.info("guided_task: training_decision 返回未知 light=%r,降级 unknown", light)
    except Exception as exc:  # noqa: BLE001 — 门控失败必须安全降级,不可让任务线 500
        logger.warning("guided_task: training_decision 失败,降级 unknown: %s", exc)
    return "unknown", None, "恢复数据不足,保守按减量处理"


def _last_completion(db: Session, user_id: int, exercise_id: str) -> Optional[LastCompletion]:
    """取最近一次该动作的完成记录(ExerciseRecord),用于确定性进阶。取不到 → None。"""
    try:
        from app.models.daily_health import ExerciseRecord

        rec = (
            db.query(ExerciseRecord)
            .filter(
                ExerciseRecord.user_id == user_id,
                ExerciseRecord.exercise_type == exercise_id,
            )
            .order_by(ExerciseRecord.record_date.desc(), ExerciseRecord.id.desc())
            .first()
        )
        if rec is None:
            return None
        # 有记录即视为完成(reps/sets 任一为正更确凿)
        completed = bool((rec.reps or 0) > 0 or (rec.sets or 0) > 0 or rec.duration_seconds)
        return LastCompletion(completed=completed, reps=rec.reps, sets=rec.sets)
    except Exception as exc:  # noqa: BLE001 — 进阶取数失败只退回默认量,不阻断
        logger.info("guided_task: 取上次完成记录失败,用默认量: %s", exc)
        return None


def _reduce_plan(plan: Plan) -> Plan:
    """YELLOW 减量:reps×0.7 取整(下限 1),sets-1(下限 1),其余不变。"""
    from dataclasses import replace

    reps = plan.reps
    if reps is not None:
        reps = max(1, int(reps * 0.7))
    sets = plan.sets
    if sets is not None:
        sets = max(1, sets - 1)
    return replace(plan, reps=reps, sets=sets)


def _plan_dict(plan: Plan, note: str) -> Dict[str, Any]:
    return {
        "sets": plan.sets,
        "reps": plan.reps,
        "duration_sec": plan.duration_sec,
        "rest_sec": plan.rest_sec,
        "progression_note": note,
    }


def _exercise_dict(ex: Exercise) -> Dict[str, Any]:
    return {
        "id": ex.id,
        "name": ex.name,
        "evidence_tier": ex.evidence_tier,
        "cues": list(ex.cues),
        "media_ref": ex.media_ref,
        "contraindications": list(ex.contraindications),
    }


def _title(ex: Exercise, plan: Plan, swapped: bool) -> str:
    if plan.duration_sec:
        minutes = max(1, round(plan.duration_sec / 60))
        if swapped:
            return f"今天换轻拉伸 · {minutes} 分钟"
        return f"{ex.name} · {minutes} 分钟"
    if plan.sets and plan.reps:
        return f"{ex.name} · {plan.sets}×{plan.reps}"
    return ex.name


def build_guided_task(db: Session, user_id: int, domain: str) -> Dict[str, Any]:
    """组装一个 readiness 门控的引导式运动任务(严格按 R17 契约)。

    domain: strength | mobility。未知 domain → 当 mobility 兜底(拉伸最安全)。
    """
    domain = domain if domain in ("strength", "mobility") else "mobility"
    zone, readiness_score, zone_reason = _readiness_zone(db, user_id)
    gate_zone = zone if zone in _VALID_ZONES else "yellow"  # unknown → 保守按 yellow

    ex = lib.default_exercise_for_domain(domain) or lib.red_fallback_exercise()
    swapped = False
    safety_note: Optional[str] = None

    # ── 门控裁决 ──────────────────────────────────────────────
    if domain == "strength" and gate_zone == "red":
        # RED:不推力量,swap 成基础拉伸 / 休息
        decision = "rest_instead"
        ex = lib.red_fallback_exercise()
        swapped = True
        safety_note = "今日恢复不足(红灯),已将力量训练替换为轻拉伸 / 休息"
        prog = ex.progression_rule(ex, None)
        plan = prog.plan
        progression_note = "恢复优先:今天只做轻拉伸,放松不加压"
    elif gate_zone == "yellow":
        # YELLOW:减量做
        decision = "modified"
        last = _last_completion(db, user_id, ex.id)
        prog = ex.progression_rule(ex, last)
        plan = _reduce_plan(prog.plan)
        progression_note = "今日恢复一般(黄灯),已减量:" + prog.note
        safety_note = "今日恢复一般,训练量已下调"
    else:
        # GREEN:全量 + 按上次完成进阶
        decision = "do"
        last = _last_completion(db, user_id, ex.id)
        prog = ex.progression_rule(ex, last)
        plan = prog.plan
        progression_note = prog.note

    gate_reason = zone_reason
    if zone == "unknown":
        gate_reason = "恢复数据不足,保守按减量处理(未在低 readiness 推力量)"

    return {
        "domain": domain,
        "gate": {
            "decision": decision,
            "readiness_zone": zone,           # green/yellow/red/unknown(真实 zone,unknown 透明暴露)
            "reason": gate_reason,
        },
        "title": _title(ex, plan, swapped),
        "exercise": _exercise_dict(ex),
        "plan": _plan_dict(plan, progression_note),
        "voice_script": list(ex.voice_script),
        "capture": {"mode": "manual", "fields": ["completed", "rpe"]},
        "safety_note": safety_note,
    }
