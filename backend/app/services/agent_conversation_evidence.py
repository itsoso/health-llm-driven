"""Bounded user reports across owned conversations; never a write authority."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, func

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.services.agent_query_window import parse_query_window


MAX_CONVERSATION_RECORDS = 500
MAX_CONVERSATION_CONTENT_CHARS = 64000


def read_conversation_evidence(db, user_id, window):
    """Read stored user text by reporting date, preserving provenance and limits.

    Authentication and read authorization belong to the calling gateway. This
    adapter independently binds ownership and calendar bounds, does not inspect
    attachments or metadata, and never treats report text as instructions.
    """
    if type(user_id) is not int or user_id <= 0:
        raise ValueError("conversation_evidence_owner_required")
    window = parse_query_window(window.as_dict())
    if window.period is not None:
        raise ValueError("conversation_evidence_subday_unsupported")
    zone = ZoneInfo(window.timezone)
    try:
        after_end = window.end_date + timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("conversation_evidence_window_invalid") from exc
    # AgentMessage.created_at is timestamp-without-time-zone storing UTC.
    # Convert each local midnight separately: DST days are not always 24 hours.
    start = datetime.combine(window.start_date, time.min, zone).astimezone(UTC).replace(tzinfo=None)
    end = datetime.combine(after_end, time.min, zone).astimezone(UTC).replace(tzinfo=None)
    content_length = func.length(AgentMessage.content)
    # Do not load a single unbounded text into memory just to reject it. A NULL
    # here is never returned as partial evidence: the length check below fails.
    bounded_content = case(
        (content_length <= MAX_CONVERSATION_CONTENT_CHARS, AgentMessage.content),
        else_=None,
    )
    with db.no_autoflush:
        rows = (
            db.query(AgentMessage.id, AgentMessage.conversation_id,
                     AgentMessage.created_at, bounded_content, content_length)
            .join(AgentConversation, AgentConversation.id == AgentMessage.conversation_id)
            .filter(AgentConversation.user_id == user_id,
                    AgentMessage.role == "user",
                    AgentMessage.created_at >= start,
                    AgentMessage.created_at < end)
            .order_by(AgentMessage.created_at, AgentMessage.id)
            .limit(MAX_CONVERSATION_RECORDS + 1)
            .all()
        )
    if len(rows) > MAX_CONVERSATION_RECORDS:
        raise ValueError("conversation_evidence_row_limit_exceeded")
    if sum(row[4] for row in rows) > MAX_CONVERSATION_CONTENT_CHARS:
        raise ValueError("conversation_evidence_content_limit_exceeded")
    records = []
    for message_id, conversation_id, created_at, content, _length in rows:
        reported_at = (created_at.replace(tzinfo=UTC) if created_at.tzinfo is None
                       else created_at.astimezone(UTC))
        records.append({
            "id": message_id,
            "conversation_id": conversation_id,
            "record_date": reported_at.astimezone(zone).date().isoformat(),
            "reported_at": reported_at.isoformat(),
            "content": content,
        })
    return {
        "dimension": "conversation",
        "window": window.as_dict(),
        "availability": "available" if records else "no_data",
        "source_scope": "owned_user_message_reports",
        "records": records,
        "limitations": [
            "reported_time_not_event_time",
            "user_reports_not_verified_records",
            "images_not_read",
            "duplicates_not_multiple_events",
        ],
    }
