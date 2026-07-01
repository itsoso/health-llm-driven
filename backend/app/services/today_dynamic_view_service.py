"""Aheng-composed DynamicView contract for Mobile Today."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.services import agenda_service, daily_artifact_service

GENERATED_BY = "aheng_today_view_v1"
SURFACE = "mobile.today"
DEFAULT_TTL_SECONDS = 60


def build_today_dynamic_view(
    db: Session,
    user_id: int,
    *,
    trigger: str = "open",
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the first DynamicView slice for the Mobile Today tab.

    This only composes governed runtime projections. It does not introduce a
    write path or let generated content choose arbitrary endpoints.
    """
    generated_at = datetime.now(UTC)
    artifact = daily_artifact_service.build_daily_artifact(db, user_id, followup_within_days=7)
    runtime = agenda_service.runtime_range_view(db, user_id, days=7, max_items_per_day=3)
    context_hash = _context_hash(artifact, runtime, trigger, client_context or {})
    artifact_date = str(artifact.get("artifact_date") or runtime.get("start") or generated_at.date())
    safety_boundary = (
        artifact.get("safety_boundary")
        or _runtime_safety_boundary(runtime)
        or daily_artifact_service.DEFAULT_SAFETY_BOUNDARY
    )

    return {
        "view_id": f"today:{artifact_date}:{context_hash[:12]}",
        "surface": SURFACE,
        "trigger": trigger,
        "generated_by": GENERATED_BY,
        "generated_at": generated_at.isoformat(),
        "expires_at": (generated_at + timedelta(seconds=DEFAULT_TTL_SECONDS)).isoformat(),
        "context_hash": context_hash,
        "safety_boundary": safety_boundary,
        "sections": _compose_sections(artifact, runtime),
    }


def _compose_sections(artifact: dict[str, Any], runtime: dict[str, Any]) -> list[dict[str, Any]]:
    used_keys: set[str] = set()
    sections: list[dict[str, Any]] = []

    daily_card = _daily_artifact_card(artifact)
    sections.append({
        "slot": "hero",
        "priority": 100,
        "title": "今日状态",
        "cards": [daily_card],
    })
    used_keys.update(_card_dedupe_keys(daily_card))

    runtime_card = _runtime_agenda_card(runtime)
    if runtime_card and not used_keys.intersection(_card_dedupe_keys(runtime_card)):
        sections.append({
            "slot": "runtime",
            "priority": 80,
            "title": "健康运行时",
            "cards": [runtime_card],
        })

    return sections


def _daily_artifact_card(artifact: dict[str, Any]) -> dict[str, Any]:
    action = artifact.get("top_action") if isinstance(artifact.get("top_action"), dict) else {}
    artifact_date = str(artifact.get("artifact_date") or "unknown")
    action_id = _safe_token(action.get("id")) or "empty"
    dedupe_key = _primary_dedupe_key(action)
    render = {
        "atom": "daily_artifact",
        "priority": 100,
        "dedupe_key": dedupe_key,
        "dedupe_keys": _action_dedupe_keys(action),
        "reason": "primary_today_action",
    }
    return {
        "id": f"daily-artifact:{artifact_date}:{action_id}",
        "type": "daily_artifact",
        "data": artifact,
        "render": render,
    }


def _runtime_agenda_card(runtime: dict[str, Any]) -> dict[str, Any] | None:
    data = _runtime_agenda_card_data(runtime)
    action = _runtime_action(runtime)
    if not action and not data.get("days"):
        return None
    start = _safe_token(runtime.get("start")) or "unknown"
    action_id = _safe_token(action.get("id")) or "empty"
    return {
        "id": f"runtime-agenda:{start}:{action_id}",
        "type": "runtime_agenda",
        "data": data,
        "actions": [_open_runtime_agenda_action()],
        "render": {
            "atom": "runtime_agenda",
            "priority": 80,
            "dedupe_key": _primary_dedupe_key(action),
            "dedupe_keys": _action_dedupe_keys(action),
            "reason": "next_runtime_action",
        },
    }


