from __future__ import annotations

import ast
import builtins
import importlib
import inspect
import os
import socket
import subprocess
import sys
import textwrap
import traceback
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import get_type_hints

import pytest

import app.services as services_package
from app.services import health_day_composer as composer
from app.services import health_day_shadow as shadow
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


def _daily_plan_subset() -> contracts.DailyPlanSubsetFactsDTO:
    wearable_sleep = contracts.RecoveryWearableFactDTO(
        fact_kind=contracts.WearableFactKind.SLEEP_SCORE,
        record_date=LOCAL_DAY,
        value_decimal="82.5",
        freshness=contracts.SourceFreshness.CURRENT,
        competition=contracts.SourceCompetition.UNIQUE_LATEST,
        reason_codes=(),
    )
    wearable_readiness = contracts.RecoveryWearableFactDTO(
        fact_kind=contracts.WearableFactKind.TRAINING_READINESS,
        record_date=LOCAL_DAY,
        value_decimal="71",
        freshness=contracts.SourceFreshness.CURRENT,
        competition=contracts.SourceCompetition.UNIQUE_LATEST,
        reason_codes=(),
    )
    acute = contracts.AcuteSubsetDTO(
        has_active_illness=False,
        suspected_cold=False,
        fever_reported=False,
        should_rest=False,
        guardrail_code=contracts.AcuteGuardrailCode.NONE,
        severity_max=None,
        classification_status=contracts.ClassifierStatus.CLASSIFIED,
        classifier_version="acute-v1",
        classifier_policy_digest="policy:acute-v1",
        availability=contracts.SourceAvailability.AVAILABLE,
        reason_codes=(),
    )
    return contracts.DailyPlanSubsetFactsDTO(
        body_weight=contracts.BodyWeightSubsetDTO(
            record_date=LOCAL_DAY,
            weight_decimal="70.25",
            availability=contracts.SourceAvailability.AVAILABLE,
            competition=contracts.SourceCompetition.UNIQUE_LATEST,
            reason_codes=(),
        ),
        lab_anchor=contracts.LabAnchorSubsetDTO(
            availability=contracts.SourceAvailability.UNSUPPORTED,
            anchor_missing=True,
            anchor_stale=False,
            reason_codes=(
                contracts.ShadowReasonCode.DAILY_PLAN_LAB_FLAG_POLICY_UNSUPPORTED,
            ),
        ),
        recovery=contracts.RecoverySubsetDTO(
            sleep=wearable_sleep,
            readiness=wearable_readiness,
            acute=acute,
            poor_recovery=False,
            availability=contracts.SourceAvailability.AVAILABLE,
            reason_codes=(),
        ),
        interventions=(
            contracts.InterventionSubsetDTO(
                action_key="action:decomposed-e",
                priority=2,
                created_at=AS_OF,
                expires_at=None,
                metric_key="metric:sleep",
                target_value_decimal="8.25",
                evidence_level="moderate",
                check_back_date=LOCAL_DAY,
                classification_status=contracts.ClassifierStatus.CLASSIFIED,
                training_like=False,
                classifier_version="intervention-v1",
                classifier_policy_digest="policy:intervention-v1",
                domain=contracts.HealthDomain.SLEEP,
                availability=contracts.SourceAvailability.AVAILABLE,
                reason_codes=(),
            ),
            contracts.InterventionSubsetDTO(
                action_key="action:hydrate",
                priority=3,
                created_at=AS_OF,
                expires_at=AS_OF + timedelta(hours=6),
                metric_key=None,
                target_value_decimal=None,
                evidence_level=None,
                check_back_date=None,
                classification_status=contracts.ClassifierStatus.CLASSIFIED,
                training_like=False,
                classifier_version="intervention-v1",
                classifier_policy_digest="policy:intervention-v1",
                domain=contracts.HealthDomain.HYDRATION,
                availability=contracts.SourceAvailability.AVAILABLE,
                reason_codes=(),
            ),
        ),
        terminal_actions=(
            contracts.TerminalActionSubsetDTO(
                record_id="terminal:1",
                action_key="action:done",
                status=contracts.CanonicalLifecycle.COMPLETED,
                completion_provenance=contracts.CompletionProvenance.COMPLETED,
            ),
        ),
        active_cycle=contracts.ActiveCycleSubsetDTO(
            cycle_id="cycle:1",
            cycle_type="recovery",
            start_date=LOCAL_DAY - timedelta(days=2),
            planned_end_date=LOCAL_DAY + timedelta(days=5),
            primary_metric_code="sleep_score",
            outcome_status=None,
            availability=contracts.SourceAvailability.AVAILABLE,
            reason_codes=(),
        ),
        existing_dop=contracts.ExistingDOPDiagnosticDTO(
            plan_id="dop:1",
            status=contracts.DailyPlanStatus.ACTIVE,
            actions=(
                contracts.ExistingDOPActionFact(
                    action_key="dop:action:1",
                    domain=contracts.HealthDomain.SLEEP,
                    when_code="evening",
                ),
                contracts.ExistingDOPActionFact(
                    action_key="dop:action:2",
                    domain=contracts.HealthDomain.HYDRATION,
                    when_code=None,
                ),
            ),
            availability=contracts.SourceAvailability.AVAILABLE,
            reason_codes=(),
        ),
        reason_codes=(contracts.ShadowReasonCode.DAILY_PLAN_ADVICE_GUARD_UNSUPPORTED,),
    )


