"""Delivery status contract for Agent-created reminders.

This is intentionally a capability/claim contract, not a delivery receipt.
The backend can confirm reminder creation and Watch summary projection; it
cannot confirm Apple Watch notification display without a client-side receipt.
"""
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, Optional


_REMINDER_DELIVERY_STATUS: Dict[str, Any] = {
    "agent_claim": "created_not_device_delivered",
    "iphone_notification": {
        "route": "smart_reminder_scheduler",
        "status": "will_attempt_when_due",
        "delivery_confirmed": False,
    },
    "watch": {
        "route": "watch_summary_due_item",
        "status": "visible_when_watch_summary_refreshes",
        "delivery_confirmed": False,
        "push_mirror": "depends_on_ios_watch_settings",
    },
}


def _watch_visible_receipt(
    db: Any,
    *,
    user_id: Optional[int],
    reminder_id: Optional[int],
    since: Optional[datetime],
) -> Any:
    if db is None or user_id is None or reminder_id is None:
        return None
    from app.models.client_event import ClientEvent

    reminder_id_s = str(reminder_id)
    action_id = f"agenda-smart_reminder-{reminder_id_s}"
    cutoff = since or (datetime.now(UTC) - timedelta(hours=24))
    rows = (
        db.query(ClientEvent)
        .filter(
            ClientEvent.user_id == user_id,
            ClientEvent.event_name == "watch_smart_reminder_visible",
            ClientEvent.created_at >= cutoff,
        )
        .order_by(ClientEvent.created_at.desc())
        .limit(50)
        .all()
    )
    for event in rows:
        meta = event.meta or {}
        if not isinstance(meta, dict):
            continue
        if str(meta.get("action_id") or "") == action_id:
            return event
        if str(meta.get("reminder_id") or "") == reminder_id_s:
            return event
    return None


def reminder_delivery_status(
    *,
    db: Any = None,
    user_id: Optional[int] = None,
    reminder_id: Optional[int] = None,
    since: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return reminder delivery status, upgrading when Watch visibility is observed."""
    status = deepcopy(_REMINDER_DELIVERY_STATUS)
    receipt = _watch_visible_receipt(
        db,
        user_id=user_id,
        reminder_id=reminder_id,
        since=since,
    )
    if receipt is None:
        return status

    created_at = receipt.created_at
    if isinstance(created_at, datetime) and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    status["agent_claim"] = "created_watch_summary_visible"
    status["watch"].update({
        "status": "visible_on_watch_summary",
        "delivery_confirmed": True,
        "receipt_type": "watch_summary_visible",
        "notification_delivery_confirmed": False,
        "receipt_event_id": receipt.id,
        "confirmed_at": created_at.isoformat() if isinstance(created_at, datetime) else None,
    })
    return status
