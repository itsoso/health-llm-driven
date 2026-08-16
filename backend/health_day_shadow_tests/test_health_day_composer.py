from __future__ import annotations

import builtins
import importlib
import inspect
import socket
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services as services_package
from app.services import health_day_composer as composer
from app.services import health_day_shadow_contracts as contracts


AS_OF = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
LOCAL_DAY = date(2026, 8, 15)


def _source_result(
    source_kind: contracts.HealthDaySourceKind,
) -> contracts.HealthDaySourceResult:
    return contracts.HealthDaySourceResult(
        source_kind=source_kind,
        source_role=contracts.HealthDaySourceRole.CANDIDATE,
        revision="revision-v1",
        payload_digest="digest-v1",
        acquired_at=AS_OF,
        cutoff=AS_OF,
        freshness=contracts.SourceFreshness.CURRENT,
        availability=contracts.SourceAvailability.AVAILABLE,
        error_code=None,
        tombstone_state=contracts.TombstoneState.UNKNOWN,
    )


def _profile_schedule() -> contracts.ProfileScheduleDTO:
    return contracts.ProfileScheduleDTO(
        timezone="Asia/Shanghai",
        detected_timezone=None,
        manual_timezone=None,
        usual_sleep_time=None,
        usual_wake_time=None,
        work_start_time=None,
        work_end_time=None,
        workout_pref_window=None,
        workout_target_minutes=None,
    )


def _source_payload_value(
    source_kind: contracts.HealthDaySourceKind,
) -> contracts.SourcePayloadValue:
    if source_kind is contracts.HealthDaySourceKind.PROFILE_SCHEDULE:
        return _profile_schedule()
    if source_kind in {
        contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
        contracts.HealthDaySourceKind.PROTOCOLS,
        contracts.HealthDaySourceKind.PROTOCOL_EVENTS,
        contracts.HealthDaySourceKind.PROBLEM_FOLLOWUPS,
        contracts.HealthDaySourceKind.MEDICATIONS,
        contracts.HealthDaySourceKind.MEDICATION_EXECUTIONS,
        contracts.HealthDaySourceKind.SUPPLEMENTS,
        contracts.HealthDaySourceKind.SUPPLEMENT_EXECUTIONS,
    }:
        return ()
    raise AssertionError(f"test_payload_fixture_missing:{source_kind}")


def _bundle(
    *,
    sources: tuple[contracts.HealthDaySourceResult, ...] = (),
    as_of: datetime = AS_OF,
    timezone_name: str = "Asia/Shanghai",
) -> contracts.HealthDayShadowBundle:
    return contracts.HealthDayShadowBundle.create(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
        timezone=timezone_name,
        as_of=as_of,
        transaction=contracts.HealthDayTransaction(
            dialect=contracts.TransactionDialect.POSTGRESQL,
            isolation=contracts.TransactionIsolation.REPEATABLE_READ,
            read_only=True,
        ),
        sources=sources,
        source_payload_values=tuple(
            (source.source_kind, _source_payload_value(source.source_kind))
            for source in sources
        ),
        shadow_manifest_digest="",
    )


def _manifest(
    *,
    sources: tuple[contracts.HealthDaySourceResult, ...] = (),
    as_of: datetime = AS_OF,
    timezone_name: str = "Asia/Shanghai",
) -> contracts.HealthDayShadowManifest:
    return _bundle(
        sources=sources,
        as_of=as_of,
        timezone_name=timezone_name,
    ).manifest


def _identity(
    namespace: contracts.StorageNamespace = contracts.StorageNamespace.MEDICATION_ROW,
) -> contracts.ShadowItemIdentity:
    return contracts.ShadowItemIdentity(
        storage_namespace=namespace,
        source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
        source_id="7",
        local_day=LOCAL_DAY,
        slot_local_minute=8 * 60,
        dose_ordinal=0,
        projection_role=contracts.ProjectionRole.SCHEDULE,
    )


def _item(
    lifecycle: contracts.CanonicalLifecycle,
    *,
    reason_codes: tuple[contracts.ShadowReasonCode, ...] = (),
    shadow_item_key: str = "",
) -> contracts.HealthDayShadowItem:
    return contracts.HealthDayShadowItem(
        shadow_item_key=shadow_item_key,
        identity=_identity(),
        domain=contracts.HealthDomain.MEDICATION,
        status_canonical=lifecycle,
        actionable=False,
        commitment_class=contracts.CommitmentClass.FIXED,
        timing=contracts.ShadowTiming(
            precision=contracts.TimingPrecision.EXACT,
            local_minute=8 * 60,
            window_start_local_minute=None,
            window_end_local_minute=None,
            utc_instant=None,
            utc_offset_minutes=None,
            fold=None,
            crosses_midnight=None,
            reason_codes=(),
        ),
        safety=contracts.ShadowSafety(
            disposition=contracts.SafetyDisposition.UNKNOWN,
            reason_codes=(),
        ),
        ordering_facts=contracts.ShadowOrderingFacts(
            source_ordinal=0,
            priority_class=contracts.PriorityClass.NORMAL,
            scheduled_local_minute=8 * 60,
        ),
        reason_codes=reason_codes,
    )