def _protocols() -> tuple[contracts.ProtocolDTO, ...]:
    return (
        contracts.ProtocolDTO(
            protocol_id="protocol:1",
            domain=contracts.HealthDomain.CHECKUP,
            mechanism="review-e\u0301",
            cadence=contracts.ProtocolCadence.WEEKLY,
            time_window="09:00-10:00",
            completion_mode=contracts.ProtocolCompletionMode.MANUAL,
            can_default_complete=False,
            manual_track_allowed=True,
            program_id="program:1",
            source_model="health_problem",
            source_id="9",
            trigger_date=None,
            availability=contracts.SourceAvailability.AVAILABLE,
            reason_codes=(),
        ),
    )


class _CountingKeyProvider:
    __slots__ = ("calls", "key_id", "root_key")

    def __init__(
        self,
        *,
        key_id: str = "test_v1",
        root_key: bytes = bytes(range(32)),
    ) -> None:
        self.calls = 0
        self.key_id = key_id
        self.root_key = root_key

    def read_key(self) -> tuple[str, bytes]:
        self.calls += 1
        return self.key_id, self.root_key

    def __repr__(self) -> str:
        return "_CountingKeyProvider(redacted=True)"


def _signing_source(
    *,
    source_kind: contracts.HealthDaySourceKind = (
        contracts.HealthDaySourceKind.PROFILE_SCHEDULE
    ),
    value: contracts.SourcePayloadValue | None = None,
) -> shadow.SourceSigningInput:
    if value is None:
        value = _profile_schedule()
    return shadow.SourceSigningInput(
        source_kind=source_kind,
        source_role=contracts.HealthDaySourceRole.CANDIDATE,
        revision="revision:v1",
        acquired_at=AS_OF - timedelta(minutes=5),
        cutoff=AS_OF,
        freshness=contracts.SourceFreshness.CURRENT,
        availability=contracts.SourceAvailability.AVAILABLE,
        error_code=None,
        tombstone_state=contracts.TombstoneState.UNKNOWN,
        value=value,
    )


def _signing_manifest(
    *,
    sources: tuple[shadow.SourceSigningInput, ...] | None = None,
) -> shadow.ManifestSigningInput:
    if sources is None:
        sources = (_signing_source(),)
    return shadow.ManifestSigningInput(
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
        sources=sources,
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
        _manifest(
            as_of=datetime(2026, 8, 15, 20, 0, tzinfo=timezone(timedelta(hours=8)))
        )
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
    assert (
        artifact.manifest_schema_version == contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION
    )
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
    contract_names = {
        contract_type.__name__ for contract_type in contracts.CONTRACT_DATACLASS_TYPES
    }
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
        actual_fields = {
            contract_field.name for contract_field in fields(contract_type)
        }
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
        for forbidden in (
            "oracle",
            "delta",
            "participated",
            "title",
            "subtitle",
            "free_text",
        )
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
    assert all(
        contract_type.__module__ == contracts.__name__ for contract_type in shared_types
    )
    assert composer.contracts is contracts
    assert not {contract_type.__name__ for contract_type in shared_types} & set(
        composer.__dict__
    )
    assert not any(
        name.startswith(("compose_", "sign_", "load_", "project_", "diff_"))
        for name in composer.__dict__
    )


def test_unsealed_and_sealed_projection_types_have_disjoint_identity_fields():
    unsealed_names = {
        field.name for field in fields(contracts.UnsealedSurfaceProjectedRow)
    }
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


def test_same_manifest_and_key_produce_same_digest():
    first = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    second = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )

    assert first.shadow_manifest_digest == second.shadow_manifest_digest
    assert first.manifest.sources[0].payload_digest == (
        second.manifest.sources[0].payload_digest
    )
    assert first == second
    assert (
        shadow.verify_digest_bound_shadow_bundle(
            first,
            _CountingKeyProvider(),
        )
        is None
    )


def test_any_composition_field_change_changes_source_and_manifest_digest():
    source = _signing_source()
    baseline = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(sources=(source,)),
        _CountingKeyProvider(),
    )
    changes = (
        replace(
            source,
            source_kind=contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
            value=(),
        ),
        replace(source, source_role=contracts.HealthDaySourceRole.DIAGNOSTIC),
        replace(source, revision="revision:v2"),
        replace(source, acquired_at=AS_OF - timedelta(minutes=6)),
        replace(source, cutoff=AS_OF - timedelta(seconds=1)),
        replace(source, freshness=contracts.SourceFreshness.STALE),
        replace(source, availability=contracts.SourceAvailability.UNAVAILABLE),
        replace(
            source,
            error_code=contracts.ShadowReasonCode.SOURCE_REVISION_MISSING,
        ),
        replace(source, tombstone_state=contracts.TombstoneState.PRESENT),
        replace(
            source,
            value=replace(_profile_schedule(), usual_wake_time="07:15"),
        ),
    )

    for changed_source in changes:
        changed = shadow.build_digest_bound_shadow_bundle(
            _signing_manifest(sources=(changed_source,)),
            _CountingKeyProvider(),
        )
        assert changed.manifest.sources[0].payload_digest != (
            baseline.manifest.sources[0].payload_digest
        )
        assert changed.shadow_manifest_digest != baseline.shadow_manifest_digest


