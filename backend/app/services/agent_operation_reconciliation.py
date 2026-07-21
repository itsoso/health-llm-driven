"""Owner-scoped reconciliation for Runtime-managed write operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.agent_runtime import AgentRun, AgentToolOperation
from app.models.daily_health import DietRecord


AUTO_RECONCILIATION_RESOURCE_TYPES = frozenset({"diet_record"})


@dataclass(frozen=True, slots=True)
class OperationReconciliationDecision:
    disposition: str
    reason_code: str
    resource_type: str | None = None
    resource_id: str | None = None


def verify_resource_owner(
    db: Session,
    *,
    run: AgentRun,
    resource_type: str,
    resource_id: str,
) -> bool:
    """Verify an opaque receipt belongs to the Run owner; unsupported types fail closed."""
    if resource_type != "diet_record" or not resource_id.isdigit():
        return False
    return db.query(DietRecord.id).filter(
        DietRecord.id == int(resource_id),
        DietRecord.user_id == run.user_id,
    ).first() is not None


def resolve_tool_operation(
    db: Session,
    *,
    run: AgentRun,
    operation: AgentToolOperation,
    now: datetime,
    grace_seconds: int,
) -> OperationReconciliationDecision:
    if operation.tool_name != "health_record" or operation.resource_type != "diet_record":
        return OperationReconciliationDecision(
            disposition="unknown",
            reason_code="unsupported_reconciliation_resource",
        )

    record = db.query(DietRecord.id).filter(
        DietRecord.user_id == run.user_id,
        (
            (DietRecord.client_action_id == operation.operation_id)
            | DietRecord.client_action_id.startswith(
                f"{operation.operation_id}|",
                autoescape=True,
            )
        ),
    ).first()
    if record is not None:
        return OperationReconciliationDecision(
            disposition="verified_effect",
            reason_code="reconciled_effect_verified",
            resource_type="diet_record",
            resource_id=str(record.id),
        )

    observed_at = operation.finished_at or operation.created_at
    if observed_at is None:
        return OperationReconciliationDecision(
            disposition="unknown",
            reason_code="operation_timestamp_missing",
        )
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    if now < observed_at + timedelta(seconds=grace_seconds):
        return OperationReconciliationDecision(
            disposition="unknown",
            reason_code="reconciliation_grace_period",
        )
    return OperationReconciliationDecision(
        disposition="verified_no_effect",
        reason_code="reconciled_no_effect",
        resource_type="diet_record",
    )