def _artifact(**overrides: object) -> contracts.HealthDayShadowArtifact:
    values: dict[str, object] = {
        "schema_version": contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        "manifest_schema_version": contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        "manifest_digest": "manifest-digest",
        "owner_id": "42",
        "local_day": LOCAL_DAY,
        "timezone": "Asia/Shanghai",
        "as_of": AS_OF,
        "status": contracts.ArtifactStatus.DEGRADED,
        "source_results": (),
        "items": (),
        "reason_codes": (),
    }
    values.update(overrides)
    return contracts.HealthDayShadowArtifact(**values)  # type: ignore[arg-type]


def _import_llm_via_from_statement() -> object:
    from app.services import llm

    return llm


def test_manifest_requires_explicit_owner_local_day_timezone_and_as_of():
    signature = inspect.signature(contracts.HealthDayShadowBundle.create)
    for field_name in ("owner_id", "local_day", "timezone", "as_of"):
        assert signature.parameters[field_name].default is inspect.Parameter.empty

    with pytest.raises(TypeError):
        contracts.HealthDayShadowBundle.create(  # type: ignore[call-arg]
            schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            local_day=LOCAL_DAY,
            timezone="Asia/Shanghai",
            as_of=AS_OF,
            transaction=contracts.HealthDayTransaction(
                dialect=contracts.TransactionDialect.POSTGRESQL,
                isolation=contracts.TransactionIsolation.REPEATABLE_READ,
                read_only=True,
            ),
            sources=(),
            source_payload_values=(),
            shadow_manifest_digest="",
        )

    with pytest.raises(ValueError, match="timestamp_timezone_required"):
        _manifest(as_of=AS_OF.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timestamp_must_be_normalized_to_utc"):
        _manifest(as_of=datetime(2026, 8, 15, 20, 0, tzinfo=timezone(timedelta(hours=8))))
    with pytest.raises(ValueError, match="invalid_iana_timezone"):
        _manifest(timezone_name="Mars/Olympus_Mons")

    manifest = _manifest()
    assert manifest.owner_id == "42"
    assert manifest.local_day == LOCAL_DAY
    assert manifest.timezone == "Asia/Shanghai"
    assert manifest.as_of == AS_OF


def test_source_results_have_stable_controlled_order():
    assert isinstance(contracts.HEALTH_DAY_SOURCE_ORDER_V1, tuple)
    assert len(contracts.HEALTH_DAY_SOURCE_ORDER_V1) == len(
        set(contracts.HEALTH_DAY_SOURCE_ORDER_V1)
    )
    selected = (
        contracts.HealthDaySourceKind.PROFILE_SCHEDULE,
        contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
        contracts.HealthDaySourceKind.PROTOCOLS,
    )
    ordered = tuple(_source_result(source_kind) for source_kind in selected)
    assert _manifest(sources=ordered).sources == ordered

    with pytest.raises(ValueError, match="source_results_out_of_order"):
        _manifest(sources=tuple(reversed(ordered)))
    with pytest.raises(TypeError, match="immutable_tuple_required"):
        _manifest(sources=list(ordered))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="source_payload_type_mismatch"):
        contracts.HealthDayShadowBundle.create(
            schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            owner_id="42",
            local_day=LOCAL_DAY,
            timezone="Asia/Shanghai",
            as_of=AS_OF,
            transaction=contracts.HealthDayTransaction(
                dialect=contracts.TransactionDialect.POSTGRESQL,
                isolation=contracts.TransactionIsolation.REPEATABLE_READ,
                read_only=True,
            ),
            sources=(_source_result(contracts.HealthDaySourceKind.PROFILE_SCHEDULE),),
            source_payload_values=(
                (contracts.HealthDaySourceKind.PROFILE_SCHEDULE, ()),
            ),
            shadow_manifest_digest="",
        )


def test_shadow_item_identity_requires_storage_namespace_source_day_slot_and_ordinal():
    signature = inspect.signature(contracts.ShadowItemIdentity)
    required = {
        "storage_namespace",
        "source_kind",
        "source_id",
        "local_day",
        "slot_local_minute",
        "dose_ordinal",
        "projection_role",
    }
    assert required <= set(signature.parameters)
    assert all(
        signature.parameters[name].default is inspect.Parameter.empty
        for name in required
    )
    assert _identity().slot_local_minute == 480

    with pytest.raises(ValueError, match="slot_local_minute_out_of_range"):
        contracts.ShadowItemIdentity(
            storage_namespace=contracts.StorageNamespace.MEDICATION_ROW,
            source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
            source_id="7",
            local_day=LOCAL_DAY,
            slot_local_minute=1440,
            dose_ordinal=0,
            projection_role=contracts.ProjectionRole.SCHEDULE,
        )
    with pytest.raises(ValueError, match="dose_ordinal_must_be_non_negative"):
        contracts.ShadowItemIdentity(
            storage_namespace=contracts.StorageNamespace.MEDICATION_ROW,
            source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
            source_id="7",
            local_day=LOCAL_DAY,
            slot_local_minute=None,
            dose_ordinal=-1,
            projection_role=contracts.ProjectionRole.SCHEDULE,
        )