def test_any_source_or_nested_tuple_order_change_changes_digest():
    daily_plan = _daily_plan_subset()
    original_source = _signing_source(
        source_kind=contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
        value=daily_plan,
    )
    reordered_source = replace(
        original_source,
        value=replace(
            daily_plan,
            interventions=tuple(reversed(daily_plan.interventions)),
        ),
    )
    original = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(sources=(original_source,)),
        _CountingKeyProvider(),
    )
    reordered = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(sources=(reordered_source,)),
        _CountingKeyProvider(),
    )

    assert reordered.payloads[0].value.interventions == tuple(  # type: ignore[union-attr]
        reversed(daily_plan.interventions)
    )
    assert reordered.manifest.sources[0].payload_digest != (
        original.manifest.sources[0].payload_digest
    )
    assert reordered.shadow_manifest_digest != original.shadow_manifest_digest

    ordered_sources = (
        _signing_source(),
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.PROTOCOLS,
            value=_protocols(),
        ),
    )
    with pytest.raises(ValueError, match="signing_sources_out_of_order"):
        _signing_manifest(sources=tuple(reversed(ordered_sources)))


def test_forged_same_manifest_with_changed_payload_is_rejected():
    bundle = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    object.__setattr__(
        bundle.payloads[0],
        "value",
        replace(_profile_schedule(), usual_sleep_time="23:30"),
    )

    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_digest_verification_failed:source_payload:0",
    ) as exc_info:
        shadow.verify_digest_bound_shadow_bundle(bundle, _CountingKeyProvider())
    assert "23:30" not in str(exc_info.value)
    assert bundle.manifest.sources[0].payload_digest not in str(exc_info.value)


def test_source_and_manifest_signing_inputs_are_frozen_slots_with_exact_fields():
    assert tuple(field.name for field in fields(shadow.SourceSigningInput)) == (
        "source_kind",
        "source_role",
        "revision",
        "acquired_at",
        "cutoff",
        "freshness",
        "availability",
        "error_code",
        "tombstone_state",
        "value",
    )
    assert tuple(field.name for field in fields(shadow.ManifestSigningInput)) == (
        "schema_version",
        "owner_id",
        "local_day",
        "timezone",
        "as_of",
        "transaction",
        "sources",
    )
    assert tuple(field.name for field in fields(shadow.ShadowManifestIdentity)) == (
        "schema_version",
        "owner_id",
        "local_day",
    )
    for input_type in (
        shadow.SourceSigningInput,
        shadow.ManifestSigningInput,
        shadow.ShadowManifestIdentity,
    ):
        assert input_type.__dataclass_params__.frozen
        assert "__slots__" in input_type.__dict__
        assert not hasattr(
            _signing_source()
            if input_type is shadow.SourceSigningInput
            else (
                _signing_manifest()
                if input_type is shadow.ManifestSigningInput
                else shadow.ShadowManifestIdentity(
                    schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
                    owner_id="42",
                    local_day=LOCAL_DAY,
                )
            ),
            "__dict__",
        )
    source_value_field = fields(shadow.SourceSigningInput)[-1]
    assert source_value_field.name == "value"
    assert source_value_field.repr is False
    with pytest.raises(FrozenInstanceError):
        _signing_source().revision = "revision:v2"  # type: ignore[misc]


def test_source_signing_input_has_no_caller_supplied_payload_digest():
    assert "payload_digest" not in {
        field.name for field in fields(shadow.SourceSigningInput)
    }
    assert tuple(
        inspect.signature(shadow.build_digest_bound_shadow_bundle).parameters
    ) == (
        "manifest_input",
        "key_provider",
    )
    values = {
        field.name: getattr(_signing_source(), field.name)
        for field in fields(shadow.SourceSigningInput)
    }
    values["payload_digest"] = "caller-forged"
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        shadow.SourceSigningInput(**values)  # type: ignore[arg-type]


def test_bundle_builder_reads_key_provider_exactly_once():
    provider = _CountingKeyProvider()
    bundle = shadow.build_digest_bound_shadow_bundle(_signing_manifest(), provider)

    assert provider.calls == 1
    assert bundle.shadow_manifest_digest.startswith("test_v1.")
    assert all(
        source.payload_digest.startswith("test_v1.")
        for source in bundle.manifest.sources
    )


