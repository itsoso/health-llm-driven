"""Delivery status contract for Agent-created reminders.

This is intentionally a capability/claim contract, not a delivery receipt.
The backend can confirm reminder creation and Watch summary projection; it
cannot confirm Apple Watch notification display without a client-side receipt.
"""
from copy import deepcopy
from typing import Any, Dict


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


def reminder_delivery_status() -> Dict[str, Any]:
    """Return a fresh reminder delivery-status payload for API responses."""
    return deepcopy(_REMINDER_DELIVERY_STATUS)