def test_shadow_item_identity_schema_has_no_title_subtitle_or_free_text_field():
    names = {field.name for field in fields(contracts.ShadowItemIdentity)}
    assert not names & {
        "title",
        "subtitle",
        "free_text",
        "description",
        "occurrence_id",
    }
    assert "shadow_item_key" not in names


def test_equal_numeric_ids_in_two_storage_namespaces_are_distinct_contract_values():
    medication = _identity(contracts.StorageNamespace.MEDICATION_ROW)
    supplement = _identity(contracts.StorageNamespace.SUPPLEMENT_DEFINITION)
    assert medication.source_id == supplement.source_id == "7"
    assert medication != supplement
    assert hash(medication) != hash(supplement)


def test_snoozed_adjusted_and_auto_observed_remain_distinct():
    values = {
        contracts.CanonicalLifecycle.SNOOZED,
        contracts.CanonicalLifecycle.ADJUSTED,
        contracts.CanonicalLifecycle.AUTO_OBSERVED,
    }
    assert len(values) == 3
    assert {value.value for value in values} == {
        "snoozed",
        "adjusted",
        "auto_observed",
    }


def test_unknown_lifecycle_fails_visible_instead_of_guessing():
    with pytest.raises(ValueError):
        contracts.CanonicalLifecycle("future_status")
    with pytest.raises(ValueError, match="unknown_lifecycle_requires_reason"):
        _item(contracts.CanonicalLifecycle.UNKNOWN)

    item = _item(
        contracts.CanonicalLifecycle.UNKNOWN,
        reason_codes=(contracts.ShadowReasonCode.UNSUPPORTED_LIFECYCLE_STATE,),
    )
    assert item.status_canonical is contracts.CanonicalLifecycle.UNKNOWN


def test_shadow_item_key_rejects_nonempty_value_before_task2_signing():
    with pytest.raises(
        ValueError,
        match="shadow_item_key_must_be_empty_before_signing",
    ):
        _item(
            contracts.CanonicalLifecycle.PENDING,
            shadow_item_key="test-key.forbidden-before-signing",
        )
    with pytest.raises(
        ValueError,
        match="shadow_item_key_must_be_empty_before_signing",
    ):
        replace(
            _item(contracts.CanonicalLifecycle.PENDING),
            shadow_item_key="test-key.forbidden-before-signing",
        )


def test_contracts_exposes_no_public_raw_shadow_item_token_factory():
    assert not hasattr(contracts, "bind_signed_shadow_item_key")


def test_private_shadow_item_key_binder_preserves_every_unsigned_item_field():
    unsigned_item = _item(
        contracts.CanonicalLifecycle.UNKNOWN,
        reason_codes=(contracts.ShadowReasonCode.UNSUPPORTED_LIFECYCLE_STATE,),
    )
    token = f"kid_v1.{('0a' * 32)}"

    signed_item = contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
        unsigned_item,
        token,
    )

    assert signed_item is not unsigned_item
    assert signed_item.shadow_item_key == token
    for contract_field in fields(contracts.HealthDayShadowItem):
        if contract_field.name != "shadow_item_key":
            assert getattr(signed_item, contract_field.name) == getattr(
                unsigned_item,
                contract_field.name,
            )


@pytest.mark.parametrize(
    "invalid_token",
    (
        "kid_v1.item-key-v1",
        f"kid_v1.{('A' * 64)}",
        f"kid_v1.{('a' * 63)}",
        f"kid_v1.{('a' * 65)}",
        f"bad$key.{('a' * 64)}",
        f"{('k' * 33)}.{('a' * 64)}",
        f".{('a' * 64)}",
        "",
    ),
)
def test_private_shadow_item_key_binder_rejects_non_task2_tokens(invalid_token):
    with pytest.raises(
        ValueError,
        match="signed_shadow_item_key_token_invalid",
    ):
        contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
            _item(contracts.CanonicalLifecycle.PENDING),
            invalid_token,
        )


def test_private_shadow_item_key_binder_rejects_non_string_token():
    with pytest.raises(
        TypeError,
        match="signed_shadow_item_key_token_type_invalid",
    ):
        contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
            _item(contracts.CanonicalLifecycle.PENDING),
            None,
        )