@pytest.mark.parametrize(
    "field_name",
    (
        "source_kind",
        "source_role",
        "revision",
        "payload_digest",
        "acquired_at",
        "cutoff",
        "freshness",
        "availability",
        "error_code",
        "tombstone_state",
        "payload_value",
        "schema_version",
        "owner_id",
        "local_day",
        "timezone",
        "as_of",
        "transaction",
        "sources",
        "manifest_digest",
    ),
)
def test_verify_digest_bound_bundle_rejects_each_forged_source_and_manifest_field(
    field_name: str,
):
    bundle = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    source = bundle.manifest.sources[0]
    source_changes = {
        "source_kind": contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
        "source_role": contracts.HealthDaySourceRole.DIAGNOSTIC,
        "revision": "revision:v2",
        "payload_digest": f"other.{('0a' * 32)}",
        "acquired_at": AS_OF - timedelta(minutes=9),
        "cutoff": AS_OF - timedelta(seconds=1),
        "freshness": contracts.SourceFreshness.STALE,
        "availability": contracts.SourceAvailability.UNAVAILABLE,
        "error_code": contracts.ShadowReasonCode.SOURCE_REVISION_MISSING,
        "tombstone_state": contracts.TombstoneState.PRESENT,
    }
    manifest_changes = {
        "schema_version": "health_day_shadow.future",
        "owner_id": "43",
        "local_day": LOCAL_DAY + timedelta(days=1),
        "timezone": "UTC",
        "as_of": AS_OF + timedelta(seconds=1),
    }
    if field_name in source_changes:
        object.__setattr__(
            bundle.manifest,
            "sources",
            (replace(source, **{field_name: source_changes[field_name]}),),
        )
    elif field_name == "payload_value":
        object.__setattr__(
            bundle.payloads[0],
            "value",
            replace(_profile_schedule(), usual_wake_time="07:31"),
        )
    elif field_name in manifest_changes:
        object.__setattr__(bundle.manifest, field_name, manifest_changes[field_name])
    elif field_name == "transaction":
        object.__setattr__(bundle.manifest.transaction, "read_only", False)
    elif field_name == "sources":
        object.__setattr__(bundle.manifest, "sources", ())
    else:
        object.__setattr__(
            bundle,
            "shadow_manifest_digest",
            f"other.{('0b' * 32)}",
        )

    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_digest_verification_failed",
    ) as exc_info:
        shadow.verify_digest_bound_shadow_bundle(bundle, _CountingKeyProvider())
    message = str(exc_info.value)
    assert "07:31" not in message
    assert "revision:v2" not in message
    assert "other." not in message


def test_external_revision_binds_revision_acquired_at_cutoff_and_payload():
    source = _signing_source()
    variants = (
        replace(source, revision="external:revision-2"),
        replace(source, acquired_at=source.acquired_at - timedelta(microseconds=1)),
        replace(source, cutoff=source.cutoff - timedelta(microseconds=1)),
        replace(
            source,
            value=replace(_profile_schedule(), detected_timezone="America/New_York"),
        ),
    )
    baseline = shadow.sign_shadow_source_payload(source, _CountingKeyProvider())
    assert all(
        shadow.sign_shadow_source_payload(variant, _CountingKeyProvider()) != baseline
        for variant in variants
    )


def test_digest_uses_separate_health_day_shadow_domain():
    assert shadow.HEALTH_DAY_SHADOW_DOMAIN == b"health-day-shadow-v1"
    canonical_envelope = b"{}"
    frame = shadow._frame_shadow_envelope(canonical_envelope)
    assert frame == (b"\x00\x00\x00\x14health-day-shadow-v1\x00\x00\x00\x02{}")
    assert frame.count(b"health-day-shadow-v1") == 1


def test_manifest_source_and_item_use_independent_hkdf_purposes():
    root_key = bytes(range(32))
    keys = {
        purpose: shadow._derive_purpose_key(root_key, purpose)
        for purpose in ("source-payload", "manifest-digest", "item-key")
    }
    assert len(set(keys.values())) == 3
    assert all(len(value) == 32 for value in keys.values())
    for signer in (
        shadow.sign_shadow_source_payload,
        shadow.sign_shadow_manifest,
        shadow.sign_shadow_item_identity,
    ):
        assert "purpose" not in inspect.signature(signer).parameters
    with pytest.raises(shadow.ShadowSigningError, match="shadow_purpose_invalid"):
        shadow._derive_purpose_key(root_key, "authorization")


def test_item_key_is_slot_sensitive_and_title_independent():
    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
    )
    base = _identity()
    changed_slot = replace(base, slot_local_minute=481)
    first = shadow.sign_shadow_item_identity(
        manifest_identity,
        base,
        _CountingKeyProvider(),
    )
    repeated = shadow.sign_shadow_item_identity(
        manifest_identity,
        base,
        _CountingKeyProvider(),
    )
    changed = shadow.sign_shadow_item_identity(
        manifest_identity,
        changed_slot,
        _CountingKeyProvider(),
    )

    assert first == repeated
    assert first != changed
    assert not {
        "title",
        "subtitle",
        "free_text",
        "purpose",
    } & set(inspect.signature(shadow.sign_shadow_item_identity).parameters)


