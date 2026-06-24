"""Service helpers for the generic Rokid operation ledger."""
from datetime import UTC, datetime
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models.client_event import ClientEvent
from app.models.rokid_operation import RokidOperation
from app.schemas.rokid_operation import (
    RokidDiagnosticUpload,
    RokidOperationCreate,
    RokidOperationEventCreate,
    RokidOperationTraceEventResponse,
    TERMINAL_OPERATION_STATES,
)

ROKID_OPERATION_EVENT_NAME = "rokid_operation_event"
ROKID_DIAGNOSTIC_EVENT_NAME = "rokid_diagnostic_snapshot"

ENTITY_REF_ID_PAYLOAD_KEYS = {
    "visual_input_event_id": "visual_input_event_ids",
    "visual_event_id": "visual_input_event_ids",
    "meal_session_id": "meal_session_ids",
    "write_intent_id": "write_intent_ids",
    "diet_record_id": "diet_record_ids",
    "rokid_pushup_session_id": "rokid_pushup_session_ids",
    "pushup_session_id": "rokid_pushup_session_ids",
    "agent_audit_log_id": "agent_audit_log_ids",
}


def new_operation_id() -> str:
    return f"rokid-{uuid.uuid4().hex}"


def _now() -> datetime:
    return datetime.now(UTC)


def _append_entity_ref(operation: RokidOperation, key: str, value: Any) -> None:
    refs = dict(operation.entity_refs or {})
    values = refs.get(key)
    if not isinstance(values, list):
        values = []
    if value not in values:
        values.append(value)
    refs[key] = values
    operation.entity_refs = refs


def _entity_ref_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _backfill_entity_refs_from_event_payload(
    operation: RokidOperation,
    payload: dict[str, Any] | None,
) -> None:
    if not isinstance(payload, dict):
        return

    for payload_key, ref_key in ENTITY_REF_ID_PAYLOAD_KEYS.items():
        ref_id = _entity_ref_int(payload.get(payload_key))
        if ref_id is not None:
            _append_entity_ref(operation, ref_key, ref_id)

    target_type = payload.get("target_type")
    target_id = _entity_ref_int(payload.get("target_id"))
    if isinstance(target_type, str) and target_type.strip() and target_id is not None:
        _append_entity_ref(
            operation,
            "target_refs",
            {
                "target_type": target_type.strip(),
                "target_id": target_id,
            },
        )


def get_owned_operation(
    db: Session,
    *,
    operation_id: str,
    user_id: int,
) -> RokidOperation | None:
    return (
        db.query(RokidOperation)
        .filter(
            RokidOperation.operation_id == operation_id,
            RokidOperation.user_id == user_id,
        )
        .first()
    )


def create_or_update_operation(
    db: Session,
    *,
    user_id: int,
    body: RokidOperationCreate,
) -> RokidOperation:
    operation_id = body.operation_id or new_operation_id()
    existing = get_owned_operation(db, operation_id=operation_id, user_id=user_id)
    if existing:
        existing.operation_type = body.type
        existing.state = body.state
        existing.primary_surface = body.primary_surface
        existing.summary = body.summary
        existing.last_error_code = body.last_error_code
        existing.meta = body.meta
        existing.entity_refs = body.entity_refs if body.entity_refs is not None else existing.entity_refs
        if body.write_intent_id is not None:
            existing.write_intent_id = body.write_intent_id
        existing.updated_at = _now()
        if body.state in TERMINAL_OPERATION_STATES and existing.finished_at is None:
            existing.finished_at = _now()
        return existing

    operation = RokidOperation(
        operation_id=operation_id,
        user_id=user_id,
        operation_type=body.type,
        state=body.state,
        primary_surface=body.primary_surface,
        summary=body.summary,
        last_error_code=body.last_error_code,
        meta=body.meta,
        entity_refs=body.entity_refs,
        write_intent_id=body.write_intent_id,
        finished_at=_now() if body.state in TERMINAL_OPERATION_STATES else None,
    )
    db.add(operation)
    return operation


def _event_response(event: ClientEvent) -> RokidOperationTraceEventResponse:
    meta = event.meta or {}
    occurred_at = meta.get("occurred_at")
    return RokidOperationTraceEventResponse(
        id=event.id,
        operation_id=str(meta.get("operation_id") or ""),
        user_id=event.user_id,
        event_type=str(meta.get("event_type") or event.event_name),
        phase=meta.get("phase"),
        severity=str(meta.get("severity") or "info"),
        message=meta.get("message"),
        payload=meta.get("payload"),
        occurred_at=occurred_at or event.created_at,
        created_at=event.created_at,
    )


def add_operation_event(
    db: Session,
    *,
    operation: RokidOperation,
    body: RokidOperationEventCreate,
) -> ClientEvent:
    occurred_at = body.occurred_at or _now()
    event = ClientEvent(
        user_id=operation.user_id,
        event_name=ROKID_OPERATION_EVENT_NAME,
        meta={
            "operation_id": operation.operation_id,
            "event_type": body.event_type,
            "phase": body.phase,
            "severity": body.severity,
            "message": body.message,
            "payload": body.payload,
            "occurred_at": occurred_at,
        },
        created_at=occurred_at,
    )
    if body.state:
        operation.state = body.state
        if body.state in TERMINAL_OPERATION_STATES:
            operation.finished_at = occurred_at
    operation.updated_at = _now()
    db.add(event)
    db.flush()
    _append_entity_ref(operation, "client_event_ids", event.id)
    _backfill_entity_refs_from_event_payload(operation, body.payload)
    return event


def add_diagnostic_event(
    db: Session,
    *,
    operation: RokidOperation,
    body: RokidDiagnosticUpload,
) -> ClientEvent:
    occurred_at = body.occurred_at or _now()
    event = ClientEvent(
        user_id=operation.user_id,
        event_name=ROKID_DIAGNOSTIC_EVENT_NAME,
        meta={
            "operation_id": operation.operation_id,
            "event_type": "diagnostic_snapshot",
            "phase": "diagnostics",
            "severity": body.severity,
            "message": body.summary,
            "payload": {
                "summary": body.summary,
                "diagnostics": body.diagnostics,
            },
            "occurred_at": occurred_at,
        },
        created_at=occurred_at,
    )
    operation.updated_at = _now()
    db.add(event)
    db.flush()
    _append_entity_ref(operation, "client_event_ids", event.id)
    return event


def to_trace_event_response(event: ClientEvent) -> RokidOperationTraceEventResponse:
    return _event_response(event)


def list_operation_events(
    db: Session,
    *,
    operation_id: str,
    user_id: int,
    limit: int = 200,
) -> list[RokidOperationTraceEventResponse]:
    rows = (
        db.query(ClientEvent)
        .filter(
            ClientEvent.user_id == user_id,
            ClientEvent.event_name.in_({
                ROKID_OPERATION_EVENT_NAME,
                ROKID_DIAGNOSTIC_EVENT_NAME,
            }),
        )
        .order_by(ClientEvent.id.desc())
        .limit(max(limit * 5, limit))
        .all()
    )
    events = [
        _event_response(row)
        for row in rows
        if isinstance(row.meta, dict) and row.meta.get("operation_id") == operation_id
    ]
    return list(reversed(events[-limit:]))
