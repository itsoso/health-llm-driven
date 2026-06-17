"""Workday Health Scheduler v0.

把工作日微运动计划生成为 HealthProtocol,由 agenda/watch_summary 继续投影和执行。
v0 只做固定三段窗口 + readiness 降级,不接位置/日历,也不把微运动伪造成正式训练记录。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.daily_health import GarminData
from app.models.health_protocol import HealthProtocol
from app.services import recovery_decision

logger = logging.getLogger(__name__)

_SOURCE_PREFIX = "workday_scheduler:v0"


@dataclass(frozen=True)
class WorkdayActionSpec:
    slot: str
    domain: str
    name: str
    time_window: str
    implied_quantity: Dict[str, Any]


def _latest_readiness_score(db: Session, user_id: int, day: date) -> Optional[int]:
    row = db.query(GarminData.training_readiness_score).filter(
        GarminData.user_id == user_id,
        GarminData.record_date <= day,
        GarminData.training_readiness_score.isnot(None),
    ).order_by(GarminData.record_date.desc()).first()
    return int(row[0]) if row and row[0] is not None else None


def _readiness_tone(score: Optional[int]) -> str:
    if score is None:
        return "yellow"
    if score >= 70:
        return "green"
    if score >= 50:
        return "yellow"
    return "red"


def _specs_for_tone(
    tone: str,
    score: Optional[int],
    *,
    readiness_source: str,
) -> List[WorkdayActionSpec]:
    base = {
        "readiness_score": score,
        "readiness_tone": tone,
        "readiness_source": readiness_source,
        "planner": _SOURCE_PREFIX,
    }
    if tone == "green":
        return [
            WorkdayActionSpec(
                slot="arrival",
                domain="training",
                name="到公司后俯卧撑 12 个",
                time_window="morning",
                implied_quantity={
                    **base,
                    "slot": "arrival",
                    "exercise_type": "pushups",
                    "reps": 12,
                    "intensity": "micro",
                },
            ),
            WorkdayActionSpec(
                slot="post_lunch",
                domain="exercise",
                name="午餐后轻松步行 10 分钟",
                time_window="noon",
                implied_quantity={
                    **base,
                    "slot": "post_lunch",
                    "exercise_type": "walk",
                    "duration_min": 10,
                    "intensity": "easy",
                },
            ),
            WorkdayActionSpec(
                slot="afternoon",
                domain="activity",
                name="下午站立拉伸 3 分钟",
                time_window="afternoon",
                implied_quantity={
                    **base,
                    "slot": "afternoon",
                    "exercise_type": "mobility",
                    "duration_min": 3,
                    "intensity": "easy",
                },
            ),
        ]
    if tone == "red":
        return [
            WorkdayActionSpec(
                slot="arrival",
                domain="activity",
                name="到公司后轻走 3 分钟",
                time_window="morning",
                implied_quantity={
                    **base,
                    "slot": "arrival",
                    "exercise_type": "walk",
                    "duration_min": 3,
                    "intensity": "recovery",
                    "downgraded_from": "pushups",
                },
            ),
            WorkdayActionSpec(
                slot="post_lunch",
                domain="exercise",
                name="午餐后轻松步行 5 分钟",
                time_window="noon",
                implied_quantity={
                    **base,
                    "slot": "post_lunch",
                    "exercise_type": "walk",
                    "duration_min": 5,
                    "intensity": "recovery",
                },
            ),
            WorkdayActionSpec(
                slot="afternoon",
                domain="activity",
                name="下午肩颈拉伸 2 分钟",
                time_window="afternoon",
                implied_quantity={
                    **base,
                    "slot": "afternoon",
                    "exercise_type": "mobility",
                    "duration_min": 2,
                    "intensity": "recovery",
                },
            ),
        ]
    return [
        WorkdayActionSpec(
            slot="arrival",
            domain="training",
            name="到公司后上斜俯卧撑 6 个",
            time_window="morning",
            implied_quantity={
                **base,
                "slot": "arrival",
                "exercise_type": "incline_pushups",
                "reps": 6,
                "intensity": "low",
                "downgraded_from": "pushups",
            },
        ),
        WorkdayActionSpec(
            slot="post_lunch",
            domain="exercise",
            name="午餐后轻松步行 8 分钟",
            time_window="noon",
            implied_quantity={
                **base,
                "slot": "post_lunch",
                "exercise_type": "walk",
                "duration_min": 8,
                "intensity": "easy",
            },
        ),
        WorkdayActionSpec(
            slot="afternoon",
            domain="activity",
            name="下午站立拉伸 3 分钟",
            time_window="afternoon",
            implied_quantity={
                **base,
                "slot": "afternoon",
                "exercise_type": "mobility",
                "duration_min": 3,
                "intensity": "easy",
            },
        ),
    ]


def _slot_note(slot: str, *, score: Optional[int], tone: str) -> str:
    score_text = "unknown" if score is None else str(score)
    return f"{_SOURCE_PREFIX}:{slot} | readiness={tone}:{score_text}"


def _readiness_gate(db: Session, user_id: int, day: date) -> tuple[Optional[int], str, str]:
    try:
        decision = recovery_decision.training_decision(db, user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[workday_scheduler] training_decision failed user=%s: %s", user_id, exc)
        decision = None

    if isinstance(decision, dict):
        light = decision.get("light")
        score = decision.get("readiness_score")
        conf_score = decision.get("confidence_score")
        has_signal = (
            light in {"green", "yellow", "red"}
            and (
                light == "red"
                or (
                    score is not None
                    and (conf_score is None or float(conf_score) >= 0.5)
                )
            )
        )
        if has_signal:
            return (int(score) if score is not None else None), str(light), "training_decision"

    score = _latest_readiness_score(db, user_id, day)
    return score, _readiness_tone(score), "garmin_data"


def _find_slot_protocol(db: Session, user_id: int, slot: str) -> Optional[HealthProtocol]:
    prefix = f"{_SOURCE_PREFIX}:{slot}"
    rows = db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id,
        HealthProtocol.status == "active",
        HealthProtocol.notes.like(f"{prefix}%"),
    ).order_by(HealthProtocol.id.asc()).all()
    return rows[0] if rows else None


def _apply_spec(
    protocol: HealthProtocol,
    spec: WorkdayActionSpec,
    *,
    score: Optional[int],
    tone: str,
) -> None:
    protocol.domain = spec.domain
    protocol.name = spec.name
    protocol.mechanism = "pre_commit"
    protocol.implied_quantity = spec.implied_quantity
    protocol.cadence = "daily"
    protocol.time_window = spec.time_window
    protocol.completion_mode = "one_tap"
    protocol.can_default_complete = False
    protocol.manual_track_allowed = True
    protocol.source_model = None
    protocol.source_id = None
    protocol.notes = _slot_note(spec.slot, score=score, tone=tone)


def generate_today(db: Session, user_id: int, *, day: Optional[date] = None) -> Dict[str, Any]:
    """生成/刷新今日工作日微运动协议。

    幂等:同一用户同一 slot 只保留一条 active protocol;再次生成只更新强度/名称。
    """
    day = day or date.today()
    score, tone, readiness_source = _readiness_gate(db, user_id, day)
    specs = _specs_for_tone(tone, score, readiness_source=readiness_source)
    created = 0
    updated = 0
    protocols: List[HealthProtocol] = []

    for spec in specs:
        protocol = _find_slot_protocol(db, user_id, spec.slot)
        if protocol is None:
            protocol = HealthProtocol(user_id=user_id, status="active")
            db.add(protocol)
            created += 1
        else:
            updated += 1
        _apply_spec(protocol, spec, score=score, tone=tone)
        protocols.append(protocol)

    db.commit()
    for protocol in protocols:
        db.refresh(protocol)

    logger.info(
        "[workday_scheduler] generated user=%s tone=%s score=%s created=%s updated=%s",
        user_id,
        tone,
        score,
        created,
        updated,
    )
    return {
        "date": day.isoformat(),
        "readiness_score": score,
        "readiness_tone": tone,
        "readiness_source": readiness_source,
        "created": created,
        "updated": updated,
        "protocol_ids": [p.id for p in protocols],
        "actions": [
            {
                "protocol_id": p.id,
                "slot": (p.implied_quantity or {}).get("slot"),
                "domain": p.domain,
                "name": p.name,
                "time_window": p.time_window,
                "implied_quantity": p.implied_quantity,
            }
            for p in protocols
        ],
    }