def test_item_key_is_storage_namespace_sensitive_for_equal_numeric_ids():
    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
    )
    medication = shadow.sign_shadow_item_identity(
        manifest_identity,
        _identity(contracts.StorageNamespace.MEDICATION_ROW),
        _CountingKeyProvider(),
    )
    supplement = shadow.sign_shadow_item_identity(
        manifest_identity,
        _identity(contracts.StorageNamespace.SUPPLEMENT_DEFINITION),
        _CountingKeyProvider(),
    )
    assert medication != supplement


def test_sign_shadow_item_identity_rejects_missing_or_unknown_storage_namespace():
    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
    )
    with pytest.raises(shadow.ShadowSigningError, match="item_identity_invalid"):
        shadow.sign_shadow_item_identity(
            manifest_identity,
            None,  # type: ignore[arg-type]
            _CountingKeyProvider(),
        )

    forged = _identity()
    object.__setattr__(forged, "storage_namespace", "future_namespace")
    with pytest.raises(shadow.ShadowSigningError, match="item_identity_invalid"):
        shadow.sign_shadow_item_identity(
            manifest_identity,
            forged,
            _CountingKeyProvider(),
        )


def test_item_key_rejects_manifest_and_identity_local_day_mismatch():
    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY + timedelta(days=1),
    )
    with pytest.raises(
        shadow.ShadowSigningError,
        match="item_identity_local_day_mismatch",
    ):
        shadow.sign_shadow_item_identity(
            manifest_identity,
            _identity(),
            _CountingKeyProvider(),
        )


@pytest.mark.parametrize(
    "provider",
    (
        None,
        object(),
        type("MissingKeyProvider", (), {"read_key": lambda self: None})(),
        type(
            "ListKeyProvider",
            (),
            {"read_key": lambda self: ["test_v1", bytes(range(32))]},
        )(),
        _CountingKeyProvider(key_id="bad$key"),
        _CountingKeyProvider(root_key=b"short-key"),
        _CountingKeyProvider(root_key=bytearray(range(32))),  # type: ignore[arg-type]
    ),
)
def test_missing_unknown_or_short_key_fails_closed(provider):
    with pytest.raises(shadow.ShadowSigningError) as exc_info:
        shadow.sign_shadow_source_payload(_signing_source(), provider)
    message = str(exc_info.value)
    assert "short-key" not in message
    assert "bad$key" not in message


def test_jcs_subset_matches_rfc_8785_string_and_literal_golden_vector():
    # RFC 8785 §3.2 strings/literals, restricted to this no-float domain.
    value = {
        "literals": [None, True, False],
        "string": '€$\u000f\nA\'B"\\\\"/',
    }
    expected = (
        b'{"literals":[null,true,false],"string":"\xe2\x82\xac$'
        b'\\u000f\\nA\'B\\"\\\\\\\\\\"/"}'
    )
    assert shadow.canonical_shadow_jcs_subset_bytes(value) == expected


@pytest.mark.parametrize(
    "value",
    (
        1.0,
        datetime(2026, 8, 15, tzinfo=UTC),
        {"非ascii": "value"},
        {"key": "bad\ud800value"},
        {"bad\udfffkey": "value"},
        b"bytes",
        bytearray(b"bytes"),
        type("ListSubclass", (list,), {})([1]),
        type("DictSubclass", (dict,), {})({"key": 1}),
    ),
)
def test_jcs_subset_rejects_float_datetime_non_ascii_keys_and_lone_surrogates(
    value,
):
    with pytest.raises(shadow.ShadowSigningError) as exc_info:
        shadow.canonical_shadow_jcs_subset_bytes(value)
    assert "bad" not in str(exc_info.value)
    assert "非ascii" not in str(exc_info.value)


def test_jcs_subset_rejects_integer_outside_ijson_safe_range():
    lower = -(2**53 - 1)
    upper = 2**53 - 1
    assert shadow.canonical_shadow_jcs_subset_bytes([lower, upper]) == (
        b"[-9007199254740991,9007199254740991]"
    )
    for value in (lower - 1, upper + 1):
        with pytest.raises(
            shadow.ShadowSigningError,
            match="jcs_integer_out_of_range",
        ):
            shadow.canonical_shadow_jcs_subset_bytes(value)


def test_jcs_subset_preserves_unicode_without_normalization():
    composed = shadow.canonical_shadow_jcs_subset_bytes({"value": "é"})
    decomposed = shadow.canonical_shadow_jcs_subset_bytes({"value": "e\u0301"})

    assert composed == b'{"value":"\xc3\xa9"}'
    assert decomposed == b'{"value":"e\xcc\x81"}'
    assert composed != decomposed