def _runtime_agenda_card_data(runtime: dict[str, Any]) -> dict[str, Any]:
    action = _runtime_action(runtime)
    runtime_context = action.get("runtime_context") if isinstance(action.get("runtime_context"), dict) else {}
    root_context = runtime.get("runtime_context") if isinstance(runtime.get("runtime_context"), dict) else {}
    verification_window = (
        runtime_context.get("verification_window")
        if isinstance(runtime_context.get("verification_window"), dict)
        else {}
    )
    metrics = [
        str(metric)
        for metric in verification_window.get("metrics") or []
        if isinstance(metric, (str, int, float)) and str(metric).strip()
    ][:3]

    return {
        "mode": runtime.get("mode"),
        "generated_by": runtime.get("generated_by"),
        "horizon_days": runtime.get("horizon_days"),
        "start": runtime.get("start"),
        "end": runtime.get("end"),
        "safety_boundary": root_context.get("safety_boundary") or runtime_context.get("safety_boundary"),
        "next_action": {
            "id": action.get("id"),
            "title": action.get("title"),
            "kind": action.get("type"),
            "time_window": action.get("time_window"),
            "priority_tier": action.get("priority_tier"),
            "current_state_summary": runtime_context.get("current_state_summary"),
            "replan_reason": runtime_context.get("replan_reason"),
            "verification_metrics": metrics,
            "verification_window_days": verification_window.get("window_days"),
        },
        "days": [
            _compact_runtime_day(day)
            for day in (runtime.get("days") or [])[:7]
            if isinstance(day, dict)
        ],
    }


def _runtime_action(runtime: dict[str, Any]) -> dict[str, Any]:
    action = runtime.get("next_action") if isinstance(runtime.get("next_action"), dict) else None
    if action is None:
        for day in runtime.get("days") or []:
            if isinstance(day, dict) and isinstance(day.get("next_action"), dict):
                action = day["next_action"]
                break
    return action if isinstance(action, dict) else {}


def _compact_runtime_day(day: dict[str, Any]) -> dict[str, Any]:
    next_action = day.get("next_action") if isinstance(day.get("next_action"), dict) else None
    item_count = 0
    for window in day.get("time_windows") or []:
        if isinstance(window, dict) and isinstance(window.get("items"), list):
            item_count += len(window["items"])
    return {
        "date": day.get("date"),
        "next_action_title": next_action.get("title") if next_action else None,
        "items_count": item_count,
    }


def _open_runtime_agenda_action() -> dict[str, Any]:
    return {
        "id": "open-runtime-agenda",
        "label": "查看7天计划",
        "action": "route.open",
        "payload": {"route": "/agenda"},
        "style": "primary",
    }


def _runtime_safety_boundary(runtime: dict[str, Any]) -> str | None:
    context = runtime.get("runtime_context")
    if isinstance(context, dict) and context.get("safety_boundary"):
        return str(context["safety_boundary"])
    return None


def _card_dedupe_keys(card: dict[str, Any]) -> set[str]:
    render = card.get("render") if isinstance(card.get("render"), dict) else {}
    keys = render.get("dedupe_keys")
    if isinstance(keys, list):
        return {str(key) for key in keys if str(key).strip()}
    key = render.get("dedupe_key")
    return {str(key)} if key else set()


def _primary_dedupe_key(action: dict[str, Any]) -> str | None:
    keys = _action_dedupe_keys(action)
    return keys[0] if keys else None


def _action_dedupe_keys(action: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    action_id = _safe_token(action.get("id"))
    if action_id:
        keys.append(f"action:{action_id}")
    title = _title_key(action.get("title"))
    if title:
        keys.append(f"title:{title}")
    return keys


def _safe_token(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    return re.sub(r"[^A-Za-z0-9_.:-]+", "-", text).strip("-") or None


def _title_key(value: Any) -> str | None:
    text = str(value).strip().lower() if value is not None else ""
    if not text:
        return None
    return re.sub(r"[\s:：,，.。;；]+", "", text) or None


def _context_hash(
    artifact: dict[str, Any],
    runtime: dict[str, Any],
    trigger: str,
    client_context: dict[str, Any],
) -> str:
    payload = {
        "trigger": trigger,
        "artifact_date": artifact.get("artifact_date"),
        "artifact_generated_by": artifact.get("generated_by"),
        "artifact_source": artifact.get("source"),
        "top_action_id": (artifact.get("top_action") or {}).get("id")
        if isinstance(artifact.get("top_action"), dict)
        else None,
        "runtime_start": runtime.get("start"),
        "runtime_end": runtime.get("end"),
        "runtime_generated_by": runtime.get("generated_by"),
        "runtime_next_action_id": (runtime.get("next_action") or {}).get("id")
        if isinstance(runtime.get("next_action"), dict)
        else None,
        "client_capabilities": client_context.get("client_capabilities"),
        "timezone": client_context.get("timezone"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