def test_private_shadow_item_key_binder_rejects_already_signed_or_wrong_item_type():
    unsigned_item = _item(contracts.CanonicalLifecycle.PENDING)
    signed_item = contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
        unsigned_item,
        f"kid_v1.{('a' * 64)}",
    )

    with pytest.raises(
        ValueError,
        match="shadow_item_key_must_be_empty_before_binding",
    ):
        contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
            signed_item,
            f"kid_v1.{('b' * 64)}",
        )
    with pytest.raises(
        TypeError,
        match="exact_health_day_shadow_item_required",
    ):
        contracts._SIGNED_SHADOW_ITEM_KEY_BINDER.bind(  # type: ignore[attr-defined]
            object(),  # type: ignore[arg-type]
            f"kid_v1.{('c' * 64)}",
        )


def test_bundle_exclusively_constructs_manifest_and_source_payload():
    transaction = contracts.HealthDayTransaction(
        dialect=contracts.TransactionDialect.POSTGRESQL,
        isolation=contracts.TransactionIsolation.REPEATABLE_READ,
        read_only=True,
    )
    with pytest.raises(TypeError, match="manifest_must_be_constructed_by_bundle"):
        contracts.HealthDayShadowManifest(
            schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            owner_id="42",
            local_day=LOCAL_DAY,
            timezone="Asia/Shanghai",
            as_of=AS_OF,
            transaction=transaction,
            sources=(),
        )
    with pytest.raises(
        TypeError,
        match="source_payload_must_be_constructed_by_bundle",
    ):
        contracts.HealthDaySourcePayload(
            source_kind=contracts.HealthDaySourceKind.PROFILE_SCHEDULE,
            value=_profile_schedule(),
        )
    bundle = _bundle()
    other_bundle = _bundle()
    assert bundle.manifest is not other_bundle.manifest
    with pytest.raises(TypeError, match="bundle_must_be_constructed_with_create"):
        contracts.HealthDayShadowBundle(
            manifest=bundle.manifest,
            payloads=other_bundle.payloads,
            shadow_manifest_digest="",
        )


def test_raw_strings_and_scalar_subclasses_cannot_bypass_controlled_types():
    with pytest.raises(TypeError, match="contract_annotation_type_mismatch"):
        contracts.HealthDayTransaction(
            dialect="not-postgres",  # type: ignore[arg-type]
            isolation=contracts.TransactionIsolation.REPEATABLE_READ,
            read_only=True,
        )
    with pytest.raises(TypeError, match="contract_annotation_type_mismatch"):
        replace(
            _identity(),
            storage_namespace="invented_namespace",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="contract_annotation_type_mismatch"):
        replace(
            _item(contracts.CanonicalLifecycle.PENDING),
            status_canonical="future_status",  # type: ignore[arg-type]
        )

    class MutableInt(int):
        pass

    with pytest.raises(TypeError, match="contract_annotation_type_mismatch"):
        replace(_identity(), dose_ordinal=MutableInt(0))


def test_artifact_source_results_use_manifest_order_and_reject_duplicates():
    selected = (
        contracts.HealthDaySourceKind.PROFILE_SCHEDULE,
        contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
        contracts.HealthDaySourceKind.PROTOCOLS,
    )
    ordered = tuple(_source_result(source_kind) for source_kind in selected)
    artifact = _artifact(source_results=ordered)
    assert artifact.source_results == ordered

    with pytest.raises(ValueError, match="source_results_out_of_order"):
        _artifact(source_results=tuple(reversed(ordered)))
    with pytest.raises(ValueError, match="source_results_duplicate_kind"):
        _artifact(source_results=(ordered[0], ordered[0]))


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "expected_error"),
    (
        (
            "schema_version",
            "health_day_shadow.future",
            "health_day_shadow_schema_version_unsupported",
        ),
        (
            "manifest_schema_version",
            "health_day_shadow.future",
            "manifest_schema_version_unsupported",
        ),
        ("manifest_digest", "", "controlled_ascii_token_required:manifest_digest"),
        (
            "manifest_digest",
            "digest with spaces",
            "controlled_ascii_token_required:manifest_digest",
        ),
        ("owner_id", "", "owner_id_must_be_positive_decimal_ascii"),
        ("owner_id", "not-an-owner", "owner_id_must_be_positive_decimal_ascii"),
        ("timezone", "", "invalid_iana_timezone"),
        ("timezone", "Mars/Olympus_Mons", "invalid_iana_timezone"),
    ),
)
def test_artifact_revalidates_manifest_boundary_fields(
    field_name: str,
    invalid_value: object,
    expected_error: str,
):
    with pytest.raises(ValueError, match=expected_error):
        _artifact(**{field_name: invalid_value})