def test_complete_signing_protocol_matches_golden_canonical_frame_key_and_mac():
    # Independently reviewed fixed vector; expected values are never generated by
    # the helper under test. It covers every manifest/source field plus nested
    # arrays/objects, I-JSON integer bounds, control text and decomposed Unicode.
    payload = {
        "schema_version": "health_day_shadow.v1",
        "owner_id": "42",
        "local_day": "2026-03-08",
        "timezone": "America/New_York",
        "as_of": "2026-03-08T07:00:00.123456Z",
        "transaction": {
            "dialect": "postgresql",
            "isolation": "repeatable_read",
            "read_only": True,
        },
        "sources": [
            {
                "source_kind": "daily_plan_subset",
                "source_role": "candidate",
                "revision": "rev:golden-1",
                "payload_digest": (
                    "golden_v1."
                    "abababababababababababababababababababababababababababababababab"
                ),
                "acquired_at": "2026-03-08T06:59:59.000001Z",
                "cutoff": None,
                "freshness": "current",
                "availability": "available",
                "error_code": None,
                "tombstone_state": "unknown",
                "value": {
                    "array": [
                        None,
                        True,
                        False,
                        -9007199254740991,
                        9007199254740991,
                        "line\ncontrol\u000f",
                        "e\u0301",
                    ],
                    "nested": {"alpha": "€", "empty": None},
                },
            }
        ],
    }
    expected_canonical = (
        b'{"key_id":"golden_v1","payload":{"as_of":"2026-03-08T07:00:00.123456Z",'
        b'"local_day":"2026-03-08","owner_id":"42","schema_version":"health_day_shadow.v1",'
        b'"sources":[{"acquired_at":"2026-03-08T06:59:59.000001Z","availability":"available",'
        b'"cutoff":null,"error_code":null,"freshness":"current","payload_digest":"golden_v1.'
        b'abababababababababababababababababababababababababababababababab",'
        b'"revision":"rev:golden-1","source_kind":"daily_plan_subset","source_role":"candidate",'
        b'"tombstone_state":"unknown","value":{"array":[null,true,false,-9007199254740991,'
        b'9007199254740991,"line\\ncontrol\\u000f","e\xcc\x81"],"nested":{"alpha":"\xe2\x82\xac",'
        b'"empty":null}}}],"timezone":"America/New_York","transaction":{"dialect":"postgresql",'
        b'"isolation":"repeatable_read","read_only":true}},"purpose":"manifest-digest",'
        b'"schema_version":"health_day_shadow.v1"}'
    )
    expected_frame_hex = (
        "000000146865616c74682d6461792d736861646f772d763100000335"
        "7b226b65795f6964223a22676f6c64656e5f7631222c227061796c6f6164223a7b2261735f6f66223a22323032362d30332d30385430373a30303a30302e3132333435365a222c226c6f63616c5f646179223a22323032362d30332d3038222c226f776e65725f6964223a223432222c22736368656d615f76657273696f6e223a226865616c74685f6461795f736861646f772e7631222c22736f7572636573223a5b7b2261637175697265645f6174223a22323032362d30332d30385430363a35393a35392e3030303030315a222c22617661696c6162696c697479223a22617661696c61626c65222c226375746f6666223a6e756c6c2c226572726f725f636f6465223a6e756c6c2c2266726573686e657373223a2263757272656e74222c227061796c6f61645f646967657374223a22676f6c64656e5f76312e61626162616261626162616261626162616261626162616261626162616261626162616261626162616261626162616261626162616261626162616261626162222c227265766973696f6e223a227265763a676f6c64656e2d31222c22736f757263655f6b696e64223a226461696c795f706c616e5f737562736574222c22736f757263655f726f6c65223a2263616e646964617465222c22746f6d6273746f6e655f7374617465223a22756e6b6e6f776e222c2276616c7565223a7b226172726179223a5b6e756c6c2c747275652c66616c73652c2d393030373139393235343734303939312c393030373139393235343734303939312c226c696e655c6e636f6e74726f6c5c7530303066222c2265cc81225d2c226e6573746564223a7b22616c706861223a22e282ac222c22656d707479223a6e756c6c7d7d7d5d2c2274696d657a6f6e65223a22416d65726963612f4e65775f596f726b222c227472616e73616374696f6e223a7b226469616c656374223a22706f737467726573716c222c2269736f6c6174696f6e223a2272657065617461626c655f72656164222c22726561645f6f6e6c79223a747275657d7d2c22707572706f7365223a226d616e69666573742d646967657374222c22736368656d615f76657273696f6e223a226865616c74685f6461795f736861646f772e7631227d"
    )

    canonical = shadow._canonical_signing_envelope_bytes(
        payload,
        purpose="manifest-digest",
        key_id="golden_v1",
    )
    frame = shadow._frame_shadow_envelope(canonical)
    assert canonical == expected_canonical
    assert frame.hex() == expected_frame_hex
    assert shadow._derive_purpose_key(bytes(range(32)), "source-payload").hex() == (
        "1f02b1ebc70527189c16b9fcc0a253e5d65befa1727e3c2af7c50771784cdc99"
    )
    assert shadow._derive_purpose_key(bytes(range(32)), "manifest-digest").hex() == (
        "ba0572e3ddc4fd0d5b3cc46754914f8108c0fe9cbea7389821269086f73ff5da"
    )
    assert shadow._derive_purpose_key(bytes(range(32)), "item-key").hex() == (
        "424a2ef27bebe3a501090e5417296eb24319f40410a36425bba317a5f99b3882"
    )
    assert (
        shadow._sign_projected_payload(
            payload,
            purpose="manifest-digest",
            key_id="golden_v1",
            root_key=bytes(range(32)),
        )
        == "golden_v1.e877be0a28065ad8a2b0f951371f9fb9657833175c7f3fc6bc0c2d95edbc4800"
    )


