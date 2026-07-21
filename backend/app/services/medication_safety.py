"""Shared deterministic medication-safety precheck.

The precheck deliberately uses the caller's database session so it can see writes
from the current request/transaction.  A taken log is treated as an exposure fact
for the user's current local day even when the reusable medication definition is
inactive; this enrichment is confined to the in-memory Twin and never changes the
definition's ``is_active`` state.
"""

from contextvars import ContextVar
from datetime import UTC, datetime
import logging
from typing import Any, Callable, Iterable, TypeVar

from sqlalchemy.orm import Session

from app.agents.safety_guardian.engine import evaluate_rules_with_status
from app.agents.safety_guardian.schema import Alert, Severity
from app.models.medication import Medication, MedicationLog
from app.twin import builder as twin_builder
from app.twin.schema import HealthTwin, TwinMeta
from app.utils.timezone import get_user_today


logger = logging.getLogger(__name__)

_MEDICATION_SAFETY_CATEGORIES = {"pgx", "ddi", "dsi"}
_REDACT_DEPENDENCY_FAILURES: ContextVar[bool] = ContextVar(
    "medication_safety_redact_dependency_failures",
    default=False,
)
_T = TypeVar("_T")


class _MedicationSafetyDependencyLogFilter(logging.Filter):
    """Remove health data from dependency failures during this precheck only."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _REDACT_DEPENDENCY_FAILURES.get() and record.levelno >= logging.WARNING:
            record.msg = "[MedicationSafety] dependency failure details redacted"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


_DEPENDENCY_LOG_FILTER = _MedicationSafetyDependencyLogFilter()
for _dependency_logger_name in (
    "app.agents.safety_guardian.engine",
    "app.twin.builder",
    "app.twin._collectors",
):
    logging.getLogger(_dependency_logger_name).addFilter(_DEPENDENCY_LOG_FILTER)


def _run_with_redacted_dependency_failures(operation: Callable[[], _T]) -> _T:
    """Run a dependency while redacting only logs emitted in this context."""
    token = _REDACT_DEPENDENCY_FAILURES.set(True)
    try:
        return operation()
    finally:
        _REDACT_DEPENDENCY_FAILURES.reset(token)


def _fail_safe_advisory() -> Alert:
    """Return an explicit advisory when the safety evaluation is incomplete."""
    return Alert(
        rule_id="medication.safety_precheck_incomplete",
        category="ddi",
        severity=Severity.HIGH,
        title="用药安全预检未完成",
        message=(
            "本次用药相互作用/基因/补剂安全筛查未能完整跑完,无法确认是否存在风险。"
            "这不代表安全,只代表系统未能完成评估。"
        ),
        action=(
            "请勿据此判断为安全;新增或调整用药前请咨询医生或药师,"
            "如有不适及时就医。"
        ),
        data_citation={"reason": "precheck_partition_fill_or_eval_failure"},
        requires_medical_attention=True,
    )


def _log_failure(stage: str, user_id: int, exc: Exception) -> None:
    """Log only non-sensitive failure metadata.

    Exception messages and tracebacks can contain medication names or other health
    data, so neither is emitted here.
    """
    logger.error(
        "[MedicationSafety] precheck failed stage=%s user_id=%s exception_type=%s",
        stage,
        user_id,
        type(exc).__name__,
    )


def _today_taken_exposure(medication: Medication) -> dict[str, Any]:
    """Serialize only the fields currently consumed by DDI/PGx/DSI rules."""
    return {
        "medication_id": medication.id,
        "name": medication.name,
        "start_date": medication.start_date.isoformat() if medication.start_date else None,
        "is_active": False,
        "exposure_source": "taken_log",
    }


def _include_taken_inactive_medications(
    db: Session,
    user_id: int,
    twin: HealthTwin,
    *,
    exposure_log_ids: Iterable[int] = (),
) -> None:
    """Add logged exposures without reactivating reusable definitions.

    Today's logs preserve the existing API behavior. ``exposure_log_ids`` are
    the exact just-confirmed batch and remain authoritative across a local-day
    rollover (for example a 23:59 proposal confirmed at 00:01).
    """
    explicit_ids = tuple(sorted({
        int(log_id)
        for log_id in exposure_log_ids
        if isinstance(log_id, int) and not isinstance(log_id, bool) and log_id > 0
    }))
    today_query = db.query(MedicationLog.medication_id).filter(
        MedicationLog.user_id == user_id,
        MedicationLog.taken_date == get_user_today(db, user_id),
        MedicationLog.status == "taken",
    )
    medication_ids = {row[0] for row in today_query.distinct().all()}
    if explicit_ids:
        explicit_rows = (
            db.query(MedicationLog.medication_id)
            .filter(
                MedicationLog.user_id == user_id,
                MedicationLog.id.in_(explicit_ids),
                MedicationLog.status == "taken",
            )
            .distinct()
            .all()
        )
        medication_ids.update(row[0] for row in explicit_rows)

    if not medication_ids:
        return
    medications = (
        db.query(Medication)
        .filter(
            Medication.user_id == user_id,
            Medication.is_active.is_(False),
            Medication.id.in_(medication_ids),
        )
        .order_by(Medication.id.asc())
        .all()
    )

    present_ids = {
        item.get("medication_id")
        for item in (twin.medication.active_meds or [])
        if isinstance(item, dict)
    }
    for medication in medications:
        if medication.id not in present_ids:
            twin.medication.active_meds.append(_today_taken_exposure(medication))
            present_ids.add(medication.id)

    twin.medication.has_any = bool(twin.medication.active_meds)
    if medications:
        twin.meta.data_sources = sorted(
            set(twin.meta.data_sources) | {"medication"}
        )


def evaluate_medication_safety_alerts(
    db: Session,
    user_id: int,
    *,
    exposure_log_ids: Iterable[int] = (),
) -> list[dict[str, Any]]:
    """Evaluate and API-serialize medication PGx/DDI/DSI alerts.

    Partition or rule failure is never represented as a clean result: an additive
    HIGH advisory explicitly marks the incomplete evaluation.
    """
    twin = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(UTC)))
    evaluation_failed = False

    try:
        # A safety read is advisory to the already-validated write.  Isolate
        # DB/query failures in a SAVEPOINT so a legacy collector can never
        # unwind the caller's flushed WriteIntent, definitions, or logs.  The
        # strict collector path propagates instead of calling Session.rollback.
        with db.begin_nested():
            _run_with_redacted_dependency_failures(
                lambda: twin_builder.fill_medication_safety_partitions(
                    db, user_id, twin, raise_on_error=True
                )
            )
            _include_taken_inactive_medications(
                db,
                user_id,
                twin,
                exposure_log_ids=exposure_log_ids,
            )
    except Exception as exc:  # noqa: BLE001 - failure becomes a user-visible advisory
        _log_failure("partition_fill", user_id, exc)
        evaluation_failed = True

    alerts: list[Alert] = []
    try:
        all_alerts, failed = _run_with_redacted_dependency_failures(
            lambda: evaluate_rules_with_status(twin)
        )
        if failed > 0:
            logger.error(
                "[MedicationSafety] rules skipped user_id=%s failed_rule_count=%s",
                user_id,
                failed,
            )
            evaluation_failed = True
        alerts = [
            alert
            for alert in all_alerts
            if alert.category in _MEDICATION_SAFETY_CATEGORIES
        ]
    except Exception as exc:  # noqa: BLE001 - failure becomes a user-visible advisory
        _log_failure("rule_evaluation", user_id, exc)
        evaluation_failed = True

    if evaluation_failed:
        alerts.append(_fail_safe_advisory())

    alerts.sort(key=lambda alert: (-int(alert.severity), alert.category, alert.rule_id))
    return [alert.model_dump_for_api() for alert in alerts]