def test_artifact_accepts_complete_valid_boundary_and_keeps_aware_as_of():
    artifact = _artifact()
    assert artifact.schema_version == contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION
    assert artifact.manifest_schema_version == contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION
    assert artifact.manifest_digest == "manifest-digest"
    assert artifact.owner_id == "42"
    assert artifact.timezone == "Asia/Shanghai"
    assert artifact.as_of == AS_OF

    with pytest.raises(ValueError, match="timestamp_timezone_required"):
        _artifact(as_of=AS_OF.replace(tzinfo=None))


def test_contract_dtos_are_frozen_slots_and_reject_mutable_payloads():
    required_names = {
        "ProfileScheduleDTO",
        "BodyWeightSubsetDTO",
        "LabAnchorSubsetDTO",
        "RecoveryWearableFactDTO",
        "AcuteSubsetDTO",
        "RecoverySubsetDTO",
        "InterventionSubsetDTO",
        "TerminalActionSubsetDTO",
        "ActiveCycleSubsetDTO",
        "ExistingDOPDiagnosticDTO",
        "ProgramInventoryDTO",
        "ProtocolDTO",
        "ProtocolEventDTO",
        "ProblemFollowUpDTO",
        "MedicationSourceDTO",
        "MedicationExecutionDTO",
        "SupplementSourceDTO",
        "SupplementExecutionDTO",
    }
    contract_names = {contract_type.__name__ for contract_type in contracts.CONTRACT_DATACLASS_TYPES}
    assert required_names <= contract_names

    for contract_type in contracts.CONTRACT_DATACLASS_TYPES:
        assert is_dataclass(contract_type), contract_type.__name__
        assert contract_type.__dataclass_params__.frozen, contract_type.__name__
        assert "__slots__" in contract_type.__dict__, contract_type.__name__

    profile = contracts.ProfileScheduleDTO(
        timezone="Asia/Shanghai",
        detected_timezone=None,
        manual_timezone=None,
        usual_sleep_time=None,
        usual_wake_time=None,
        work_start_time=None,
        work_end_time=None,
        workout_pref_window=None,
        workout_target_minutes=None,
    )
    assert not hasattr(profile, "__dict__")
    with pytest.raises(FrozenInstanceError):
        profile.timezone = "UTC"  # type: ignore[misc]

    with pytest.raises(TypeError, match="immutable_tuple_required"):
        contracts.LegacyOccurrenceContext(
            schema_version=contracts.LEGACY_OCCURRENCE_CONTEXT_SCHEMA_VERSION,
            manifest_schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            manifest_digest="manifest-digest",
            source_payload_bindings=[],  # type: ignore[arg-type]
            occurrence_facts=(),
        )