def test_absent_null_unknown_field_and_scalar_subclass_fail_closed():
    values = {
        field.name: getattr(_signing_source(), field.name)
        for field in fields(shadow.SourceSigningInput)
    }
    values.pop("acquired_at")
    with pytest.raises(TypeError, match="missing.*acquired_at"):
        shadow.SourceSigningInput(**values)  # type: ignore[arg-type]

    explicit_null = _signing_source()
    assert replace(explicit_null, acquired_at=None).acquired_at is None
    values = {
        field.name: getattr(explicit_null, field.name)
        for field in fields(shadow.SourceSigningInput)
    }
    values["future_field"] = None
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        shadow.SourceSigningInput(**values)  # type: ignore[arg-type]

    class IntSubclass(int):
        pass

    class StrSubclass(str):
        pass

    for value in (IntSubclass(1), StrSubclass("value")):
        with pytest.raises(shadow.ShadowSigningError):
            shadow.canonical_shadow_jcs_subset_bytes(value)
    with pytest.raises(
        shadow.ShadowSigningError,
        match="source_signing_input_field_type_invalid",
    ):
        replace(explicit_null, revision=StrSubclass("revision:v1"))


def test_safe_repr_scope_hides_signing_value_and_sanitizes_errors_without_a_bundle_repr_contract():
    secret_value = replace(
        _profile_schedule(),
        usual_sleep_time="private-health-value-23:10",
    )
    signing_input = _signing_source(value=secret_value)
    assert "private-health-value-23:10" not in repr(signing_input)
    assert "value=" not in repr(signing_input)

    malformed = _signing_source()
    object.__setattr__(malformed, "value", "private-health-value-invalid")
    with pytest.raises(shadow.ShadowSigningError) as exc_info:
        shadow.sign_shadow_source_payload(malformed, _CountingKeyProvider())
    assert "private-health-value-invalid" not in str(exc_info.value)
    assert "__repr__" in contracts.HealthDayShadowBundle.__dict__
    assert contracts.HealthDayShadowBundle.__repr__ is not (
        shadow.SourceSigningInput.__repr__
    )

    class LeakyProvider:
        def read_key(self):
            raise RuntimeError("private-key-material-must-not-leak")

    with pytest.raises(shadow.ShadowSigningError) as provider_exc:
        shadow.sign_shadow_source_payload(signing_input, LeakyProvider())
    formatted = "".join(
        traceback.format_exception(
            type(provider_exc.value),
            provider_exc.value,
            provider_exc.value.__traceback__,
        )
    )
    assert "private-key-material-must-not-leak" not in formatted

    class DescriptorLeakyProvider:
        @property
        def read_key(self):
            raise RuntimeError("descriptor-key-material-must-not-leak")

    with pytest.raises(shadow.ShadowSigningError) as descriptor_exc:
        shadow.sign_shadow_source_payload(signing_input, DescriptorLeakyProvider())
    descriptor_formatted = "".join(
        traceback.format_exception(
            type(descriptor_exc.value),
            descriptor_exc.value,
            descriptor_exc.value.__traceback__,
        )
    )
    assert "descriptor-key-material-must-not-leak" not in descriptor_formatted

    oversized_owner = "9" * 5000
    oversized_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id=oversized_owner,
        local_day=LOCAL_DAY,
    )
    assert oversized_identity.owner_id == oversized_owner


def test_bind_signed_shadow_item_key_accepts_only_task2_token_and_preserves_other_fields():
    unsigned_item = _item(contracts.CanonicalLifecycle.PENDING)
    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
    )
    expected_token = shadow.sign_shadow_item_identity(
        manifest_identity,
        unsigned_item.identity,
        _CountingKeyProvider(),
    )
    signed_item = shadow.bind_signed_shadow_item_key(
        unsigned_item,
        manifest_identity=manifest_identity,
        key_provider=_CountingKeyProvider(),
    )

    assert signed_item.shadow_item_key == expected_token
    for contract_field in fields(contracts.HealthDayShadowItem):
        if contract_field.name != "shadow_item_key":
            assert getattr(signed_item, contract_field.name) == getattr(
                unsigned_item,
                contract_field.name,
            )
    assert (
        "token" not in inspect.signature(shadow.bind_signed_shadow_item_key).parameters
    )
    with pytest.raises(TypeError, match="unexpected keyword argument"):
        shadow.bind_signed_shadow_item_key(  # type: ignore[call-arg]
            unsigned_item,
            manifest_identity=manifest_identity,
            key_provider=_CountingKeyProvider(),
            token=f"forged.{('0a' * 32)}",
        )


def test_private_shadow_item_binder_has_only_the_task2_service_import_edge():
    service_dir = Path(contracts.__file__).parent
    importers = set()
    for path in service_dir.glob("health_day*.py"):
        if path.name == "health_day_shadow_contracts.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and any(
                alias.name == "_SIGNED_SHADOW_ITEM_KEY_BINDER" for alias in node.names
            ):
                importers.add(path.name)
    assert importers == {"health_day_shadow.py"}


