"""Behavior-free immutable contracts for Health Day Phase 1a.

This leaf is intentionally stdlib-only. It owns data shapes and construction
invariants; signing, composition, persistence, clocks, providers and logging
belong in higher layers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, is_dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum, unique
from types import UnionType
from typing import TypeAlias, Union, get_args, get_origin, get_type_hints
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


HEALTH_DAY_SHADOW_SCHEMA_VERSION = "health_day_shadow.v1"
LEGACY_OCCURRENCE_CONTEXT_SCHEMA_VERSION = "legacy_occurrence_context.v1"
SURFACE_PROJECTION_SCHEMA_VERSION = "health_day_surface_projection.v1"


@unique
class HealthDaySourceKind(StrEnum):
    PROFILE_SCHEDULE = "profile_schedule"
    DAILY_PLAN_SUBSET = "daily_plan_subset"
    PROGRAM_INVENTORY = "program_inventory"
    PROTOCOLS = "protocols"
    PROTOCOL_EVENTS = "protocol_events"
    PROBLEM_FOLLOWUPS = "problem_followups"
    MEDICATIONS = "medications"
    MEDICATION_EXECUTIONS = "medication_executions"
    SUPPLEMENTS = "supplements"
    SUPPLEMENT_EXECUTIONS = "supplement_executions"
    CALENDAR = "calendar"
    SAFETY = "safety"


HEALTH_DAY_SOURCE_ORDER_V1 = (
    HealthDaySourceKind.PROFILE_SCHEDULE,
    HealthDaySourceKind.DAILY_PLAN_SUBSET,
    HealthDaySourceKind.PROGRAM_INVENTORY,
    HealthDaySourceKind.PROTOCOLS,
    HealthDaySourceKind.PROTOCOL_EVENTS,
    HealthDaySourceKind.PROBLEM_FOLLOWUPS,
    HealthDaySourceKind.MEDICATIONS,
    HealthDaySourceKind.MEDICATION_EXECUTIONS,
    HealthDaySourceKind.SUPPLEMENTS,
    HealthDaySourceKind.SUPPLEMENT_EXECUTIONS,
    HealthDaySourceKind.CALENDAR,
    HealthDaySourceKind.SAFETY,
)
_SOURCE_ORDER_INDEX = {
    source_kind: index
    for index, source_kind in enumerate(HEALTH_DAY_SOURCE_ORDER_V1)
}


@unique
class HealthDaySourceRole(StrEnum):
    CANDIDATE = "candidate"
    PROJECTION = "projection"
    DIAGNOSTIC = "diagnostic"


@unique
class SourceFreshness(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


@unique
class SourceAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@unique
class TombstoneState(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


@unique
class TransactionDialect(StrEnum):
    POSTGRESQL = "postgresql"


@unique
class TransactionIsolation(StrEnum):
    REPEATABLE_READ = "repeatable_read"


@unique
class StorageNamespace(StrEnum):
    MEDICATION_ROW = "medication_row"
    SUPPLEMENT_DEFINITION = "supplement_definition"
    HEALTH_PROTOCOL = "health_protocol"
    HEALTH_PROBLEM = "health_problem"
    DAILY_PLAN_ACTION = "daily_plan_action"


STORAGE_NAMESPACE_V1 = tuple(StorageNamespace)


@unique
class ProjectionRole(StrEnum):
    ACTION = "action"
    CHECKUP = "checkup"
    SCHEDULE = "schedule"
    SAFETY = "safety"
    PRESENTATION = "presentation"


@unique
class HealthDomain(StrEnum):
    HYDRATION = "hydration"
    DIET = "diet"
    SLEEP = "sleep"
    TRAINING = "training"
    MEDICATION = "medication"
    SUPPLEMENT = "supplement"
    MEASUREMENT = "measurement"
    MOOD = "mood"
    ACTIVITY = "activity"
    EXERCISE = "exercise"
    CHECKUP = "checkup"
    RESPIRATORY = "respiratory"
    MOVEMENT = "movement"
    UNKNOWN = "unknown"


@unique
class CanonicalLifecycle(StrEnum):
    PENDING = "pending"
    DUE = "due"
    OVERDUE = "overdue"
    SNOOZED = "snoozed"
    ADJUSTED = "adjusted"
    AUTO_OBSERVED = "auto_observed"
    BLOCKED = "blocked"
    CONFLICT = "conflict"
    DEFERRED = "deferred"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    INFO = "info"
    UNKNOWN = "unknown"


@unique
class CommitmentClass(StrEnum):
    FIXED = "fixed"
    ADAPTIVE = "adaptive"
    OPPORTUNITY = "opportunity"
    UNKNOWN = "unknown"


@unique
class TimingPrecision(StrEnum):
    EXACT = "exact"
    WINDOW = "window"
    DATE = "date"
    UNKNOWN = "unknown"
    UNSUPPORTED = "unsupported"


@unique
class SafetyDisposition(StrEnum):
    ALLOWED = "allowed"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@unique
class PriorityClass(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    DIAGNOSTIC = "diagnostic"


@unique
class ArtifactStatus(StrEnum):
    COMPLETE = "complete"
    DEGRADED = "degraded"
    ERROR = "error"


@unique
class SourceCompetition(StrEnum):
    UNIQUE_LATEST = "unique_latest"
    SAME_SOURCE_DUPLICATE = "same_source_duplicate"
    MULTI_SOURCE_COMPETITION = "multi_source_competition"
    UNAVAILABLE = "unavailable"


@unique
class WearableFactKind(StrEnum):
    SLEEP_SCORE = "sleep_score"
    TRAINING_READINESS = "training_readiness"


@unique
class ClassifierStatus(StrEnum):
    CLASSIFIED = "classified"
    INPUT_UNAVAILABLE = "input_unavailable"
    POLICY_MISMATCH = "policy_mismatch"


@unique
class AcuteGuardrailCode(StrEnum):
    FEVER = "fever"
    COLD = "cold"
    ACTIVE_ILLNESS = "active_illness"
    NONE = "none"
    UNKNOWN = "unknown"


@unique
class CompletionProvenance(StrEnum):
    COMPLETED = "completed"
    OTHER_TERMINAL = "other_terminal"
    NONTERMINAL = "nonterminal"
    UNKNOWN = "unknown"


@unique
class DailyPlanStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


@unique
class ProtocolCadence(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"
    EVENT_TRIGGERED = "event_triggered"
    PER_MEAL = "per_meal"
    UNKNOWN = "unknown"


@unique
class ProtocolCompletionMode(StrEnum):
    MANUAL = "manual"
    PASSIVE = "passive"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


@unique
class ProblemRiskLevel(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@unique
class ProblemStatus(StrEnum):
    ACTIVE = "active"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


@unique
class OccurrenceAvailability(StrEnum):
    AVAILABLE = "available"
    SOURCE_COUNT_MISMATCH = "source_count_mismatch"
    SLOT_IDENTITY_AMBIGUOUS = "slot_identity_ambiguous"
    UNSUPPORTED = "unsupported"


@unique
class DomainClassificationProvenance(StrEnum):
    EXACT_SUPPLEMENT = "exact_supplement"
    LEGACY_DEFAULT_MEDICATION = "legacy_default_medication"
    INPUT_UNAVAILABLE = "input_unavailable"
    POLICY_MISMATCH = "policy_mismatch"


@unique
class TimingRelation(StrEnum):
    FIXED = "fixed"
    BEFORE_MEAL = "before_meal"
    WITH_MEAL = "with_meal"
    AFTER_MEAL = "after_meal"
    ANYTIME = "anytime"
    UNKNOWN = "unknown"


@unique
class MealAnchor(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    ANYTIME = "anytime"
    NONE = "none"
    UNKNOWN = "unknown"


@unique
class ExecutionMatchDisposition(StrEnum):
    EXACT_UNIQUE_SLOT = "exact_unique_slot"
    SINGLE_DAILY_MARKER = "single_daily_marker"
    MULTIDOSE_DAILY_MARKER = "multidose_daily_marker"
    OFF_SLOT = "off_slot"
    NORMALIZED_COLLISION = "normalized_collision"
    SOURCE_AMBIGUOUS = "source_ambiguous"
    UNMATCHED = "unmatched"


@unique
class SupplementTimingLabel(StrEnum):
    MORNING = "morning"
    NOON = "noon"
    EVENING = "evening"
    BEDTIME = "bedtime"
    UNKNOWN = "unknown"


@unique
class CalendarKnowledgeState(StrEnum):
    TRUSTED_CURRENT = "trusted_current"
    PROVENANCE_UNKNOWN = "provenance_unknown"
    STALE_UNKNOWN = "stale_unknown"
    FAILED_UNKNOWN = "failed_unknown"
    TOMBSTONE_UNSUPPORTED = "tombstone_unsupported"


@unique
class CountConsistency(StrEnum):
    CONSISTENT = "consistent"
    MISMATCH = "mismatch"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@unique
class TimingOrigin(StrEnum):
    EXACT_REMINDER = "exact_reminder"
    FLEXIBLE = "flexible"
    UNKNOWN = "unknown"


@unique
class CalendarBusyState(StrEnum):
    BUSY_INPUT_PRESENT_AND_ELIGIBLE = "busy_input_present_and_eligible"
    NO_BUSY_INPUT = "no_busy_input"
    UNKNOWN = "unknown"


@unique
class ProjectionCoverage(StrEnum):
    COMPARABLE = "comparable"
    INTENTIONALLY_UNSCOPED = "intentionally_unscoped"
    LOSSY_IDENTITY = "lossy_identity"
    AMBIGUOUS_IDENTITY = "ambiguous_identity"
    UNSUPPORTED_PRECISION = "unsupported_precision"


@unique
class SurfaceName(StrEnum):
    DAILY_PLAN = "daily_plan"
    AGENDA = "agenda"
    RUNTIME = "runtime"
    SCHEDULE = "schedule"
    DAILY_ARTIFACT = "daily_artifact"
    DYNAMIC_VIEW = "dynamic_view"
    TIMELINE = "timeline"


@unique
class SurfaceHorizon(StrEnum):
    LOCAL_DAY = "local_day"
    TODAY_AND_FUTURE_DIAGNOSTIC = "today_and_future_diagnostic"


@unique
class SurfaceCardinality(StrEnum):
    ALL = "all"
    TOP_ONE = "top_one"
    TOP_N = "top_n"


@unique
class ScheduleDisposition(StrEnum):
    SCHEDULED = "scheduled"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


@unique
class DiffKind(StrEnum):
    MISSING = "missing"
    EXTRA = "extra"
    RANK_CHANGED = "rank_changed"
    TIMING_CHANGED = "timing_changed"
    SAFETY_CHANGED = "safety_changed"


@unique
class ShadowReasonCode(StrEnum):
    UNSUPPORTED_CURRENT_COMPOSER = "unsupported_current_composer"
    SAFETY_SNAPSHOT_UNAVAILABLE = "safety_snapshot_unavailable"
    CALENDAR_TOMBSTONE_UNSUPPORTED = "calendar_tombstone_unsupported"
    CALENDAR_SYNC_STALE = "calendar_sync_stale"
    CALENDAR_SYNC_FAILED = "calendar_sync_failed"
    CALENDAR_TIMEZONE_PROVENANCE_UNKNOWN = "calendar_timezone_provenance_unknown"
    CALENDAR_ALL_DAY_TIMEZONE_PROVENANCE_UNSUPPORTED = (
        "calendar_all_day_timezone_provenance_unsupported"
    )
    CALENDAR_INTERVAL_INVALID = "calendar_interval_invalid"
    CALENDAR_EVENT_CAP_EXCEEDED = "calendar_event_cap_exceeded"
    LEGACY_CALENDAR_BUSY_PRECISION_UNSUPPORTED = (
        "legacy_calendar_busy_precision_unsupported"
    )
    LEGACY_FLEXIBLE_SCHEDULE_TIMING_UNSUPPORTED = (
        "legacy_flexible_schedule_timing_unsupported"
    )
    TIMEZONE_CANDIDATE_INVALID = "timezone_candidate_invalid"
    TIMEZONE_MANIFEST_PROFILE_MISMATCH = "timezone_manifest_profile_mismatch"
    DAILY_PLAN_SNAPSHOT_MISSING = "daily_plan_snapshot_missing"
    DAILY_PLAN_INPUTS_INCOMPLETE = "daily_plan_inputs_incomplete"
    DAILY_PLAN_WEIGHT_SOURCE_POLICY_UNSUPPORTED = (
        "daily_plan_weight_source_policy_unsupported"
    )
    DAILY_PLAN_LAB_FLAG_POLICY_UNSUPPORTED = "daily_plan_lab_flag_policy_unsupported"
    DAILY_PLAN_RECOVERY_MULTISOURCE_POLICY_UNSUPPORTED = (
        "daily_plan_recovery_multisource_policy_unsupported"
    )
    DAILY_PLAN_COMPOSITE_TRAINING_GATE_UNSUPPORTED = (
        "daily_plan_composite_training_gate_unsupported"
    )
    DAILY_PLAN_ADVICE_GUARD_UNSUPPORTED = "daily_plan_advice_guard_unsupported"
    DAILY_PLAN_POST_GUARD_SELECTION_UNCOMPARABLE = (
        "daily_plan_post_guard_selection_uncomparable"
    )
    DAILY_PLAN_PREDICTION_ENRICHMENT_UNSUPPORTED = (
        "daily_plan_prediction_enrichment_unsupported"
    )
    DAILY_PLAN_INTERVENTION_DOMAIN_UNKNOWN = "daily_plan_intervention_domain_unknown"
    DAILY_PLAN_CYCLE_LABEL_POLICY_UNSUPPORTED = (
        "daily_plan_cycle_label_policy_unsupported"
    )
    DAILY_PLAN_WEIGHT_DEFAULT_USED = "daily_plan_weight_default_used"
    DAILY_PLAN_TRAINING_CLASSIFIER_POLICY_MISMATCH = (
        "daily_plan_training_classifier_policy_mismatch"
    )
    DAILY_PLAN_ACUTE_CLASSIFIER_POLICY_MISMATCH = (
        "daily_plan_acute_classifier_policy_mismatch"
    )
    MEDICATION_DOMAIN_CLASSIFIER_POLICY_MISMATCH = (
        "medication_domain_classifier_policy_mismatch"
    )
    LEGACY_NONDETERMINISTIC_TIE = "legacy_nondeterministic_tie"
    SOURCE_REVISION_MISSING = "source_revision_missing"
    SOURCE_PAYLOAD_DIGEST_MISMATCH = "source_payload_digest_mismatch"
    LEGACY_LOSSY_IDENTITY = "legacy_lossy_identity"
    UNSUPPORTED_TIMING_PRECISION = "unsupported_timing_precision"
    SLOT_IDENTITY_AMBIGUOUS = "slot_identity_ambiguous"
    INVALID_LOCAL_SLOT = "invalid_local_slot"
    NONEXISTENT_LOCAL_TIME = "nonexistent_local_time"
    AMBIGUOUS_LOCAL_TIME_WITHOUT_FOLD = "ambiguous_local_time_without_fold"
    UNSUPPORTED_LIFECYCLE_STATE = "unsupported_lifecycle_state"
    PROTOCOL_PER_MEAL_OCCURRENCE_UNSUPPORTED = (
        "protocol_per_meal_occurrence_unsupported"
    )
    MEDICATION_SOURCE_OCCURRENCE_COUNT_MISMATCH = (
        "medication_source_occurrence_count_mismatch"
    )
    MEDICATION_DAILY_MARKER_MULTIDOSE_UNSUPPORTED = (
        "medication_daily_marker_multidose_unsupported"
    )
    MEDICATION_OFF_SLOT_EXECUTION_UNSUPPORTED = (
        "medication_off_slot_execution_unsupported"
    )
    MEDICATION_NORMALIZED_LOG_COLLISION = "medication_normalized_log_collision"
    LEGACY_ORACLE_BASELINE_MISMATCH = "legacy_oracle_baseline_mismatch"
    AMBIGUOUS_COMPARABLE_IDENTITY = "ambiguous_comparable_identity"
    DAILY_ARTIFACT_TOP_SOURCE_UNSUPPORTED = "daily_artifact_top_source_unsupported"
    RUNTIME_FUTURE_PROJECTION_UNSCOPED = "runtime_future_projection_unscoped"
    LEGACY_TRAINING_DECISION_UNSUPPORTED = "legacy_training_decision_unsupported"
    LEGACY_DAY_SCHEDULE_WORKOUT_UNSUPPORTED = (
        "legacy_day_schedule_workout_unsupported"
    )
    LEGACY_DATA_QUALITY_UNSUPPORTED = "legacy_data_quality_unsupported"
    LEGACY_WEARABLE_ROUTER_UNSUPPORTED = "legacy_wearable_router_unsupported"
    LEGACY_PROTOCOL_CORRECTION_UNSUPPORTED = (
        "legacy_protocol_correction_unsupported"
    )
    LEGACY_OUTCOME_CORRECTION_UNSUPPORTED = "legacy_outcome_correction_unsupported"
    LEGACY_REVIEW_SCHEDULE_UNSUPPORTED = "legacy_review_schedule_unsupported"
    LEGACY_BASELINE_DEVIATION_UNSUPPORTED = (
        "legacy_baseline_deviation_unsupported"
    )
    LEGACY_RUNTIME_GUIDANCE_UNSUPPORTED = "legacy_runtime_guidance_unsupported"
    LEGACY_TIMELINE_OBSERVATION_UNSCOPED = "legacy_timeline_observation_unscoped"
    LEGACY_TIMELINE_OUTCOME_UNSCOPED = "legacy_timeline_outcome_unscoped"
    LEGACY_TIMELINE_WORK_UNSCOPED = "legacy_timeline_work_unscoped"
    LEGACY_TIMELINE_RHYTHM_UNSCOPED = "legacy_timeline_rhythm_unscoped"
    LEGACY_SCHEDULE_MEAL_DEFAULT_UNSUPPORTED = (
        "legacy_schedule_meal_default_unsupported"
    )
    LEGACY_SCHEDULE_SLEEP_DEFAULT_UNSUPPORTED = (
        "legacy_schedule_sleep_default_unsupported"
    )
    LEGACY_SCHEDULE_WORKOUT_DEFAULT_UNSUPPORTED = (
        "legacy_schedule_workout_default_unsupported"
    )
    STANDALONE_SUPPLEMENT_NON_SCHEDULE_SURFACE_UNSCOPED = (
        "standalone_supplement_non_schedule_surface_unscoped"
    )
    LEGACY_SURFACE_SOURCE_ROLE_UNKNOWN = "legacy_surface_source_role_unknown"


_CONTROLLED_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_SIGNED_SHADOW_ITEM_KEY_RE = re.compile(
    r"[A-Za-z0-9_-]{1,32}\.[0-9a-f]{64}"
)


def _require_controlled_token(value: str, field_name: str) -> None:
    if not value or not value.isascii() or _CONTROLLED_TOKEN_RE.fullmatch(value) is None:
        raise ValueError(f"controlled_ascii_token_required:{field_name}")


def _require_signed_shadow_item_key_token(value: object) -> None:
    if type(value) is not str:
        raise TypeError("signed_shadow_item_key_token_type_invalid")
    if _SIGNED_SHADOW_ITEM_KEY_RE.fullmatch(value) is None:
        raise ValueError("signed_shadow_item_key_token_invalid")


def _require_health_day_shadow_schema_version(value: str) -> None:
    if value != HEALTH_DAY_SHADOW_SCHEMA_VERSION:
        raise ValueError("health_day_shadow_schema_version_unsupported")


def _require_manifest_schema_version(value: str) -> None:
    if value != HEALTH_DAY_SHADOW_SCHEMA_VERSION:
        raise ValueError("manifest_schema_version_unsupported")


def _require_owner_id(value: str) -> None:
    if not value.isascii() or not value.isdigit() or int(value) < 1:
        raise ValueError("owner_id_must_be_positive_decimal_ascii")


def _require_iana_timezone(value: str) -> None:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError(f"invalid_iana_timezone:{value}") from exc


def _require_utc_datetime(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"timestamp_timezone_required:{field_name}")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"timestamp_must_be_normalized_to_utc:{field_name}")


def _validate_boundary_value(value: object, path: str) -> None:
    if value is None or type(value) in {str, int, bool, date}:
        return
    if type(value) is datetime:
        _require_utc_datetime(value, path)
        return
    if isinstance(value, StrEnum):
        return
    if type(value) is tuple:
        for index, member in enumerate(value):
            _validate_boundary_value(member, f"{path}[{index}]")
        return
    if type(value) in {list, dict, set, bytearray}:
        raise TypeError(f"immutable_tuple_required:{path}")
    if isinstance(value, _ContractBoundary) and is_dataclass(value):
        return
    raise TypeError(f"unsupported_contract_boundary_type:{path}:{type(value).__name__}")


def _validate_annotation(value: object, annotation: object, path: str) -> None:
    origin = get_origin(annotation)
    if origin in {Union, UnionType}:
        for option in get_args(annotation):
            try:
                _validate_annotation(value, option, path)
            except TypeError:
                continue
            return
        raise TypeError(f"contract_annotation_type_mismatch:{path}")

    if origin is tuple:
        if type(value) in {list, dict, set, bytearray}:
            raise TypeError(f"immutable_tuple_required:{path}")
        if type(value) is not tuple:
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        arguments = get_args(annotation)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            for index, member in enumerate(value):
                _validate_annotation(member, arguments[0], f"{path}[{index}]")
            return
        if len(value) != len(arguments):
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        for index, (member, member_annotation) in enumerate(zip(value, arguments)):
            _validate_annotation(member, member_annotation, f"{path}[{index}]")
        return

    if annotation is type(None):
        if value is not None:
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        return

    if annotation in {str, int, bool, date, datetime}:
        if type(value) is not annotation:
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        return

    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        if type(value) is not annotation:
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        return

    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not annotation:
            raise TypeError(f"contract_annotation_type_mismatch:{path}")
        return

    raise TypeError(f"unsupported_contract_annotation:{path}")


def _require_local_minute(value: int | None, field_name: str) -> None:
    if value is not None and (type(value) is not int or not 0 <= value <= 1439):
        raise ValueError(f"slot_local_minute_out_of_range:{field_name}")


def _require_unknown_lifecycle_reason(
    status: CanonicalLifecycle,
    reason_codes: tuple[ShadowReasonCode, ...],
) -> None:
    if (
        status is CanonicalLifecycle.UNKNOWN
        and ShadowReasonCode.UNSUPPORTED_LIFECYCLE_STATE not in reason_codes
    ):
        raise ValueError("unknown_lifecycle_requires_reason")


class _ContractBoundary:
    __slots__ = ()

    def __post_init__(self) -> None:
        type_hints = get_type_hints(type(self))
        for contract_field in fields(self):
            path = f"{type(self).__name__}.{contract_field.name}"
            _validate_annotation(
                getattr(self, contract_field.name),
                type_hints[contract_field.name],
                path,
            )
            _validate_boundary_value(
                getattr(self, contract_field.name),
                path,
            )
        self._validate_contract()

    def _validate_contract(self) -> None:
        return None


_BUNDLE_OWNERSHIP_ISSUER = object()


class _BundleOwnership:
    __slots__ = ("issuer",)

    def __init__(self, issuer: object) -> None:
        if issuer is not _BUNDLE_OWNERSHIP_ISSUER:
            raise TypeError("bundle_ownership_issuer_invalid")
        self.issuer = issuer


class _BundleOwnedContract(_ContractBoundary):
    __slots__ = ("_bundle_ownership",)


_SIGNED_SHADOW_ITEM_KEY_ISSUER = object()


class _SignedShadowItemContract(_ContractBoundary):
    __slots__ = ("_signed_shadow_item_key_issuer",)


def _construct_bundle_owned(
    contract_type: type[_BundleOwnedContract],
    ownership: _BundleOwnership,
    values: dict[str, object],
) -> _BundleOwnedContract:
    if (
        type(ownership) is not _BundleOwnership
        or ownership.issuer is not _BUNDLE_OWNERSHIP_ISSUER
    ):
        raise TypeError("bundle_ownership_capability_invalid")
    expected_fields = {contract_field.name for contract_field in fields(contract_type)}
    if set(values) != expected_fields:
        raise TypeError("bundle_owned_contract_fields_mismatch")
    instance = object.__new__(contract_type)
    for field_name, value in values.items():
        object.__setattr__(instance, field_name, value)
    object.__setattr__(instance, "_bundle_ownership", ownership)
    instance.__post_init__()
    return instance


def _validate_source_results(
    source_results: tuple[HealthDaySourceResult, ...],
) -> None:
    kinds = tuple(source.source_kind for source in source_results)
    if len(kinds) != len(set(kinds)):
        raise ValueError("source_results_duplicate_kind")
    expected = tuple(sorted(kinds, key=_SOURCE_ORDER_INDEX.__getitem__))
    if kinds != expected:
        raise ValueError("source_results_out_of_order")


@dataclass(frozen=True, slots=True)
class HealthDayTransaction(_ContractBoundary):
    dialect: TransactionDialect
    isolation: TransactionIsolation
    read_only: bool

    def _validate_contract(self) -> None:
        if not self.read_only:
            raise ValueError("health_day_transaction_must_be_read_only")


@dataclass(frozen=True, slots=True)
class HealthDaySourceResult(_ContractBoundary):
    source_kind: HealthDaySourceKind
    source_role: HealthDaySourceRole
    revision: str | None
    payload_digest: str
    acquired_at: datetime | None
    cutoff: datetime | None
    freshness: SourceFreshness
    availability: SourceAvailability
    error_code: ShadowReasonCode | None
    tombstone_state: TombstoneState

    def _validate_contract(self) -> None:
        if self.revision is not None:
            _require_controlled_token(self.revision, "revision")
        _require_controlled_token(self.payload_digest, "payload_digest")


@dataclass(frozen=True, slots=True)
class ProfileScheduleDTO(_ContractBoundary):
    timezone: str | None
    detected_timezone: str | None
    manual_timezone: str | None
    usual_sleep_time: str | None
    usual_wake_time: str | None
    work_start_time: str | None
    work_end_time: str | None
    workout_pref_window: str | None
    workout_target_minutes: int | None


@dataclass(frozen=True, slots=True)
class BodyWeightSubsetDTO(_ContractBoundary):
    record_date: date | None
    weight_decimal: str | None
    availability: SourceAvailability
    competition: SourceCompetition
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class LabAnchorSubsetDTO(_ContractBoundary):
    availability: SourceAvailability
    anchor_missing: bool
    anchor_stale: bool
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class RecoveryWearableFactDTO(_ContractBoundary):
    fact_kind: WearableFactKind
    record_date: date | None
    value_decimal: str | None
    freshness: SourceFreshness
    competition: SourceCompetition
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class AcuteSubsetDTO(_ContractBoundary):
    has_active_illness: bool
    suspected_cold: bool
    fever_reported: bool
    should_rest: bool
    guardrail_code: AcuteGuardrailCode
    severity_max: int | None
    classification_status: ClassifierStatus
    classifier_version: str
    classifier_policy_digest: str
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class RecoverySubsetDTO(_ContractBoundary):
    sleep: RecoveryWearableFactDTO
    readiness: RecoveryWearableFactDTO
    acute: AcuteSubsetDTO
    poor_recovery: bool | None
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class InterventionSubsetDTO(_ContractBoundary):
    action_key: str
    priority: int
    created_at: datetime
    expires_at: datetime | None
    metric_key: str | None
    target_value_decimal: str | None
    evidence_level: str | None
    check_back_date: date | None
    classification_status: ClassifierStatus
    training_like: bool | None
    classifier_version: str
    classifier_policy_digest: str
    domain: HealthDomain
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class TerminalActionSubsetDTO(_ContractBoundary):
    record_id: str
    action_key: str
    status: CanonicalLifecycle
    completion_provenance: CompletionProvenance

    def _validate_contract(self) -> None:
        _require_unknown_lifecycle_reason(self.status, ())


@dataclass(frozen=True, slots=True)
class ActiveCycleSubsetDTO(_ContractBoundary):
    cycle_id: str
    cycle_type: str
    start_date: date
    planned_end_date: date | None
    primary_metric_code: str | None
    outcome_status: str | None
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ExistingDOPActionFact(_ContractBoundary):
    action_key: str
    domain: HealthDomain
    when_code: str | None


@dataclass(frozen=True, slots=True)
class ExistingDOPDiagnosticDTO(_ContractBoundary):
    plan_id: str
    status: DailyPlanStatus
    actions: tuple[ExistingDOPActionFact, ...]
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class DailyPlanSubsetFactsDTO(_ContractBoundary):
    body_weight: BodyWeightSubsetDTO
    lab_anchor: LabAnchorSubsetDTO
    recovery: RecoverySubsetDTO
    interventions: tuple[InterventionSubsetDTO, ...]
    terminal_actions: tuple[TerminalActionSubsetDTO, ...]
    active_cycle: ActiveCycleSubsetDTO | None
    existing_dop: ExistingDOPDiagnosticDTO | None
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ProgramInventoryDTO(_ContractBoundary):
    program_id: str
    program_type: str
    problem_id: str | None
    started_on: date
    target_end_on: date | None
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ProtocolDTO(_ContractBoundary):
    protocol_id: str
    domain: HealthDomain
    mechanism: str | None
    cadence: ProtocolCadence
    time_window: str | None
    completion_mode: ProtocolCompletionMode
    can_default_complete: bool
    manual_track_allowed: bool
    program_id: str | None
    source_model: str | None
    source_id: str | None
    trigger_date: date | None
    availability: SourceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ProtocolEventDTO(_ContractBoundary):
    event_id: str
    protocol_id: str
    event_date: date
    status: CanonicalLifecycle
    track: str | None
    snoozed_until: datetime | None
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_unknown_lifecycle_reason(self.status, self.reason_codes)


@dataclass(frozen=True, slots=True)
class ProblemFollowUpDTO(_ContractBoundary):
    problem_id: str
    risk_level: ProblemRiskLevel
    status: ProblemStatus
    last_checkup: date | None
    cadence: ProtocolCadence
    next_due: date | None
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class MedicationSourceDTO(_ContractBoundary):
    storage_namespace: StorageNamespace
    medication_id: str
    times_per_day: int
    normalized_slots: tuple[int, ...]
    domain: HealthDomain
    domain_classification_provenance: DomainClassificationProvenance
    domain_classifier_version: str
    domain_classifier_policy_digest: str
    timing_relation: TimingRelation
    meal_anchor: MealAnchor
    start_date: date | None
    end_date: date | None
    occurrence_availability: OccurrenceAvailability
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        if self.storage_namespace is not StorageNamespace.MEDICATION_ROW:
            raise ValueError("medication_source_storage_namespace_invalid")
        for slot in self.normalized_slots:
            _require_local_minute(slot, "normalized_slots")


@dataclass(frozen=True, slots=True)
class MedicationExecutionDTO(_ContractBoundary):
    record_id: str
    medication_id: str
    taken_date: date
    raw_slot_present: bool
    normalized_slot: int | None
    status: CanonicalLifecycle
    match_disposition: ExecutionMatchDisposition
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_local_minute(self.normalized_slot, "normalized_slot")
        _require_unknown_lifecycle_reason(self.status, self.reason_codes)


@dataclass(frozen=True, slots=True)
class SupplementSourceDTO(_ContractBoundary):
    storage_namespace: StorageNamespace
    supplement_definition_id: str
    timing_label: SupplementTimingLabel
    timing_precision_status: TimingPrecision
    sort_order: int
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        if self.storage_namespace is not StorageNamespace.SUPPLEMENT_DEFINITION:
            raise ValueError("supplement_source_storage_namespace_invalid")


@dataclass(frozen=True, slots=True)
class SupplementExecutionDTO(_ContractBoundary):
    record_id: str
    supplement_definition_id: str
    record_date: date
    normalized_time: int | None
    taken: bool
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_local_minute(self.normalized_time, "normalized_time")


@dataclass(frozen=True, slots=True)
class CalendarSourceFact(_ContractBoundary):
    source_id: str
    provider_code: str
    sync_enabled: bool
    last_sync_at: datetime | None
    sync_failed: bool


@dataclass(frozen=True, slots=True)
class CalendarIntervalFact(_ContractBoundary):
    event_id: str
    source_id: str
    start_utc: datetime | None
    end_utc: datetime | None
    all_day: bool
    local_start_minute: int | None
    local_end_minute: int | None
    utc_offset_start_minutes: int | None
    utc_offset_end_minutes: int | None
    fold_start: int | None
    fold_end: int | None
    crosses_midnight: bool | None
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_local_minute(self.local_start_minute, "local_start_minute")
        _require_local_minute(self.local_end_minute, "local_end_minute")
        for value in (self.fold_start, self.fold_end):
            if value is not None and value not in {0, 1}:
                raise ValueError("calendar_fold_must_be_zero_or_one")


@dataclass(frozen=True, slots=True)
class CalendarKnowledgeDTO(_ContractBoundary):
    state: CalendarKnowledgeState
    effective_timezone: str
    day_start_utc: datetime
    day_end_utc: datetime
    sources: tuple[CalendarSourceFact, ...]
    intervals: tuple[CalendarIntervalFact, ...]
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class SafetySeamDTO(_ContractBoundary):
    availability: SourceAvailability
    disposition: SafetyDisposition
    reason_codes: tuple[ShadowReasonCode, ...]


SourcePayloadValue: TypeAlias = (
    ProfileScheduleDTO
    | DailyPlanSubsetFactsDTO
    | tuple[ProgramInventoryDTO, ...]
    | tuple[ProtocolDTO, ...]
    | tuple[ProtocolEventDTO, ...]
    | tuple[ProblemFollowUpDTO, ...]
    | tuple[MedicationSourceDTO, ...]
    | tuple[MedicationExecutionDTO, ...]
    | tuple[SupplementSourceDTO, ...]
    | tuple[SupplementExecutionDTO, ...]
    | CalendarKnowledgeDTO
    | SafetySeamDTO
)


@dataclass(frozen=True, slots=True, init=False)
class HealthDaySourcePayload(_BundleOwnedContract):
    source_kind: HealthDaySourceKind
    value: SourcePayloadValue

    def __init__(self, **_values: object) -> None:
        raise TypeError("source_payload_must_be_constructed_by_bundle")

    def _validate_contract(self) -> None:
        singleton_types = {
            HealthDaySourceKind.PROFILE_SCHEDULE: ProfileScheduleDTO,
            HealthDaySourceKind.DAILY_PLAN_SUBSET: DailyPlanSubsetFactsDTO,
            HealthDaySourceKind.CALENDAR: CalendarKnowledgeDTO,
            HealthDaySourceKind.SAFETY: SafetySeamDTO,
        }
        collection_types = {
            HealthDaySourceKind.PROGRAM_INVENTORY: ProgramInventoryDTO,
            HealthDaySourceKind.PROTOCOLS: ProtocolDTO,
            HealthDaySourceKind.PROTOCOL_EVENTS: ProtocolEventDTO,
            HealthDaySourceKind.PROBLEM_FOLLOWUPS: ProblemFollowUpDTO,
            HealthDaySourceKind.MEDICATIONS: MedicationSourceDTO,
            HealthDaySourceKind.MEDICATION_EXECUTIONS: MedicationExecutionDTO,
            HealthDaySourceKind.SUPPLEMENTS: SupplementSourceDTO,
            HealthDaySourceKind.SUPPLEMENT_EXECUTIONS: SupplementExecutionDTO,
        }
        if expected := singleton_types.get(self.source_kind):
            if type(self.value) is not expected:
                raise ValueError(f"source_payload_type_mismatch:{self.source_kind}")
            return
        expected_member = collection_types[self.source_kind]
        if type(self.value) is not tuple or not all(
            type(member) is expected_member for member in self.value
        ):
            raise ValueError(f"source_payload_type_mismatch:{self.source_kind}")


@dataclass(frozen=True, slots=True, init=False)
class HealthDayShadowManifest(_BundleOwnedContract):
    schema_version: str
    owner_id: str
    local_day: date
    timezone: str
    as_of: datetime
    transaction: HealthDayTransaction
    sources: tuple[HealthDaySourceResult, ...]

    def __init__(self, **_values: object) -> None:
        raise TypeError("manifest_must_be_constructed_by_bundle")

    def _validate_contract(self) -> None:
        _require_health_day_shadow_schema_version(self.schema_version)
        _require_owner_id(self.owner_id)
        if type(self.local_day) is not date:
            raise TypeError("local_day_date_required")
        _require_iana_timezone(self.timezone)
        _validate_source_results(self.sources)


@dataclass(frozen=True, slots=True, init=False)
class HealthDayShadowBundle(_BundleOwnedContract):
    manifest: HealthDayShadowManifest
    payloads: tuple[HealthDaySourcePayload, ...]
    shadow_manifest_digest: str

    def __init__(self, **_values: object) -> None:
        raise TypeError("bundle_must_be_constructed_with_create")

    @classmethod
    def create(
        cls,
        *,
        schema_version: str,
        owner_id: str,
        local_day: date,
        timezone: str,
        as_of: datetime,
        transaction: HealthDayTransaction,
        sources: tuple[HealthDaySourceResult, ...],
        source_payload_values: tuple[
            tuple[HealthDaySourceKind, SourcePayloadValue], ...
        ],
        shadow_manifest_digest: str,
    ) -> HealthDayShadowBundle:
        if type(source_payload_values) is not tuple:
            raise TypeError("immutable_tuple_required:source_payload_values")
        ownership = _BundleOwnership(_BUNDLE_OWNERSHIP_ISSUER)
        payloads: list[HealthDaySourcePayload] = []
        for index, entry in enumerate(source_payload_values):
            if type(entry) is not tuple or len(entry) != 2:
                raise TypeError(
                    f"source_payload_entry_tuple_required:source_payload_values[{index}]"
                )
            source_kind, value = entry
            payload = _construct_bundle_owned(
                HealthDaySourcePayload,
                ownership,
                {"source_kind": source_kind, "value": value},
            )
            payloads.append(payload)  # type: ignore[arg-type]
        manifest = _construct_bundle_owned(
            HealthDayShadowManifest,
            ownership,
            {
                "schema_version": schema_version,
                "owner_id": owner_id,
                "local_day": local_day,
                "timezone": timezone,
                "as_of": as_of,
                "transaction": transaction,
                "sources": sources,
            },
        )
        bundle = _construct_bundle_owned(
            cls,
            ownership,
            {
                "manifest": manifest,
                "payloads": tuple(payloads),
                "shadow_manifest_digest": shadow_manifest_digest,
            },
        )
        return bundle  # type: ignore[return-value]

    def _validate_contract(self) -> None:
        ownership = self._bundle_ownership
        if self.manifest._bundle_ownership is not ownership or any(
            payload._bundle_ownership is not ownership for payload in self.payloads
        ):
            raise ValueError("bundle_ownership_mismatch")
        payload_kinds = tuple(payload.source_kind for payload in self.payloads)
        manifest_kinds = tuple(source.source_kind for source in self.manifest.sources)
        if payload_kinds != manifest_kinds:
            raise ValueError("bundle_manifest_payload_source_mismatch")
        if len(payload_kinds) != len(set(payload_kinds)):
            raise ValueError("bundle_payload_source_duplicate")
        if self.shadow_manifest_digest:
            _require_controlled_token(
                self.shadow_manifest_digest,
                "shadow_manifest_digest",
            )


@dataclass(frozen=True, slots=True)
class LegacySourcePayloadBinding(_ContractBoundary):
    storage_namespace: StorageNamespace
    source_kind: HealthDaySourceKind
    source_id: str
    payload_digest: str

    def _validate_contract(self) -> None:
        _require_controlled_token(self.source_id, "source_id")
        _require_controlled_token(self.payload_digest, "payload_digest")


@dataclass(frozen=True, slots=True)
class LegacyOccurrenceSlot(_ContractBoundary):
    local_minute: int | None
    dose_ordinal: int

    def _validate_contract(self) -> None:
        _require_local_minute(self.local_minute, "local_minute")
        if type(self.dose_ordinal) is not int or self.dose_ordinal < 0:
            raise ValueError("dose_ordinal_must_be_non_negative")


@dataclass(frozen=True, slots=True)
class LegacyOccurrenceFacts(_ContractBoundary):
    storage_namespace: StorageNamespace
    source_id: str
    domain: HealthDomain
    slots: tuple[LegacyOccurrenceSlot, ...]
    count_consistency: CountConsistency
    timing_origin: TimingOrigin
    calendar_busy_state: CalendarBusyState
    domain_classification_provenance: DomainClassificationProvenance
    domain_classifier_version: str
    domain_classifier_policy_digest: str
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_controlled_token(self.source_id, "source_id")


@dataclass(frozen=True, slots=True)
class LegacyOccurrenceContext(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    source_payload_bindings: tuple[LegacySourcePayloadBinding, ...]
    occurrence_facts: tuple[LegacyOccurrenceFacts, ...]

    def _validate_contract(self) -> None:
        if self.schema_version != LEGACY_OCCURRENCE_CONTEXT_SCHEMA_VERSION:
            raise ValueError("legacy_occurrence_context_schema_unsupported")
        if self.manifest_schema_version != HEALTH_DAY_SHADOW_SCHEMA_VERSION:
            raise ValueError("legacy_occurrence_manifest_schema_mismatch")
        _require_controlled_token(self.manifest_digest, "manifest_digest")
        binding_keys = tuple(
            (binding.storage_namespace, binding.source_id)
            for binding in self.source_payload_bindings
        )
        if len(binding_keys) != len(set(binding_keys)):
            raise ValueError("legacy_occurrence_payload_binding_duplicate")
        occurrence_keys = tuple(
            (fact.storage_namespace, fact.source_id) for fact in self.occurrence_facts
        )
        if len(occurrence_keys) != len(set(occurrence_keys)):
            raise ValueError("legacy_occurrence_fact_duplicate")
        if not set(occurrence_keys) <= set(binding_keys):
            raise ValueError("legacy_occurrence_fact_missing_payload_binding")


@dataclass(frozen=True, slots=True)
class ShadowItemIdentity(_ContractBoundary):
    storage_namespace: StorageNamespace
    source_kind: HealthDaySourceKind
    source_id: str
    local_day: date
    slot_local_minute: int | None
    dose_ordinal: int
    projection_role: ProjectionRole

    def _validate_contract(self) -> None:
        _require_controlled_token(self.source_id, "source_id")
        _require_local_minute(self.slot_local_minute, "slot_local_minute")
        if type(self.dose_ordinal) is not int or self.dose_ordinal < 0:
            raise ValueError("dose_ordinal_must_be_non_negative")


@dataclass(frozen=True, slots=True)
class ShadowTiming(_ContractBoundary):
    precision: TimingPrecision
    local_minute: int | None
    window_start_local_minute: int | None
    window_end_local_minute: int | None
    utc_instant: datetime | None
    utc_offset_minutes: int | None
    fold: int | None
    crosses_midnight: bool | None
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_local_minute(self.local_minute, "local_minute")
        _require_local_minute(self.window_start_local_minute, "window_start_local_minute")
        _require_local_minute(self.window_end_local_minute, "window_end_local_minute")
        if self.fold is not None and self.fold not in {0, 1}:
            raise ValueError("timing_fold_must_be_zero_or_one")


@dataclass(frozen=True, slots=True)
class ShadowSafety(_ContractBoundary):
    disposition: SafetyDisposition
    reason_codes: tuple[ShadowReasonCode, ...]


@dataclass(frozen=True, slots=True)
class ShadowOrderingFacts(_ContractBoundary):
    source_ordinal: int | None
    priority_class: PriorityClass
    scheduled_local_minute: int | None

    def _validate_contract(self) -> None:
        if self.source_ordinal is not None and self.source_ordinal < 0:
            raise ValueError("source_ordinal_must_be_non_negative")
        _require_local_minute(self.scheduled_local_minute, "scheduled_local_minute")


@dataclass(frozen=True, slots=True)
class HealthDayShadowItem(_SignedShadowItemContract):
    shadow_item_key: str
    identity: ShadowItemIdentity
    domain: HealthDomain
    status_canonical: CanonicalLifecycle
    actionable: bool
    commitment_class: CommitmentClass
    timing: ShadowTiming
    safety: ShadowSafety
    ordering_facts: ShadowOrderingFacts
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        if self.shadow_item_key:
            if (
                getattr(self, "_signed_shadow_item_key_issuer", None)
                is not _SIGNED_SHADOW_ITEM_KEY_ISSUER
            ):
                raise ValueError("shadow_item_key_must_be_empty_before_signing")
            _require_signed_shadow_item_key_token(self.shadow_item_key)
        _require_unknown_lifecycle_reason(self.status_canonical, self.reason_codes)


class _SignedShadowItemKeyBinder:
    __slots__ = ()

    def bind(
        self,
        unsigned_item: HealthDayShadowItem,
        token: str,
    ) -> HealthDayShadowItem:
        """Bind one Task 2 signer-produced non-authorizing opaque key."""

        if type(unsigned_item) is not HealthDayShadowItem:
            raise TypeError("exact_health_day_shadow_item_required")
        if unsigned_item.shadow_item_key:
            raise ValueError("shadow_item_key_must_be_empty_before_binding")
        _require_signed_shadow_item_key_token(token)

        signed_item = object.__new__(HealthDayShadowItem)
        for contract_field in fields(HealthDayShadowItem):
            value = (
                token
                if contract_field.name == "shadow_item_key"
                else getattr(unsigned_item, contract_field.name)
            )
            object.__setattr__(signed_item, contract_field.name, value)
        object.__setattr__(
            signed_item,
            "_signed_shadow_item_key_issuer",
            _SIGNED_SHADOW_ITEM_KEY_ISSUER,
        )
        signed_item.__post_init__()
        return signed_item


_SIGNED_SHADOW_ITEM_KEY_BINDER = _SignedShadowItemKeyBinder()


@dataclass(frozen=True, slots=True)
class HealthDayShadowArtifact(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    owner_id: str
    local_day: date
    timezone: str
    as_of: datetime
    status: ArtifactStatus
    source_results: tuple[HealthDaySourceResult, ...]
    items: tuple[HealthDayShadowItem, ...]
    reason_codes: tuple[ShadowReasonCode, ...]

    def _validate_contract(self) -> None:
        _require_health_day_shadow_schema_version(self.schema_version)
        _require_manifest_schema_version(self.manifest_schema_version)
        _require_controlled_token(self.manifest_digest, "manifest_digest")
        _require_owner_id(self.owner_id)
        _require_iana_timezone(self.timezone)
        _validate_source_results(self.source_results)


@dataclass(frozen=True, slots=True)
class SurfaceRank(_ContractBoundary):
    ordinal: int
    is_top: bool
    is_now: bool

    def _validate_contract(self) -> None:
        if self.ordinal < 0:
            raise ValueError("surface_rank_ordinal_must_be_non_negative")


@dataclass(frozen=True, slots=True)
class SurfaceProjectionPolicy(_ContractBoundary):
    schema_version: str
    policy_version: str
    surface: SurfaceName
    horizon: SurfaceHorizon
    included_projection_roles: tuple[ProjectionRole, ...]
    cardinality: SurfaceCardinality
    top_n: int | None
    intentional_dedupe_rule: str
    ordering_rule: str
    top_rule: str
    now_rule: str
    safety_comparable: bool


@dataclass(frozen=True, slots=True)
class UnsealedSurfaceProjectedRow(_ContractBoundary):
    coverage: ProjectionCoverage
    identity: ShadowItemIdentity | None
    domain: HealthDomain
    status_canonical: CanonicalLifecycle
    actionable: bool
    timing: ShadowTiming
    safety: ShadowSafety
    rank: SurfaceRank | None
    schedule_disposition: ScheduleDisposition
    reason_codes: tuple[ShadowReasonCode, ...]
    diagnostic_row_ordinal: int

    def _validate_contract(self) -> None:
        _require_unknown_lifecycle_reason(self.status_canonical, self.reason_codes)


@dataclass(frozen=True, slots=True)
class UnsealedCanonicalSurfaceProjection(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    policy_version: str
    surface: SurfaceName
    local_day: date
    rows: tuple[UnsealedSurfaceProjectedRow, ...]


@dataclass(frozen=True, slots=True)
class UnsealedLegacySurfaceProjection(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    policy_version: str
    surface: SurfaceName
    local_day: date
    rows: tuple[UnsealedSurfaceProjectedRow, ...]


@dataclass(frozen=True, slots=True)
class SealedSurfaceProjectedRow(_ContractBoundary):
    coverage: ProjectionCoverage
    opaque_item_key: str | None
    domain: HealthDomain
    status_canonical: CanonicalLifecycle
    actionable: bool
    timing: ShadowTiming
    safety: ShadowSafety
    rank: SurfaceRank | None
    schedule_disposition: ScheduleDisposition
    reason_codes: tuple[ShadowReasonCode, ...]
    diagnostic_row_ordinal: int

    def _validate_contract(self) -> None:
        _require_unknown_lifecycle_reason(self.status_canonical, self.reason_codes)


@dataclass(frozen=True, slots=True)
class SealedCanonicalSurfaceProjection(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    policy_version: str
    surface: SurfaceName
    local_day: date
    rows: tuple[SealedSurfaceProjectedRow, ...]


@dataclass(frozen=True, slots=True)
class SealedLegacySurfaceProjection(_ContractBoundary):
    schema_version: str
    manifest_schema_version: str
    manifest_digest: str
    policy_version: str
    surface: SurfaceName
    local_day: date
    rows: tuple[SealedSurfaceProjectedRow, ...]


@dataclass(frozen=True, slots=True)
class ShadowSurfaceDiffRow(_ContractBoundary):
    surface: SurfaceName
    diff_kind: DiffKind
    opaque_item_key: str | None
    diagnostic_row_ordinal: int
    reason_code: ShadowReasonCode
    canonical_coverage: ProjectionCoverage | None
    legacy_coverage: ProjectionCoverage | None


CONTRACT_DATACLASS_TYPES = (
    HealthDayTransaction,
    HealthDaySourceResult,
    ProfileScheduleDTO,
    BodyWeightSubsetDTO,
    LabAnchorSubsetDTO,
    RecoveryWearableFactDTO,
    AcuteSubsetDTO,
    RecoverySubsetDTO,
    InterventionSubsetDTO,
    TerminalActionSubsetDTO,
    ActiveCycleSubsetDTO,
    ExistingDOPActionFact,
    ExistingDOPDiagnosticDTO,
    DailyPlanSubsetFactsDTO,
    ProgramInventoryDTO,
    ProtocolDTO,
    ProtocolEventDTO,
    ProblemFollowUpDTO,
    MedicationSourceDTO,
    MedicationExecutionDTO,
    SupplementSourceDTO,
    SupplementExecutionDTO,
    CalendarSourceFact,
    CalendarIntervalFact,
    CalendarKnowledgeDTO,
    SafetySeamDTO,
    HealthDaySourcePayload,
    HealthDayShadowManifest,
    HealthDayShadowBundle,
    LegacySourcePayloadBinding,
    LegacyOccurrenceSlot,
    LegacyOccurrenceFacts,
    LegacyOccurrenceContext,
    ShadowItemIdentity,
    ShadowTiming,
    ShadowSafety,
    ShadowOrderingFacts,
    HealthDayShadowItem,
    HealthDayShadowArtifact,
    SurfaceRank,
    SurfaceProjectionPolicy,
    UnsealedSurfaceProjectedRow,
    UnsealedCanonicalSurfaceProjection,
    UnsealedLegacySurfaceProjection,
    SealedSurfaceProjectedRow,
    SealedCanonicalSurfaceProjection,
    SealedLegacySurfaceProjection,
    ShadowSurfaceDiffRow,
)
