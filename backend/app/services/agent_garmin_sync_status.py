"""Read an owned Garmin job receipt and date availability without starting work.

Celery SUCCESS is transport completion, not the Garmin business outcome. Date
rows and credential timestamps never establish that a particular job succeeded.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import UUID

from app.services.agent_query_window import (
    QueryWindow,
    parse_query_window,
    read_calendar_health_query,
)

_JOB_VERSION = "garmin-sync-job.v1"
_TASK_NAME = "app.tasks.garmin_sync.sync_user_garmin_data"
_MAX_HISTORY_MESSAGES = 50


def _validate_owner(owner_id: int) -> None:
    if isinstance(owner_id, bool) or not isinstance(owner_id, int) or owner_id <= 0:
        raise ValueError("garmin_sync_owner_required")


@dataclass(frozen=True)
class VerifiedGarminSyncJob:
    """Server-only context, constructed after enqueue or from owned assistant meta.

    This object is not a tool input or a user-supplied authorization token.
    Callers must never construct it from model arguments or arbitrary JSON.
    """

    owner_id: int
    job_id: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        _validate_owner(self.owner_id)
        if not isinstance(self.job_id, str):
            raise ValueError("garmin_sync_job_id_invalid")
        try:
            canonical = str(UUID(self.job_id))
        except (ValueError, AttributeError) as exc:
            raise ValueError("garmin_sync_job_id_invalid") from exc
        if self.job_id != canonical:
            raise ValueError("garmin_sync_job_id_invalid")
        if (
            not isinstance(self.submitted_at, datetime)
            or self.submitted_at.utcoffset() is None
        ):
            raise ValueError("garmin_sync_job_timestamp_invalid")

    def as_metadata(self) -> dict[str, str]:
        """Only opaque receipt metadata; persist under assistant meta.garmin_sync_job."""
        return {
            "version": _JOB_VERSION,
            "task_name": _TASK_NAME,
            "job_id": self.job_id,
            "submitted_at": self.submitted_at.isoformat(),
        }


def latest_owned_garmin_sync_job(
    db, user_id: int, conversation_id: int
) -> VerifiedGarminSyncJob | None:
    """Bounded owner join; user messages and other conversations grant no access."""
    _validate_owner(user_id)
    if (
        isinstance(conversation_id, bool)
        or not isinstance(conversation_id, int)
        or conversation_id <= 0
    ):
        raise ValueError("garmin_sync_conversation_required")
    from app.models.agent_conversation import AgentConversation, AgentMessage

    with db.no_autoflush:
        messages = (
            db.query(AgentMessage)
            .join(
                AgentConversation, AgentMessage.conversation_id == AgentConversation.id
            )
            .filter(
                AgentConversation.user_id == user_id,
                AgentConversation.id == conversation_id,
                AgentMessage.role == "assistant",
            )
            .order_by(AgentMessage.created_at.desc(), AgentMessage.id.desc())
            .limit(_MAX_HISTORY_MESSAGES)
            .all()
        )
    for message in messages:
        if not isinstance(message.meta, dict) or "garmin_sync_job" not in message.meta:
            continue
        raw = message.meta["garmin_sync_job"]
        # Do not silently select an older job when the newest receipt is invalid.
        if (
            not isinstance(raw, dict)
            or raw.get("version") != _JOB_VERSION
            or raw.get("task_name") != _TASK_NAME
        ):
            return None
        try:
            timestamp = datetime.fromisoformat(raw["submitted_at"])
            return VerifiedGarminSyncJob(user_id, raw["job_id"], timestamp)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _read_task_meta(job_id: str) -> dict[str, Any]:
    from app.celery_app import celery_app

    # A single non-polling result read. Never join/wait/get(), enqueue or retry a job.
    return celery_app.backend.get_task_meta(job_id, cache=False)


def _job_observation(meta: Any, job_id: str) -> tuple[str, str, str]:
    if not isinstance(meta, dict):
        return "unknown", "UNKNOWN", "job_backend_result_invalid"
    if meta.get("task_id", job_id) != job_id:
        return "unknown", "UNKNOWN", "job_identity_mismatch"
    state = meta.get("status")
    if not isinstance(state, str):
        return "unknown", "UNKNOWN", "job_backend_result_invalid"
    if state in {"RECEIVED", "QUEUED"}:
        return "queued", state, "job_queue_observed"
    if state in {"STARTED", "RETRY"}:
        return (
            "running",
            state,
            "job_retry_observed" if state == "RETRY" else "job_running_observed",
        )
    if state in {"FAILURE", "REVOKED"}:
        return "failed", state, "job_worker_failed"
    if state != "SUCCESS":
        # PENDING also means absent/expired result; track_started is not enabled.
        return (
            "unknown",
            "PENDING" if state == "PENDING" else "UNKNOWN",
            "job_state_unavailable",
        )
    result = meta.get("result")
    if not isinstance(result, dict):
        return "unknown", state, "job_business_result_invalid"
    if not isinstance(result.get("status"), str):
        return "unknown", state, "job_business_result_invalid"
    if result.get("status") in {"error", "failed", "skipped", "partial"}:
        return "failed", state, "job_business_failed"
    counts = [
        result.get(key) for key in ("success_count", "error_count", "activities_count")
    ]
    if result.get("status") != "success" or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts
    ):
        return "unknown", state, "job_business_result_invalid"
    if result["error_count"]:
        return "failed", state, "job_partial_failure"
    return "completed", state, "job_reported_success"


def read_garmin_sync_status(
    db,
    user_id: int,
    conversation_id: int | None,
    window: QueryWindow,
    *,
    current_job: VerifiedGarminSyncJob | None = None,
    result_reader: Callable[[str], Any] | None = None,
    include_date_availability: bool = False,
    allow_history: bool = True,
) -> dict[str, Any]:
    """Observe one server-correlated job and independently query owned date rows.

    current_job is for the current turn before its assistant message is saved.
    Otherwise only the current owned conversation is searched, with a bounded
    history. No raw model-supplied job id is accepted. DB failures propagate;
    backend failures are explicit retryable unknown observations, never success.
    """
    _validate_owner(user_id)
    window = parse_query_window(window.as_dict())
    if current_job is not None and (
        not isinstance(current_job, VerifiedGarminSyncJob)
        or current_job.owner_id != user_id
    ):
        raise ValueError("garmin_sync_job_owner_mismatch")
    with db.no_autoflush if db is not None else nullcontext():
        job = current_job or (
            latest_owned_garmin_sync_job(db, user_id, conversation_id)
            if allow_history and conversation_id is not None
            else None
        )
        data = (
            read_calendar_health_query(db, user_id, "sleep", window)
            if include_date_availability
            else {"availability": "not_requested"}
        )
    availability = data.get("availability")
    if availability not in {"available", "partial", "no_data", "not_requested"}:
        raise ValueError("garmin_sync_data_availability_invalid")
    output: dict[str, Any] = {
        "version": "garmin-sync-status.v1",
        "status": "unknown",
        "observed_state": "UNKNOWN",
        "submission_status": "accepted" if job else "unverified",
        "job_success_verified": False,
        "reason_code": "owned_job_not_found",
        "retryable": False,
        "data": {
            "dimension": "sleep",
            "window": window.as_dict(),
            "availability": availability,
            "attributed_to_job": False,
            "source_scope": "owned_calendar_sleep_records"
            if include_date_availability
            else "not_requested",
        },
        "limitations": [
            "date_rows_do_not_prove_job_success",
            "target_date_not_attested_by_job",
            "activity_coverage_not_attested",
            "pending_may_mean_expired_result",
            "date_rows_may_include_other_sources",
        ],
    }
    if job is None:
        output["limitations"].append(
            "only_recent_owned_conversation_receipts_searched"
            if allow_history
            else "new_sync_submission_not_verified"
        )
        if not allow_history:
            output["reason_code"] = "new_sync_submission_unverified"
        return output
    output.update(job_id=job.job_id, submitted_at=job.submitted_at.isoformat())
    try:
        meta = (result_reader or _read_task_meta)(job.job_id)
    except Exception:  # backend errors are an explicit failed observation, without private exception text
        output.update(reason_code="job_backend_unavailable", retryable=True)
        return output
    status, state, reason = _job_observation(meta, job.job_id)
    output.update(
        status=status,
        observed_state=state,
        reason_code=reason,
        job_success_verified=status == "completed",
    )
    return output
