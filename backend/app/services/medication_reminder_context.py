"""Deterministic reminder occurrence validation; no inferred dose or date writes."""

import hashlib
import json
import re
from datetime import date

from app.models.medication import MedicationLog, medication_timing_label
from app.utils.timezone import get_user_now


def medication_revision(med):
    fields = (
        "id",
        "user_id",
        "name",
        "dosage",
        "frequency",
        "reminder_times",
        "is_active",
        "start_date",
        "end_date",
        "timing_relation",
        "meal_anchor",
        "category",
    )
    raw = {key: getattr(med, key) for key in fields}
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def reminder_context(
    db,
    user_id,
    med,
    target_date: date | None,
    time: str | None,
    source_timezone: str | None = None,
):
    now = get_user_now(db, user_id)
    timezone = getattr(now.tzinfo, "key", None) or (
        "Asia/Shanghai" if now.utcoffset().total_seconds() == 28800 else str(now.tzinfo)
    )
    resolved_date = target_date or now.date()
    log = None
    if time:
        log = (
            db.query(MedicationLog)
            .filter(
                MedicationLog.user_id == user_id,
                MedicationLog.medication_id == med.id,
                MedicationLog.taken_date == resolved_date,
                MedicationLog.taken_time == time,
            )
            .first()
        )
    reason = None
    if not target_date:
        reason = "date_confirmation_required"
    elif not time:
        reason = "time_required"
    elif source_timezone is not None and source_timezone != timezone:
        reason = "timezone_mismatch"
    elif not med.is_active:
        reason = "inactive"
    elif not (med.name or "").strip() or re.match(
        r"^(?:记录(?:一下|下来)?[\s：:]|不要|请勿|不建议|提醒我|备注[：:]|补剂[：:])",
        med.name.strip(),
    ):
        reason = "invalid_medication_name"
    elif not (med.dosage or "").strip():
        reason = "dose_missing"
    elif time not in (med.reminder_times or []):
        reason = "schedule_changed"
    elif resolved_date > now.date() or (
        resolved_date == now.date() and time > now.strftime("%H:%M")
    ):
        reason = "future_occurrence"
    elif (med.start_date and resolved_date < med.start_date) or (
        med.end_date and resolved_date > med.end_date
    ):
        reason = "outside_course"
    elif log:
        reason = "already_recorded"
    return {
        "user_id": user_id,
        "timezone": timezone,
        "today_date": str(now.date()),
        "date": str(resolved_date),
        "time": time,
        "requires_date_confirmation": target_date is None,
        "revision": medication_revision(med),
        "medication": {
            "id": med.id,
            "user_id": user_id,
            "name": med.name,
            "dosage": med.dosage,
            "frequency": med.frequency,
            "is_active": med.is_active,
            "reminder_times": med.reminder_times or [],
            "timing_label": medication_timing_label(
                med.timing_relation, med.meal_anchor
            ),
            "safety_alerts": [],
        },
        "log": {
            "id": log.id,
            "medication_id": log.medication_id,
            "taken_date": str(log.taken_date),
            "taken_time": log.taken_time,
            "status": log.status,
        }
        if log
        else None,
        "actionable": reason is None,
        "reason": reason,
    }
