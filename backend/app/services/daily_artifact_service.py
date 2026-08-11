"""Daily Artifact projection and telemetry.

The artifact is a compact presentation contract over the rolling health
runtime: one top action, at most three evidence cards, and append-only event
telemetry.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from urllib.parse import quote

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
    artifact_date: date | str | None = None,
    followup_within_days: int = 7,
    top_action_id: str | None = None,
) -> dict[str, Any]:
    """Build a single-action artifact from the runtime projection."""
    runtime_days = max(1, min(int(followup_within_days or 7), 14))
    runtime_payload = agenda_service.runtime_range_view(
        db,
        user_id,
        days=runtime_days,
        max_items_per_day=3,
    )
    runtime_artifact_date = _coerce_date(
        runtime_payload.get("start"),
        fallback=get_user_today(db, user_id),
    )
    requested_artifact_date = None
    if artifact_date:
        requested_artifact_date = _coerce_date(
            artifact_date,
            fallback=runtime_artifact_date,
        )
    if requested_artifact_date and requested_artifact_date != runtime_artifact_date:
        raise ValueError("daily_artifact_date_not_found")

    requested_top_action_id = (top_action_id or "").strip() or None
    top_action = runtime_payload.get("next_action")

    if not isinstance(top_action, dict):
        if requested_top_action_id:
            raise ValueError("daily_artifact_action_not_found")
        return _empty_artifact(runtime_artifact_date, runtime_payload)

    action_view = _top_action_view(top_action)
    if requested_top_action_id and action_view.get("id") != requested_top_action_id:
        raise ValueError("daily_artifact_action_not_found")

    evidence = _evidence_cards(top_action)[:3]
    safety_boundary = (
        top_action.get("claim_boundary")
        or _runtime_context(top_action, runtime_payload).get("safety_boundary")
        or DEFAULT_SAFETY_BOUNDARY
    )

    return {
        "artifact_date": runtime_artifact_date.isoformat(),
        "generated_by": "daily_artifact_runtime_v1",
        "source": _runtime_source(runtime_payload),
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


def _empty_artifact(artifact_date: date, runtime_payload: dict[str, Any]) -> dict[str, Any]:
    runtime_context = runtime_payload.get("runtime_context")
    safety_boundary = DEFAULT_SAFETY_BOUNDARY
    if isinstance(runtime_context, dict) and runtime_context.get("safety_boundary"):
        safety_boundary = str(runtime_context["safety_boundary"])
    return {
        "artifact_date": artifact_date.isoformat(),
        "generated_by": "daily_artifact_runtime_v1",
        "source": _runtime_source(runtime_payload),
        "empty_state": True,
        "state": {
            "label": "暂无今日重点",
            "tone": "neutral",
            "summary": "今天暂无需要突出的健康行动。",
        },
        "top_action": None,
        "evidence": [],
        "confidence": "low",
        "freshness": {"status": "limited", "sources": ["agenda.runtime_range"]},
        "safety_boundary": safety_boundary,
    }


def _top_action_view(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    trajectory = item.get("trajectory_context") if isinstance(item.get("trajectory_context"), dict) else None
    target_state_variable = item.get("target_state_variable") or (trajectory or {}).get("state_variable")
    verification_signal = (
        item.get("verification_signal")
        or (trajectory or {}).get("verification_signal")
        or target_state_variable
    )
    completion_action = {
        "method": "POST",
        "endpoint": "/api/v1/agenda/complete",
        "enabled": bool(item.get("can_complete")),
        "source": source,
    }
    if source.get("object_type") == "daily_plan_action":
        action_id = quote(str(source.get("object_id") or "").strip(), safe="._-")
        completion_action.update({
            "endpoint": f"/api/v1/daily-plan/actions/{action_id}/events",
            "payload": {"event_type": "completed"},
        })
    view = {
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
        "trajectory_context": trajectory,
        "target_state_variable": target_state_variable,
        "verification_signal": verification_signal,
        "claim_boundary": item.get("claim_boundary"),
        "actions": {
            "complete": completion_action,
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
    runtime_context = item.get("runtime_context")
    if isinstance(runtime_context, dict) and runtime_context:
        view["runtime_context"] = runtime_context
    return view


def _evidence_cards(item: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    source_kind = source.get("object_type") or "agenda"
    runtime_context = item.get("runtime_context") if isinstance(item.get("runtime_context"), dict) else {}

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
    if isinstance(verify_by, dict) or isinstance(runtime_context, dict):
        if not isinstance(verify_by, dict):
            verify_by = {}
        runtime_window = runtime_context.get("verification_window") if isinstance(runtime_context, dict) else {}
        if not isinstance(runtime_window, dict):
            runtime_window = {}
        metrics = [str(m) for m in (verify_by.get("metrics") or []) if m][:3]
        if not metrics:
            metrics = [str(m) for m in (runtime_window.get("metrics") or []) if m][:3]
        if metrics:
            cards.append({
                "kind": "verification",
                "label": "Verification",
                "summary": "后续用这些信号验证是否有效。",
                "metrics": metrics,
                "window_days": verify_by.get("window_days")
                or (verify_by.get("trajectory") or {}).get("verification_window_days"),
                "replan_reason": runtime_context.get("replan_reason") if isinstance(runtime_context, dict) else None,
            })
            if cards[-1]["window_days"] is None:
                cards[-1]["window_days"] = runtime_window.get("window_days")

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
    sources.append("agenda.runtime_range")
    return {
        "status": "fresh" if evidence else "limited",
        "sources": [source for source in sources if source],
    }


def _runtime_context(item: dict[str, Any], runtime_payload: dict[str, Any]) -> dict[str, Any]:
    item_context = item.get("runtime_context")
    if isinstance(item_context, dict):
        return item_context
    payload_context = runtime_payload.get("runtime_context")
    if isinstance(payload_context, dict):
        return payload_context
    return {}


def _runtime_source(runtime_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "agenda.runtime_range",
        "runtime_generated_by": runtime_payload.get("generated_by"),
        "mode": runtime_payload.get("mode"),
        "horizon_days": runtime_payload.get("horizon_days"),
        "start": runtime_payload.get("start"),
        "end": runtime_payload.get("end"),
        "source_count": _runtime_item_count(runtime_payload),
    }


def _runtime_item_count(runtime_payload: dict[str, Any]) -> int:
    count = 0
    days = runtime_payload.get("days")
    if not isinstance(days, list):
        return count
    for day in days:
        if not isinstance(day, dict):
            continue
        windows = day.get("time_windows")
        if not isinstance(windows, list):
            continue
        for window in windows:
            if not isinstance(window, dict):
                continue
            items = window.get("items")
            if isinstance(items, list):
                count += len(items)
    return count


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
