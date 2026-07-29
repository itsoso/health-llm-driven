"""Owner-scoped reconciliation for Runtime-managed write operations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models.agent_runtime import AgentRun, AgentToolOperation
from app.models.daily_health import DietRecord
from app.models.medical_exam import MedicalExam
from app.services.agent_runtime_identity import runtime_hmac_digest


AUTO_RECONCILIATION_RESOURCE_TYPES = frozenset(
    {"diet_record", "medical_exam"}
)


def runtime_operation_source_fingerprint(operation_id: str) -> str:
    """Build the opaque persisted identity used to reconcile a local write."""
    normalized = str(operation_id or "").strip()
    if not normalized:
        raise ValueError("runtime_operation_id_required")
    return runtime_hmac_digest(
        "runtime-operation-source-fingerprint-v1",
        normalized,
    )


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
    if not resource_id.isdigit():
        return False
    model = {
        "diet_record": DietRecord,
        "medical_exam": MedicalExam,
    }.get(resource_type)
    if model is None:
        return False
    return db.query(model.id).filter(
        model.id == int(resource_id),
        model.user_id == run.user_id,
    ).first() is not None


def resolve_tool_operation(
    db: Session,
    *,
    run: AgentRun,
    operation: AgentToolOperation,
    now: datetime,
    grace_seconds: int,
) -> OperationReconciliationDecision:
    if (
        operation.tool_name == "health_record"
        and operation.resource_type == "diet_record"
    ):
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
        effect_resource_type = "diet_record"
    elif (
        operation.tool_name == "upload_medical_exam_text"
        and operation.resource_type == "medical_exam"
    ):
        record = db.query(MedicalExam.id).filter(
            MedicalExam.user_id == run.user_id,
            MedicalExam.source_fingerprint
            == runtime_operation_source_fingerprint(operation.operation_id),
        ).first()
        effect_resource_type = "medical_exam"
    else:
        return OperationReconciliationDecision(
            disposition="unknown",
            reason_code="unsupported_reconciliation_resource",
        )

    if record is not None:
        return OperationReconciliationDecision(
            disposition="verified_effect",
            reason_code="reconciled_effect_verified",
            resource_type=effect_resource_type,
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
        resource_type=effect_resource_type,
    )
