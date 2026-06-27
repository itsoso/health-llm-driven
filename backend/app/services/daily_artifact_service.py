"""Daily Artifact projection and telemetry.

The artifact is a small presentation contract over the smart agenda: one top
action, at most three evidence cards, and append-only event telemetry.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.daily_artifact import DailyArtifactEvent
from app.services import agenda_service
from app.utils.timezone import get_user_today


ALLOWED_EVENT_TYPES = frozenset({"impression", "accepted", "completed", "skipped"})
DEFAULT_SAFETY_BOUNDARY = "这是健康管理行动建议, 不替代医生诊断、处方或治疗。"


def build_daily_artifact(
    db: Session,
    user_id: int,
    *,
    followup_within_days: int = 14,
) -> dict[str, Any]:
    """Build today's single-action artifact from the smart agenda."""
    smart_payload = agenda_service.smart_today(
        db,
        user_id,
        followup_within_days=followup_within_days,
        max_items=3,
    )
    artifact_date = _coerce_date(
        smart_payload.get("agenda_date"),
        fallback=get_user_today(db, user_id),
    )
    top_items = ((smart_payload.get("smart") or {}).get("top_items") or [])
    top_action = top_items[0] if top_items else None

    if not isinstance(top_action, dict):
        return _empty_artifact(artifact_date, smart_payload)

    action_view = _top_action_view(top_action)
    evidence = _evidence_cards(top_action)[:3]
    safety_boundary = top_action.get("claim_boundary") or DEFAULT_SAFETY_BOUNDARY

    return {
        "artifact_date": artifact_date.isoformat(),
        "generated_by": "daily_artifact_v1",
        "source": {
            "kind": "agenda.smart_today",
            "ranking": (smart_payload.get("smart") or {}).get("ranking"),
            "source_count": smart_payload.get("source_count", 0),
        },
        "empty_state": False,
        "state": _state_for(top_action),
        "top_action": action_view,
        "evidence": evidence,
        "confidence": _confidence_for(top_action),
        "freshness": _freshness_for(top_action, evidence),
        "safety_boundary": safety_boundary,
    }