def test_source_payload_dispatch_is_strict_by_source_kind_even_for_empty_tuples():
    protocols = _signing_source(
        source_kind=contracts.HealthDaySourceKind.PROTOCOLS,
        value=(),
    )
    supplements = _signing_source(
        source_kind=contracts.HealthDaySourceKind.SUPPLEMENTS,
        value=(),
    )
    assert shadow.sign_shadow_source_payload(
        protocols,
        _CountingKeyProvider(),
    ) != shadow.sign_shadow_source_payload(supplements, _CountingKeyProvider())

    with pytest.raises(shadow.ShadowSigningError, match="source_value_schema_mismatch"):
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.PROFILE_SCHEDULE,
            value=(),
        )
    with pytest.raises(shadow.ShadowSigningError, match="source_value_schema_mismatch"):
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.SUPPLEMENTS,
            value=_protocols(),
        )


@pytest.mark.parametrize(
    "bad_decimal",
    ("70.0", "070", "1e3", "1E+3", "-0", "-0.0", "NaN", "Infinity", ""),
)
def test_signing_projectors_reject_noncanonical_decimal_strings(bad_decimal: str):
    value = replace(
        _daily_plan_subset(),
        body_weight=replace(
            _daily_plan_subset().body_weight,
            weight_decimal=bad_decimal,
        ),
    )
    with pytest.raises(
        shadow.ShadowSigningError,
        match="source_decimal_not_canonical",
    ) as exc_info:
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
            value=value,
        )
    if bad_decimal:
        assert bad_decimal not in str(exc_info.value)


def test_signing_decimal_projection_preserves_large_fixed_point_exactly():
    exact_decimal = "123456789012345678901234567890.1234567890123456789"
    daily_plan = _daily_plan_subset()
    value = replace(
        daily_plan,
        body_weight=replace(
            daily_plan.body_weight,
            weight_decimal=exact_decimal,
        ),
    )
    source_input = _signing_source(
        source_kind=contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
        value=value,
    )
    projected = shadow._project_source_signing_input(source_input)
    assert projected["value"]["body_weight"]["weight_decimal"] == exact_decimal


@pytest.mark.parametrize("bad_identifier", ("", "contains space", "药物:1"))
def test_signing_projectors_reject_empty_or_non_ascii_identifiers(
    bad_identifier: str,
):
    value = (
        contracts.ProgramInventoryDTO(
            program_id=bad_identifier,
            program_type="recovery",
            problem_id=None,
            started_on=LOCAL_DAY,
            target_end_on=None,
            availability=contracts.SourceAvailability.AVAILABLE,
            reason_codes=(),
        ),
    )
    with pytest.raises(
        shadow.ShadowSigningError,
        match="source_identifier_invalid",
    ) as exc_info:
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
            value=value,
        )
    if bad_identifier:
        assert bad_identifier not in str(exc_info.value)


def test_signing_source_projectors_are_explicit_and_do_not_walk_dataclasses():
    source = Path(shadow.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "asdict(",
        "fields(",
        "vars(",
        ".__dict__",
        "dataclasses.asdict",
    ):
        assert forbidden not in source
    assert set(shadow._SOURCE_PAYLOAD_PROJECTORS) == set(
        contracts.HEALTH_DAY_SOURCE_ORDER_V1
    )


def test_digest_is_stable_across_fresh_python_processes():
    expected = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    ).shadow_manifest_digest
    script = textwrap.dedent(
        """
        from datetime import UTC, date, datetime, timedelta
        from app.services import health_day_shadow as shadow
        from app.services import health_day_shadow_contracts as contracts

        class Provider:
            def read_key(self):
                return "test_v1", bytes(range(32))

        as_of = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
        value = contracts.ProfileScheduleDTO(
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
        source = shadow.SourceSigningInput(
            source_kind=contracts.HealthDaySourceKind.PROFILE_SCHEDULE,
            source_role=contracts.HealthDaySourceRole.CANDIDATE,
            revision="revision:v1",
            acquired_at=as_of - timedelta(minutes=5),
            cutoff=as_of,
            freshness=contracts.SourceFreshness.CURRENT,
            availability=contracts.SourceAvailability.AVAILABLE,
            error_code=None,
            tombstone_state=contracts.TombstoneState.UNKNOWN,
            value=value,
        )
        manifest = shadow.ManifestSigningInput(
            schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            owner_id="42",
            local_day=date(2026, 8, 15),
            timezone="Asia/Shanghai",
            as_of=as_of,
            transaction=contracts.HealthDayTransaction(
                dialect=contracts.TransactionDialect.POSTGRESQL,
                isolation=contracts.TransactionIsolation.REPEATABLE_READ,
                read_only=True,
            ),
            sources=(source,),
        )
        print(shadow.build_digest_bound_shadow_bundle(manifest, Provider()).shadow_manifest_digest)
        """
    )
    backend_dir = Path(__file__).parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(backend_dir)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=backend_dir,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.stderr == ""
    assert result.stdout.strip() == expected