def test_task3_source_dto_field_and_annotation_contracts_are_exact():
    expected_contracts = {
        contracts.HealthDaySourceResult: (
            ("source_kind", contracts.HealthDaySourceKind),
            ("source_role", contracts.HealthDaySourceRole),
            ("revision", str | None),
            ("payload_digest", str),
            ("acquired_at", datetime | None),
            ("cutoff", datetime | None),
            ("freshness", contracts.SourceFreshness),
            ("availability", contracts.SourceAvailability),
            ("error_code", contracts.ShadowReasonCode | None),
            ("tombstone_state", contracts.TombstoneState),
        ),
        contracts.ProfileScheduleDTO: (
            ("timezone", str | None),
            ("detected_timezone", str | None),
            ("manual_timezone", str | None),
            ("usual_sleep_time", str | None),
            ("usual_wake_time", str | None),
            ("work_start_time", str | None),
            ("work_end_time", str | None),
            ("workout_pref_window", str | None),
            ("workout_target_minutes", int | None),
        ),
        contracts.BodyWeightSubsetDTO: (
            ("record_date", date | None),
            ("weight_decimal", str | None),
            ("availability", contracts.SourceAvailability),
            ("competition", contracts.SourceCompetition),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.LabAnchorSubsetDTO: (
            ("availability", contracts.SourceAvailability),
            ("anchor_missing", bool),
            ("anchor_stale", bool),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.RecoveryWearableFactDTO: (
            ("fact_kind", contracts.WearableFactKind),
            ("record_date", date | None),
            ("value_decimal", str | None),
            ("freshness", contracts.SourceFreshness),
            ("competition", contracts.SourceCompetition),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.AcuteSubsetDTO: (
            ("has_active_illness", bool),
            ("suspected_cold", bool),
            ("fever_reported", bool),
            ("should_rest", bool),
            ("guardrail_code", contracts.AcuteGuardrailCode),
            ("severity_max", int | None),
            ("classification_status", contracts.ClassifierStatus),
            ("classifier_version", str),
            ("classifier_policy_digest", str),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.RecoverySubsetDTO: (
            ("sleep", contracts.RecoveryWearableFactDTO),
            ("readiness", contracts.RecoveryWearableFactDTO),
            ("acute", contracts.AcuteSubsetDTO),
            ("poor_recovery", bool | None),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.InterventionSubsetDTO: (
            ("action_key", str),
            ("priority", int),
            ("created_at", datetime),
            ("expires_at", datetime | None),
            ("metric_key", str | None),
            ("target_value_decimal", str | None),
            ("evidence_level", str | None),
            ("check_back_date", date | None),
            ("classification_status", contracts.ClassifierStatus),
            ("training_like", bool | None),
            ("classifier_version", str),
            ("classifier_policy_digest", str),
            ("domain", contracts.HealthDomain),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.TerminalActionSubsetDTO: (
            ("record_id", str),
            ("action_key", str),
            ("status", contracts.CanonicalLifecycle),
            ("completion_provenance", contracts.CompletionProvenance),
        ),
        contracts.ActiveCycleSubsetDTO: (
            ("cycle_id", str),
            ("cycle_type", str),
            ("start_date", date),
            ("planned_end_date", date | None),
            ("primary_metric_code", str | None),
            ("outcome_status", str | None),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.ExistingDOPActionFact: (
            ("action_key", str),
            ("domain", contracts.HealthDomain),
            ("when_code", str | None),
        ),
        contracts.ExistingDOPDiagnosticDTO: (
            ("plan_id", str),
            ("status", contracts.DailyPlanStatus),
            ("actions", tuple[contracts.ExistingDOPActionFact, ...]),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.DailyPlanSubsetFactsDTO: (
            ("body_weight", contracts.BodyWeightSubsetDTO),
            ("lab_anchor", contracts.LabAnchorSubsetDTO),
            ("recovery", contracts.RecoverySubsetDTO),
            ("interventions", tuple[contracts.InterventionSubsetDTO, ...]),
            ("terminal_actions", tuple[contracts.TerminalActionSubsetDTO, ...]),
            ("active_cycle", contracts.ActiveCycleSubsetDTO | None),
            ("existing_dop", contracts.ExistingDOPDiagnosticDTO | None),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.ProgramInventoryDTO: (
            ("program_id", str),
            ("program_type", str),
            ("problem_id", str | None),
            ("started_on", date),
            ("target_end_on", date | None),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.ProtocolDTO: (
            ("protocol_id", str),
            ("domain", contracts.HealthDomain),
            ("mechanism", str | None),
            ("cadence", contracts.ProtocolCadence),
            ("time_window", str | None),
            ("completion_mode", contracts.ProtocolCompletionMode),
            ("can_default_complete", bool),
            ("manual_track_allowed", bool),
            ("program_id", str | None),
            ("source_model", str | None),
            ("source_id", str | None),
            ("trigger_date", date | None),
            ("availability", contracts.SourceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.ProtocolEventDTO: (
            ("event_id", str),
            ("protocol_id", str),
            ("event_date", date),
            ("status", contracts.CanonicalLifecycle),
            ("track", str | None),
            ("snoozed_until", datetime | None),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.ProblemFollowUpDTO: (
            ("problem_id", str),
            ("risk_level", contracts.ProblemRiskLevel),
            ("status", contracts.ProblemStatus),
            ("last_checkup", date | None),
            ("cadence", contracts.ProtocolCadence),
            ("next_due", date | None),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.MedicationSourceDTO: (
            ("storage_namespace", contracts.StorageNamespace),
            ("medication_id", str),
            ("times_per_day", int),
            ("normalized_slots", tuple[int, ...]),
            ("domain", contracts.HealthDomain),
            (
                "domain_classification_provenance",
                contracts.DomainClassificationProvenance,
            ),
            ("domain_classifier_version", str),
            ("domain_classifier_policy_digest", str),
            ("timing_relation", contracts.TimingRelation),
            ("meal_anchor", contracts.MealAnchor),
            ("start_date", date | None),
            ("end_date", date | None),
            ("occurrence_availability", contracts.OccurrenceAvailability),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.MedicationExecutionDTO: (
            ("record_id", str),
            ("medication_id", str),
            ("taken_date", date),
            ("raw_slot_present", bool),
            ("normalized_slot", int | None),
            ("status", contracts.CanonicalLifecycle),
            ("match_disposition", contracts.ExecutionMatchDisposition),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.SupplementSourceDTO: (
            ("storage_namespace", contracts.StorageNamespace),
            ("supplement_definition_id", str),
            ("timing_label", contracts.SupplementTimingLabel),
            ("timing_precision_status", contracts.TimingPrecision),
            ("sort_order", int),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.SupplementExecutionDTO: (
            ("record_id", str),
            ("supplement_definition_id", str),
            ("record_date", date),
            ("normalized_time", int | None),
            ("taken", bool),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.CalendarSourceFact: (
            ("source_id", str),
            ("provider_code", str),
            ("sync_enabled", bool),
            ("last_sync_at", datetime | None),
            ("sync_failed", bool),
        ),
        contracts.CalendarIntervalFact: (
            ("event_id", str),
            ("source_id", str),
            ("start_utc", datetime | None),
            ("end_utc", datetime | None),
            ("all_day", bool),
            ("local_start_minute", int | None),
            ("local_end_minute", int | None),
            ("utc_offset_start_minutes", int | None),
            ("utc_offset_end_minutes", int | None),
            ("fold_start", int | None),
            ("fold_end", int | None),
            ("crosses_midnight", bool | None),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.CalendarKnowledgeDTO: (
            ("state", contracts.CalendarKnowledgeState),
            ("effective_timezone", str),
            ("day_start_utc", datetime),
            ("day_end_utc", datetime),
            ("sources", tuple[contracts.CalendarSourceFact, ...]),
            ("intervals", tuple[contracts.CalendarIntervalFact, ...]),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.SafetySeamDTO: (
            ("availability", contracts.SourceAvailability),
            ("disposition", contracts.SafetyDisposition),
            ("reason_codes", tuple[contracts.ShadowReasonCode, ...]),
        ),
        contracts.HealthDaySourcePayload: (
            ("source_kind", contracts.HealthDaySourceKind),
            ("value", contracts.SourcePayloadValue),
        ),
    }

    for contract_type, expected_fields in expected_contracts.items():
        type_hints = get_type_hints(contract_type)
        actual_fields = tuple(
            (contract_field.name, type_hints[contract_field.name])
            for contract_field in fields(contract_type)
        )
        assert actual_fields == expected_fields, contract_type.__name__


def test_task3_source_dtos_exclude_raw_health_text_and_calendar_pii_fields():
    source_dto_types = (
        contracts.ProfileScheduleDTO,
        contracts.BodyWeightSubsetDTO,
        contracts.LabAnchorSubsetDTO,
        contracts.RecoveryWearableFactDTO,
        contracts.AcuteSubsetDTO,
        contracts.RecoverySubsetDTO,
        contracts.InterventionSubsetDTO,
        contracts.TerminalActionSubsetDTO,
        contracts.ActiveCycleSubsetDTO,
        contracts.ExistingDOPActionFact,
        contracts.ExistingDOPDiagnosticDTO,
        contracts.DailyPlanSubsetFactsDTO,
        contracts.ProgramInventoryDTO,
        contracts.ProtocolDTO,
        contracts.ProtocolEventDTO,
        contracts.ProblemFollowUpDTO,
        contracts.MedicationSourceDTO,
        contracts.MedicationExecutionDTO,
        contracts.SupplementSourceDTO,
        contracts.SupplementExecutionDTO,
        contracts.CalendarSourceFact,
        contracts.CalendarIntervalFact,
        contracts.CalendarKnowledgeDTO,
        contracts.SafetySeamDTO,
    )
    forbidden_fields = {
        "title",
        "name",
        "description",
        "illness_name",
        "symptom_description",
        "medication_name",
        "supplement_name",
        "dosage",
        "raw_category",
        "calendar_title",
        "location",
        "attendees",
        "uid",
        "encrypted_credentials",
        "encrypted_access_token",
        "encrypted_refresh_token",
        "error_message",
    }

    for contract_type in source_dto_types:
        actual_fields = {contract_field.name for contract_field in fields(contract_type)}
        assert actual_fields.isdisjoint(forbidden_fields), contract_type.__name__


def test_legacy_occurrence_context_schema_requires_manifest_and_payload_digest_binding_fields():
    names = {field.name for field in fields(contracts.LegacyOccurrenceContext)}
    assert {
        "schema_version",
        "manifest_schema_version",
        "manifest_digest",
        "source_payload_bindings",
        "occurrence_facts",
    } <= names
    assert not any(
        forbidden in name
        for name in names
        for forbidden in ("oracle", "delta", "participated", "title", "subtitle", "free_text")
    )

    binding_names = {
        field.name for field in fields(contracts.LegacySourcePayloadBinding)
    }
    assert {
        "storage_namespace",
        "source_kind",
        "source_id",
        "payload_digest",
    } <= binding_names
    fact_names = {field.name for field in fields(contracts.LegacyOccurrenceFacts)}
    assert {
        "storage_namespace",
        "source_id",
        "domain",
        "slots",
        "count_consistency",
        "timing_origin",
        "calendar_busy_state",
    } <= fact_names
    assert "calendar_participated" not in fact_names


def test_shared_surface_projection_and_diff_types_live_only_in_contracts_leaf():
    shared_types = (
        contracts.SurfaceRank,
        contracts.SurfaceProjectionPolicy,
        contracts.UnsealedSurfaceProjectedRow,
        contracts.UnsealedCanonicalSurfaceProjection,
        contracts.UnsealedLegacySurfaceProjection,
        contracts.SealedSurfaceProjectedRow,
        contracts.SealedCanonicalSurfaceProjection,
        contracts.SealedLegacySurfaceProjection,
        contracts.ShadowSurfaceDiffRow,
    )
    assert all(contract_type.__module__ == contracts.__name__ for contract_type in shared_types)
    assert composer.contracts is contracts
    assert not {
        contract_type.__name__ for contract_type in shared_types
    } & set(composer.__dict__)
    assert not any(
        name.startswith(("compose_", "sign_", "load_", "project_", "diff_"))
        for name in composer.__dict__
    )


def test_unsealed_and_sealed_projection_types_have_disjoint_identity_fields():
    unsealed_names = {field.name for field in fields(contracts.UnsealedSurfaceProjectedRow)}
    sealed_names = {field.name for field in fields(contracts.SealedSurfaceProjectedRow)}
    assert "identity" in unsealed_names
    assert "opaque_item_key" not in unsealed_names
    assert "opaque_item_key" in sealed_names
    assert not sealed_names & {
        "identity",
        "storage_namespace",
        "source_kind",
        "source_id",
        "local_day",
    }
    assert {field.name for field in fields(contracts.ShadowSurfaceDiffRow)} == {
        "surface",
        "diff_kind",
        "opaque_item_key",
        "diagnostic_row_ordinal",
        "reason_code",
        "canonical_coverage",
        "legacy_coverage",
    }


def test_phase1_subtree_does_not_load_parent_autouse_redis_fixtures(request):
    plugin_paths = {
        Path(path).resolve()
        for _name, plugin in request.config.pluginmanager.list_name_plugin()
        if (path := getattr(plugin, "__file__", None))
    }
    local_conftest = Path(__file__).with_name("conftest.py").resolve()
    parent_conftest = Path(__file__).parents[1] / "tests" / "conftest.py"
    assert local_conftest in plugin_paths
    assert parent_conftest.resolve() not in plugin_paths

    fixture_registry = request._fixturemanager._arg2fixturedefs
    assert "db" not in fixture_registry
    assert "_isolate_twin_cache" not in fixture_registry
    assert "_noop_twin_cache" not in fixture_registry
    assert "_health_day_shadow_default_deny" in fixture_registry

    with pytest.raises(RuntimeError, match="health_day_shadow_external_network_denied"):
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)
    for module_name in (
        "app.database",
        "app.utils.redis_cache",
        "app.services.llm.provider",
    ):
        with pytest.raises(
            RuntimeError,
            match="health_day_shadow_ambient_import_denied",
        ):
            importlib.import_module(module_name)


def test_phase1_subtree_denies_connect_ex_network_escape():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        with pytest.raises(
            RuntimeError,
            match="health_day_shadow_external_network_denied",
        ):
            candidate.connect_ex(("127.0.0.1", 9))


def test_phase1_subtree_denies_datagram_sendto_network_escape():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as candidate:
        with pytest.raises(
            RuntimeError,
            match="health_day_shadow_external_network_denied",
        ):
            candidate.sendto(b"health-day-shadow-deny-probe", ("127.0.0.1", 9))


@pytest.mark.skipif(
    not hasattr(socket.socket, "sendmsg"),
    reason="socket.sendmsg is unavailable on this platform",
)
def test_phase1_subtree_denies_sendmsg_network_escape():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as candidate:
        with pytest.raises(
            RuntimeError,
            match="health_day_shadow_external_network_denied",
        ):
            candidate.sendmsg(
                [b"health-day-shadow-deny-probe"],
                [],
                0,
                ("127.0.0.1", 9),
            )


@pytest.mark.parametrize(
    "route",
    ("from_statement", "absolute_fromlist", "relative_fromlist"),
)
def test_phase1_subtree_denies_forbidden_fromlist_import_routes(monkeypatch, route):
    monkeypatch.setattr(services_package, "llm", object(), raising=False)

    with pytest.raises(
        RuntimeError,
        match="health_day_shadow_ambient_import_denied:app.services.llm",
    ):
        if route == "from_statement":
            _import_llm_via_from_statement()
        elif route == "absolute_fromlist":
            builtins.__import__("app.services", fromlist=("llm",))
        else:
            builtins.__import__(
                "",
                {"__package__": "app.services", "__name__": "app.services._probe"},
                {},
                ("llm",),
                1,
            )


def test_phase1_subtree_allows_health_day_fromlist_imports():
    imported = builtins.__import__(
        "app.services",
        fromlist=("health_day_shadow_contracts",),
    )
    assert imported.health_day_shadow_contracts is contracts


def test_phase1_subtree_denies_importlib_dunder_import_fromlist(monkeypatch):
    monkeypatch.setattr(services_package, "llm", object(), raising=False)

    with pytest.raises(
        RuntimeError,
        match="health_day_shadow_ambient_import_denied:app.services.llm",
    ):
        importlib.__import__("app.services", fromlist=("llm",))