def record_daily_artifact_event(
    db: Session,
    user_id: int,
    *,
    event_type: str,
    artifact_date: date | str | None = None,
    top_action_id: str | None = None,
    skip_reason: str | None = None,
    delivered_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an append-only interaction event for the artifact."""
    normalized_event = (event_type or "").strip()
    if normalized_event not in ALLOWED_EVENT_TYPES:
        raise ValueError(f"event_type 仅支持 {sorted(ALLOWED_EVENT_TYPES)}")

    normalized_reason = (skip_reason or "").strip() or None
    if normalized_event == "skipped" and not normalized_reason:
        raise ValueError("event_type=skipped 时必须提供 skip_reason")

    event_date = _coerce_date(artifact_date, fallback=get_user_today(db, user_id))
    event = DailyArtifactEvent(
        user_id=user_id,
        artifact_date=event_date,
        event_type=normalized_event,
        top_action_id=(top_action_id or "").strip() or None,
        skip_reason=normalized_reason,
        delivered_context=delivered_context,
        week_index=_week_index(db, user_id, event_date),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_view(event)


def _empty_artifact(artifact_date: date, smart_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_date": artifact_date.isoformat(),
        "generated_by": "daily_artifact_v1",
        "source": {
            "kind": "agenda.smart_today",
            "ranking": (smart_payload.get("smart") or {}).get("ranking"),
            "source_count": smart_payload.get("source_count", 0),
        },
        "empty_state": True,
        "state": {
            "label": "暂无今日重点",
            "tone": "neutral",
            "summary": "今天暂无需要突出的健康行动。",
        },
        "top_action": None,
        "evidence": [],
        "confidence": "low",
        "freshness": {"status": "limited", "sources": []},
        "safety_boundary": DEFAULT_SAFETY_BOUNDARY,
    }


def _top_action_view(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    return {
        "id": str(item.get("id") or ""),
        "title": item.get("title") or "今日健康行动",
        "type": item.get("type"),
        "status": item.get("status") or "pending",
        "priority_tier": _priority_tier(item),
        "confidence": _confidence_for(item),
        "source": source,
        "why_now": item.get("why_now"),
        "do_now": item.get("do_now"),
        "verify_by": item.get("verify_by") or {},
        "actions": {
            "complete": {
                "method": "POST",
                "endpoint": "/api/v1/agenda/complete",
                "enabled": bool(item.get("can_complete")),
                "source": source,
            },
            "skip": {
                "method": "POST",
                "endpoint": "/api/v1/daily-artifact/me/events",
                "requires_reason": True,
                "event_type": "skipped",
            },
            "ask_reva": {
                "method": "OPEN",
                "target": "/voice-chat?intent=daily_artifact",
            },
        },
    }


def _evidence_cards(item: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    source_kind = source.get("object_type") or "agenda"

    why_now = _clean_text(item.get("why_now"))
    if why_now:
        cards.append({
            "kind": "why_now",
            "label": "Why now",
            "summary": why_now,
            "source": source_kind,
        })

    trajectory = item.get("trajectory_context")
    if isinstance(trajectory, dict) and trajectory:
        summary = _clean_text(trajectory.get("why")) or _clean_text(trajectory.get("state_variable"))
        cards.append({
            "kind": "trajectory",
            "label": "Trajectory",
            "summary": summary or "近期健康轨迹提示这项行动值得优先处理。",
            "domain": trajectory.get("domain"),
            "level": trajectory.get("level"),
            "state_variable": trajectory.get("state_variable"),
            "confidence": trajectory.get("confidence"),
        })

    verify_by = item.get("verify_by")
    if isinstance(verify_by, dict):
        metrics = [str(m) for m in (verify_by.get("metrics") or []) if m][:3]
        if metrics:
            cards.append({
                "kind": "verification",
                "label": "Verification",
                "summary": "后续用这些信号验证是否有效。",
                "metrics": metrics,
                "window_days": verify_by.get("window_days")
                or (verify_by.get("trajectory") or {}).get("verification_window_days"),
            })

    return cards


def _state_for(item: dict[str, Any]) -> dict[str, Any]:
    tier = _priority_tier(item)
    if tier == "P0":
        tone = "urgent"
    elif tier == "P1":
        tone = "focused"
    else:
        tone = "steady"
    return {
        "label": "今日最重要行动",
        "tone": tone,
        "summary": item.get("why_now") or item.get("title") or "今天先完成这一项。",
    }


def _priority_tier(item: dict[str, Any]) -> str:
    explicit = item.get("priority_tier")
    if explicit:
        return str(explicit)
    score = int(item.get("rank_score") or item.get("priority") or 0)
    if score >= 110:
        return "P0"
    if score >= 80:
        return "P1"
    return "P2"


def _confidence_for(item: dict[str, Any]) -> str:
    explicit = item.get("confidence")
    if explicit:
        return str(explicit)
    trajectory = item.get("trajectory_context")
    if isinstance(trajectory, dict) and trajectory.get("confidence"):
        return str(trajectory["confidence"])
    return "medium"


def _freshness_for(item: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    sources = [source.get("object_type")] if source.get("object_type") else []
    return {
        "status": "fresh" if evidence else "limited",
        "sources": sources,
    }


def _week_index(db: Session, user_id: int, artifact_date: date) -> int:
    first = (
        db.query(DailyArtifactEvent)
        .filter(DailyArtifactEvent.user_id == user_id)
        .order_by(DailyArtifactEvent.artifact_date.asc(), DailyArtifactEvent.created_at.asc())
        .first()
    )
    if not first or not first.artifact_date:
        return 1
    return max(1, ((artifact_date - first.artifact_date).days // 7) + 1)


def _event_view(event: DailyArtifactEvent) -> dict[str, Any]:
    created_at = event.created_at
    if isinstance(created_at, datetime):
        created_at_value = created_at.isoformat()
    else:
        created_at_value = str(created_at) if created_at else None
    return {
        "id": event.id,
        "user_id": event.user_id,
        "artifact_date": event.artifact_date.isoformat(),
        "event_type": event.event_type,
        "top_action_id": event.top_action_id,
        "skip_reason": event.skip_reason,
        "delivered_context": event.delivered_context,
        "week_index": event.week_index,
        "created_at": created_at_value,
    }


def _coerce_date(value: date | str | None, *, fallback: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        return date.fromisoformat(value.strip()[:10])
    return fallback


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
