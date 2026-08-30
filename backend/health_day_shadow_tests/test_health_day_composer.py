from __future__ import annotations

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import os
import socket
import subprocess
import sys
import textwrap
import traceback
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
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


def _medication_source() -> contracts.MedicationSourceDTO:
    return contracts.MedicationSourceDTO(
        storage_namespace=contracts.StorageNamespace.MEDICATION_ROW,
        medication_id="medication:7",
        times_per_day=2,
        normalized_slots=(8 * 60, 20 * 60),
        domain=contracts.HealthDomain.MEDICATION,
        domain_classification_provenance=(
            contracts.DomainClassificationProvenance.LEGACY_DEFAULT_MEDICATION
        ),
        domain_classifier_version="domain:v1",
        domain_classifier_policy_digest="policy:domain-v1",
        timing_relation=contracts.TimingRelation.FIXED,
        meal_anchor=contracts.MealAnchor.NONE,
        start_date=LOCAL_DAY - timedelta(days=1),
        end_date=None,
        occurrence_availability=contracts.OccurrenceAvailability.AVAILABLE,
        reason_codes=(),
    )


def _protocol_event() -> contracts.ProtocolEventDTO:
    return contracts.ProtocolEventDTO(
        event_id="event:1",
        protocol_id="protocol:1",
        event_date=LOCAL_DAY,
        status=contracts.CanonicalLifecycle.PENDING,
        track=None,
        snoozed_until=None,
        reason_codes=(),
    )


def _calendar_knowledge() -> contracts.CalendarKnowledgeDTO:
    calendar_sources = (
        contracts.CalendarSourceFact(
            source_id="calendar-source:1",
            provider_code="provider:one",
            sync_enabled=True,
            last_sync_at=AS_OF - timedelta(minutes=10),
            sync_failed=False,
        ),
        contracts.CalendarSourceFact(
            source_id="calendar-source:2",
            provider_code="provider:two",
            sync_enabled=True,
            last_sync_at=AS_OF - timedelta(minutes=5),
            sync_failed=False,
        ),
    )
    intervals = (
        contracts.CalendarIntervalFact(
            event_id="calendar-event:1",
            source_id="calendar-source:1",
            start_utc=AS_OF + timedelta(hours=1),
            end_utc=AS_OF + timedelta(hours=2),
            all_day=False,
            local_start_minute=20 * 60,
            local_end_minute=21 * 60,
            utc_offset_start_minutes=8 * 60,
            utc_offset_end_minutes=8 * 60,
            fold_start=0,
            fold_end=0,
            crosses_midnight=False,
            reason_codes=(),
        ),
        contracts.CalendarIntervalFact(
            event_id="calendar-event:2",
            source_id="calendar-source:2",
            start_utc=AS_OF + timedelta(hours=3),
            end_utc=AS_OF + timedelta(hours=4),
            all_day=False,
            local_start_minute=22 * 60,
            local_end_minute=23 * 60,
            utc_offset_start_minutes=8 * 60,
            utc_offset_end_minutes=8 * 60,
            fold_start=0,
            fold_end=0,
            crosses_midnight=False,
            reason_codes=(),
        ),
    )
    return contracts.CalendarKnowledgeDTO(
        state=contracts.CalendarKnowledgeState.TRUSTED_CURRENT,
        effective_timezone="Asia/Shanghai",
        day_start_utc=AS_OF - timedelta(hours=12),
        day_end_utc=AS_OF + timedelta(hours=12),
        sources=calendar_sources,
        intervals=intervals,
        reason_codes=(),
    )


def _two_member_collection_payloads() -> dict[
    contracts.HealthDaySourceKind,
    contracts.SourcePayloadValue,
]:
    program = contracts.ProgramInventoryDTO(
        program_id="program:1",
        program_type="recovery",
        problem_id="problem:1",
        started_on=LOCAL_DAY - timedelta(days=3),
        target_end_on=LOCAL_DAY + timedelta(days=4),
        availability=contracts.SourceAvailability.AVAILABLE,
        reason_codes=(),
    )
    protocols = (
        _protocols()[0],
        replace(
            _protocols()[0],
            protocol_id="protocol:2",
            mechanism="control-\u000f",
        ),
    )
    protocol_event = _protocol_event()
    problem = contracts.ProblemFollowUpDTO(
        problem_id="problem:1",
        risk_level=contracts.ProblemRiskLevel.MEDIUM,
        status=contracts.ProblemStatus.MONITORING,
        last_checkup=LOCAL_DAY - timedelta(days=7),
        cadence=contracts.ProtocolCadence.MONTHLY,
        next_due=LOCAL_DAY + timedelta(days=21),
        reason_codes=(),
    )
    medication = _medication_source()
    medication_execution = contracts.MedicationExecutionDTO(
        record_id="medication-execution:1",
        medication_id="medication:7",
        taken_date=LOCAL_DAY,
        raw_slot_present=True,
        normalized_slot=8 * 60,
        status=contracts.CanonicalLifecycle.COMPLETED,
        match_disposition=contracts.ExecutionMatchDisposition.EXACT_UNIQUE_SLOT,
        reason_codes=(),
    )
    supplement = contracts.SupplementSourceDTO(
        storage_namespace=contracts.StorageNamespace.SUPPLEMENT_DEFINITION,
        supplement_definition_id="supplement:1",
        timing_label=contracts.SupplementTimingLabel.MORNING,
        timing_precision_status=contracts.TimingPrecision.EXACT,
        sort_order=1,
        reason_codes=(),
    )
    supplement_execution = contracts.SupplementExecutionDTO(
        record_id="supplement-execution:1",
        supplement_definition_id="supplement:1",
        record_date=LOCAL_DAY,
        normalized_time=9 * 60,
        taken=True,
        reason_codes=(),
    )
    return {
        contracts.HealthDaySourceKind.PROGRAM_INVENTORY: (
            program,
            replace(program, program_id="program:2"),
        ),
        contracts.HealthDaySourceKind.PROTOCOLS: protocols,
        contracts.HealthDaySourceKind.PROTOCOL_EVENTS: (
            protocol_event,
            replace(protocol_event, event_id="event:2"),
        ),
        contracts.HealthDaySourceKind.PROBLEM_FOLLOWUPS: (
            problem,
            replace(problem, problem_id="problem:2"),
        ),
        contracts.HealthDaySourceKind.MEDICATIONS: (
            medication,
            replace(medication, medication_id="medication:8"),
        ),
        contracts.HealthDaySourceKind.MEDICATION_EXECUTIONS: (
            medication_execution,
            replace(medication_execution, record_id="medication-execution:2"),
        ),
        contracts.HealthDaySourceKind.SUPPLEMENTS: (
            supplement,
            replace(supplement, supplement_definition_id="supplement:2"),
        ),
        contracts.HealthDaySourceKind.SUPPLEMENT_EXECUTIONS: (
            supplement_execution,
            replace(
                supplement_execution,
                record_id="supplement-execution:2",
            ),
        ),
    }


def _complex_golden_manifest() -> shadow.ManifestSigningInput:
    maximum = 2**53 - 1
    reason_a = (
        contracts.ShadowReasonCode.DAILY_PLAN_ADVICE_GUARD_UNSUPPORTED,
        contracts.ShadowReasonCode.DAILY_PLAN_POST_GUARD_SELECTION_UNCOMPARABLE,
    )
    reason_b = (
        contracts.ShadowReasonCode.DAILY_PLAN_PREDICTION_ENRICHMENT_UNSUPPORTED,
        contracts.ShadowReasonCode.DAILY_PLAN_CYCLE_LABEL_POLICY_UNSUPPORTED,
    )
    daily = _daily_plan_subset()
    daily = replace(
        daily,
        body_weight=replace(
            daily.body_weight,
            competition=contracts.SourceCompetition.MULTI_SOURCE_COMPETITION,
            reason_codes=(
                contracts.ShadowReasonCode.DAILY_PLAN_WEIGHT_DEFAULT_USED,
                contracts.ShadowReasonCode.DAILY_PLAN_WEIGHT_SOURCE_POLICY_UNSUPPORTED,
            ),
        ),
        lab_anchor=replace(
            daily.lab_anchor,
            reason_codes=(
                contracts.ShadowReasonCode.DAILY_PLAN_LAB_FLAG_POLICY_UNSUPPORTED,
                contracts.ShadowReasonCode.DAILY_PLAN_INPUTS_INCOMPLETE,
            ),
        ),
        recovery=replace(
            daily.recovery,
            sleep=replace(
                daily.recovery.sleep,
                reason_codes=(
                    contracts.ShadowReasonCode.DAILY_PLAN_RECOVERY_MULTISOURCE_POLICY_UNSUPPORTED,
                    contracts.ShadowReasonCode.LEGACY_NONDETERMINISTIC_TIE,
                ),
            ),
            readiness=replace(
                daily.recovery.readiness,
                freshness=contracts.SourceFreshness.STALE,
                competition=contracts.SourceCompetition.SAME_SOURCE_DUPLICATE,
                reason_codes=(
                    contracts.ShadowReasonCode.DAILY_PLAN_COMPOSITE_TRAINING_GATE_UNSUPPORTED,
                    contracts.ShadowReasonCode.LEGACY_DATA_QUALITY_UNSUPPORTED,
                ),
            ),
            acute=replace(
                daily.recovery.acute,
                suspected_cold=True,
                should_rest=True,
                guardrail_code=contracts.AcuteGuardrailCode.COLD,
                severity_max=2,
                classification_status=contracts.ClassifierStatus.POLICY_MISMATCH,
                classifier_version="acute.v2",
                classifier_policy_digest="policy:acute:v2",
                reason_codes=(
                    contracts.ShadowReasonCode.DAILY_PLAN_ACUTE_CLASSIFIER_POLICY_MISMATCH,
                    contracts.ShadowReasonCode.DAILY_PLAN_ADVICE_GUARD_UNSUPPORTED,
                ),
            ),
            poor_recovery=True,
            reason_codes=reason_b,
        ),
        interventions=(
            replace(
                daily.interventions[0],
                action_key="action:max",
                priority=maximum,
                created_at=datetime(2026, 8, 15, 10, 1, 2, 123456, tzinfo=UTC),
                expires_at=datetime(2026, 8, 15, 18, 30, 0, 654321, tzinfo=UTC),
                evidence_level="strong",
                check_back_date=date(2026, 8, 16),
                classifier_version="intervention.v2",
                classifier_policy_digest="policy:intervention:v2",
                reason_codes=reason_a,
            ),
            replace(
                daily.interventions[1],
                action_key="action:min",
                priority=-maximum,
                created_at=datetime(2026, 8, 15, 10, 2, 3, 1, tzinfo=UTC),
                expires_at=None,
                classification_status=contracts.ClassifierStatus.INPUT_UNAVAILABLE,
                training_like=None,
                classifier_version="intervention.v3",
                classifier_policy_digest="policy:intervention:v3",
                availability=contracts.SourceAvailability.UNAVAILABLE,
                reason_codes=tuple(reversed(reason_a)),
            ),
        ),
        terminal_actions=(
            daily.terminal_actions[0],
            replace(
                daily.terminal_actions[0],
                record_id="terminal:2",
                action_key="action:skip",
                status=contracts.CanonicalLifecycle.SKIPPED,
                completion_provenance=contracts.CompletionProvenance.OTHER_TERMINAL,
            ),
        ),
        active_cycle=replace(
            daily.active_cycle,
            outcome_status="tracking",
            reason_codes=tuple(reversed(reason_b)),
        ),
        existing_dop=replace(
            daily.existing_dop,
            actions=(
                daily.existing_dop.actions[0],
                replace(daily.existing_dop.actions[1], when_code="morning"),
            ),
            reason_codes=reason_a,
        ),
        reason_codes=reason_a,
    )
    protocols = (
        replace(
            _protocols()[0],
            mechanism="mechanism-e\u0301",
            trigger_date=LOCAL_DAY,
            reason_codes=(
                contracts.ShadowReasonCode.PROTOCOL_PER_MEAL_OCCURRENCE_UNSUPPORTED,
                contracts.ShadowReasonCode.LEGACY_PROTOCOL_CORRECTION_UNSUPPORTED,
            ),
        ),
        contracts.ProtocolDTO(
            protocol_id="protocol:2",
            domain=contracts.HealthDomain.MEASUREMENT,
            mechanism="control-\u000f",
            cadence=contracts.ProtocolCadence.EVENT_TRIGGERED,
            time_window="20:00-21:00",
            completion_mode=contracts.ProtocolCompletionMode.HYBRID,
            can_default_complete=True,
            manual_track_allowed=False,
            program_id="program:2",
            source_model="health_metric",
            source_id="10",
            trigger_date=date(2026, 8, 16),
            availability=contracts.SourceAvailability.UNSUPPORTED,
            reason_codes=(
                contracts.ShadowReasonCode.UNSUPPORTED_CURRENT_COMPOSER,
                contracts.ShadowReasonCode.UNSUPPORTED_TIMING_PRECISION,
            ),
        ),
    )
    medication = replace(
        _medication_source(),
        domain_classifier_version="domain.v2",
        domain_classifier_policy_digest="policy:domain:v2",
        end_date=date(2026, 9, 15),
        reason_codes=(
            contracts.ShadowReasonCode.MEDICATION_SOURCE_OCCURRENCE_COUNT_MISMATCH,
            contracts.ShadowReasonCode.MEDICATION_DOMAIN_CLASSIFIER_POLICY_MISMATCH,
        ),
    )
    calendar = replace(
        _calendar_knowledge(),
        day_start_utc=datetime(2026, 8, 14, 16, 0, tzinfo=UTC),
        day_end_utc=datetime(2026, 8, 15, 16, 0, tzinfo=UTC),
        sources=(
            replace(
                _calendar_knowledge().sources[0],
                last_sync_at=datetime(2026, 8, 15, 11, 50, 0, 123456, tzinfo=UTC),
            ),
            replace(
                _calendar_knowledge().sources[1],
                sync_enabled=False,
                last_sync_at=datetime(2026, 8, 15, 11, 40, 0, 654321, tzinfo=UTC),
                sync_failed=True,
            ),
        ),
        intervals=(
            replace(
                _calendar_knowledge().intervals[0],
                start_utc=datetime(2026, 8, 15, 1, 0, 0, 123456, tzinfo=UTC),
                end_utc=datetime(2026, 8, 15, 2, 30, 0, 654321, tzinfo=UTC),
                local_start_minute=540,
                local_end_minute=630,
                reason_codes=(
                    contracts.ShadowReasonCode.CALENDAR_TIMEZONE_PROVENANCE_UNKNOWN,
                    contracts.ShadowReasonCode.CALENDAR_INTERVAL_INVALID,
                ),
            ),
            replace(
                _calendar_knowledge().intervals[1],
                start_utc=datetime(2026, 8, 15, 15, 0, 0, 1, tzinfo=UTC),
                end_utc=datetime(2026, 8, 15, 17, 0, 0, 999999, tzinfo=UTC),
                local_start_minute=1380,
                local_end_minute=60,
                fold_start=1,
                fold_end=1,
                crosses_midnight=True,
                reason_codes=(
                    contracts.ShadowReasonCode.CALENDAR_SYNC_STALE,
                    contracts.ShadowReasonCode.CALENDAR_SYNC_FAILED,
                ),
            ),
        ),
        reason_codes=(
            contracts.ShadowReasonCode.CALENDAR_SYNC_FAILED,
            contracts.ShadowReasonCode.CALENDAR_EVENT_CAP_EXCEEDED,
        ),
    )
    outer = (
        (
            contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
            contracts.HealthDaySourceRole.CANDIDATE,
            "revision:daily:v1",
            datetime(2026, 8, 15, 11, 51, 1, 123456, tzinfo=UTC),
            datetime(2026, 8, 15, 11, 59, 59, 654321, tzinfo=UTC),
            contracts.SourceFreshness.CURRENT,
            contracts.SourceAvailability.AVAILABLE,
            None,
            contracts.TombstoneState.PRESENT,
            daily,
        ),
        (
            contracts.HealthDaySourceKind.PROTOCOLS,
            contracts.HealthDaySourceRole.PROJECTION,
            "revision:protocols:v2",
            datetime(2026, 8, 15, 11, 52, 2, 234567, tzinfo=UTC),
            datetime(2026, 8, 15, 11, 59, 58, 543210, tzinfo=UTC),
            contracts.SourceFreshness.STALE,
            contracts.SourceAvailability.UNAVAILABLE,
            contracts.ShadowReasonCode.UNSUPPORTED_CURRENT_COMPOSER,
            contracts.TombstoneState.UNKNOWN,
            protocols,
        ),
        (
            contracts.HealthDaySourceKind.MEDICATIONS,
            contracts.HealthDaySourceRole.CANDIDATE,
            "revision:medications:v3",
            datetime(2026, 8, 15, 11, 53, 3, 345678, tzinfo=UTC),
            datetime(2026, 8, 15, 11, 59, 57, 432109, tzinfo=UTC),
            contracts.SourceFreshness.CURRENT,
            contracts.SourceAvailability.AVAILABLE,
            None,
            contracts.TombstoneState.ABSENT,
            (medication,),
        ),
        (
            contracts.HealthDaySourceKind.CALENDAR,
            contracts.HealthDaySourceRole.DIAGNOSTIC,
            "revision:calendar:v4",
            datetime(2026, 8, 15, 11, 54, 4, 456789, tzinfo=UTC),
            datetime(2026, 8, 15, 11, 59, 56, 321098, tzinfo=UTC),
            contracts.SourceFreshness.STALE,
            contracts.SourceAvailability.UNAVAILABLE,
            contracts.ShadowReasonCode.CALENDAR_SYNC_FAILED,
            contracts.TombstoneState.PRESENT,
            calendar,
        ),
    )
    sources = tuple(
        shadow.SourceSigningInput(
            source_kind=entry[0],
            source_role=entry[1],
            revision=entry[2],
            acquired_at=entry[3],
            cutoff=entry[4],
            freshness=entry[5],
            availability=entry[6],
            error_code=entry[7],
            tombstone_state=entry[8],
            value=entry[9],
        )
        for entry in outer
    )
    return shadow.ManifestSigningInput(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
        timezone="Asia/Shanghai",
        as_of=datetime(2026, 8, 15, 12, 0, 0, 123456, tzinfo=UTC),
        transaction=contracts.HealthDayTransaction(
            dialect=contracts.TransactionDialect.POSTGRESQL,
            isolation=contracts.TransactionIsolation.REPEATABLE_READ,
            read_only=True,
        ),
        sources=sources,
    )


def _complex_golden_expected_source_primitives() -> tuple[dict[str, object], ...]:
    maximum = 2**53 - 1
    reason_a = [
        "daily_plan_advice_guard_unsupported",
        "daily_plan_post_guard_selection_uncomparable",
    ]
    reason_b = [
        "daily_plan_prediction_enrichment_unsupported",
        "daily_plan_cycle_label_policy_unsupported",
    ]
    daily_value = {
        "body_weight": {
            "record_date": "2026-08-15",
            "weight_decimal": "70.25",
            "availability": "available",
            "competition": "multi_source_competition",
            "reason_codes": [
                "daily_plan_weight_default_used",
                "daily_plan_weight_source_policy_unsupported",
            ],
        },
        "lab_anchor": {
            "availability": "unsupported",
            "anchor_missing": True,
            "anchor_stale": False,
            "reason_codes": [
                "daily_plan_lab_flag_policy_unsupported",
                "daily_plan_inputs_incomplete",
            ],
        },
        "recovery": {
            "sleep": {
                "fact_kind": "sleep_score",
                "record_date": "2026-08-15",
                "value_decimal": "82.5",
                "freshness": "current",
                "competition": "unique_latest",
                "reason_codes": [
                    "daily_plan_recovery_multisource_policy_unsupported",
                    "legacy_nondeterministic_tie",
                ],
            },
            "readiness": {
                "fact_kind": "training_readiness",
                "record_date": "2026-08-15",
                "value_decimal": "71",
                "freshness": "stale",
                "competition": "same_source_duplicate",
                "reason_codes": [
                    "daily_plan_composite_training_gate_unsupported",
                    "legacy_data_quality_unsupported",
                ],
            },
            "acute": {
                "has_active_illness": False,
                "suspected_cold": True,
                "fever_reported": False,
                "should_rest": True,
                "guardrail_code": "cold",
                "severity_max": 2,
                "classification_status": "policy_mismatch",
                "classifier_version": "acute.v2",
                "classifier_policy_digest": "policy:acute:v2",
                "availability": "available",
                "reason_codes": [
                    "daily_plan_acute_classifier_policy_mismatch",
                    "daily_plan_advice_guard_unsupported",
                ],
            },
            "poor_recovery": True,
            "availability": "available",
            "reason_codes": reason_b,
        },
        "interventions": [
            {
                "action_key": "action:max",
                "priority": maximum,
                "created_at": "2026-08-15T10:01:02.123456Z",
                "expires_at": "2026-08-15T18:30:00.654321Z",
                "metric_key": "metric:sleep",
                "target_value_decimal": "8.25",
                "evidence_level": "strong",
                "check_back_date": "2026-08-16",
                "classification_status": "classified",
                "training_like": False,
                "classifier_version": "intervention.v2",
                "classifier_policy_digest": "policy:intervention:v2",
                "domain": "sleep",
                "availability": "available",
                "reason_codes": reason_a,
            },
            {
                "action_key": "action:min",
                "priority": -maximum,
                "created_at": "2026-08-15T10:02:03.000001Z",
                "expires_at": None,
                "metric_key": None,
                "target_value_decimal": None,
                "evidence_level": None,
                "check_back_date": None,
                "classification_status": "input_unavailable",
                "training_like": None,
                "classifier_version": "intervention.v3",
                "classifier_policy_digest": "policy:intervention:v3",
                "domain": "hydration",
                "availability": "unavailable",
                "reason_codes": list(reversed(reason_a)),
            },
        ],
        "terminal_actions": [
            {
                "record_id": "terminal:1",
                "action_key": "action:done",
                "status": "completed",
                "completion_provenance": "completed",
            },
            {
                "record_id": "terminal:2",
                "action_key": "action:skip",
                "status": "skipped",
                "completion_provenance": "other_terminal",
            },
        ],
        "active_cycle": {
            "cycle_id": "cycle:1",
            "cycle_type": "recovery",
            "start_date": "2026-08-13",
            "planned_end_date": "2026-08-20",
            "primary_metric_code": "sleep_score",
            "outcome_status": "tracking",
            "availability": "available",
            "reason_codes": list(reversed(reason_b)),
        },
        "existing_dop": {
            "plan_id": "dop:1",
            "status": "active",
            "actions": [
                {
                    "action_key": "dop:action:1",
                    "domain": "sleep",
                    "when_code": "evening",
                },
                {
                    "action_key": "dop:action:2",
                    "domain": "hydration",
                    "when_code": "morning",
                },
            ],
            "availability": "available",
            "reason_codes": reason_a,
        },
        "reason_codes": reason_a,
    }
    protocol_value = [
        {
            "protocol_id": "protocol:1",
            "domain": "checkup",
            "mechanism": "mechanism-e\u0301",
            "cadence": "weekly",
            "time_window": "09:00-10:00",
            "completion_mode": "manual",
            "can_default_complete": False,
            "manual_track_allowed": True,
            "program_id": "program:1",
            "source_model": "health_problem",
            "source_id": "9",
            "trigger_date": "2026-08-15",
            "availability": "available",
            "reason_codes": [
                "protocol_per_meal_occurrence_unsupported",
                "legacy_protocol_correction_unsupported",
            ],
        },
        {
            "protocol_id": "protocol:2",
            "domain": "measurement",
            "mechanism": "control-\u000f",
            "cadence": "event_triggered",
            "time_window": "20:00-21:00",
            "completion_mode": "hybrid",
            "can_default_complete": True,
            "manual_track_allowed": False,
            "program_id": "program:2",
            "source_model": "health_metric",
            "source_id": "10",
            "trigger_date": "2026-08-16",
            "availability": "unsupported",
            "reason_codes": [
                "unsupported_current_composer",
                "unsupported_timing_precision",
            ],
        },
    ]
    medication_value = [
        {
            "storage_namespace": "medication_row",
            "medication_id": "medication:7",
            "times_per_day": 2,
            "normalized_slots": [480, 1200],
            "domain": "medication",
            "domain_classification_provenance": "legacy_default_medication",
            "domain_classifier_version": "domain.v2",
            "domain_classifier_policy_digest": "policy:domain:v2",
            "timing_relation": "fixed",
            "meal_anchor": "none",
            "start_date": "2026-08-14",
            "end_date": "2026-09-15",
            "occurrence_availability": "available",
            "reason_codes": [
                "medication_source_occurrence_count_mismatch",
                "medication_domain_classifier_policy_mismatch",
            ],
        }
    ]
    calendar_value = {
        "state": "trusted_current",
        "effective_timezone": "Asia/Shanghai",
        "day_start_utc": "2026-08-14T16:00:00.000000Z",
        "day_end_utc": "2026-08-15T16:00:00.000000Z",
        "sources": [
            {
                "source_id": "calendar-source:1",
                "provider_code": "provider:one",
                "sync_enabled": True,
                "last_sync_at": "2026-08-15T11:50:00.123456Z",
                "sync_failed": False,
            },
            {
                "source_id": "calendar-source:2",
                "provider_code": "provider:two",
                "sync_enabled": False,
                "last_sync_at": "2026-08-15T11:40:00.654321Z",
                "sync_failed": True,
            },
        ],
        "intervals": [
            {
                "event_id": "calendar-event:1",
                "source_id": "calendar-source:1",
                "start_utc": "2026-08-15T01:00:00.123456Z",
                "end_utc": "2026-08-15T02:30:00.654321Z",
                "all_day": False,
                "local_start_minute": 540,
                "local_end_minute": 630,
                "utc_offset_start_minutes": 480,
                "utc_offset_end_minutes": 480,
                "fold_start": 0,
                "fold_end": 0,
                "crosses_midnight": False,
                "reason_codes": [
                    "calendar_timezone_provenance_unknown",
                    "calendar_interval_invalid",
                ],
            },
            {
                "event_id": "calendar-event:2",
                "source_id": "calendar-source:2",
                "start_utc": "2026-08-15T15:00:00.000001Z",
                "end_utc": "2026-08-15T17:00:00.999999Z",
                "all_day": False,
                "local_start_minute": 1380,
                "local_end_minute": 60,
                "utc_offset_start_minutes": 480,
                "utc_offset_end_minutes": 480,
                "fold_start": 1,
                "fold_end": 1,
                "crosses_midnight": True,
                "reason_codes": ["calendar_sync_stale", "calendar_sync_failed"],
            },
        ],
        "reason_codes": ["calendar_sync_failed", "calendar_event_cap_exceeded"],
    }

    def source(
        kind: str,
        role: str,
        revision: str,
        acquired_at: str,
        cutoff: str,
        freshness: str,
        availability: str,
        error_code: str | None,
        tombstone_state: str,
        value: object,
    ) -> dict[str, object]:
        return {
            "source_kind": kind,
            "source_role": role,
            "revision": revision,
            "acquired_at": acquired_at,
            "cutoff": cutoff,
            "freshness": freshness,
            "availability": availability,
            "error_code": error_code,
            "tombstone_state": tombstone_state,
            "value": value,
        }

    return (
        source(
            "daily_plan_subset",
            "candidate",
            "revision:daily:v1",
            "2026-08-15T11:51:01.123456Z",
            "2026-08-15T11:59:59.654321Z",
            "current",
            "available",
            None,
            "present",
            daily_value,
        ),
        source(
            "protocols",
            "projection",
            "revision:protocols:v2",
            "2026-08-15T11:52:02.234567Z",
            "2026-08-15T11:59:58.543210Z",
            "stale",
            "unavailable",
            "unsupported_current_composer",
            "unknown",
            protocol_value,
        ),
        source(
            "medications",
            "candidate",
            "revision:medications:v3",
            "2026-08-15T11:53:03.345678Z",
            "2026-08-15T11:59:57.432109Z",
            "current",
            "available",
            None,
            "absent",
            medication_value,
        ),
        source(
            "calendar",
            "diagnostic",
            "revision:calendar:v4",
            "2026-08-15T11:54:04.456789Z",
            "2026-08-15T11:59:56.321098Z",
            "stale",
            "unavailable",
            "calendar_sync_failed",
            "present",
            calendar_value,
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


def test_low_level_envelope_and_restricted_jcs_match_independent_golden():
    # This is the low-level envelope/JCS vector. The real typed public-path
    # source/manifest/item golden is locked separately below.
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


@pytest.mark.parametrize(
    ("nested_field", "invalid_value"),
    (("timing", 2), ("ordering_facts", -1)),
)
def test_bind_signed_shadow_item_key_revalidates_mutated_nested_item_before_key_read(
    nested_field: str,
    invalid_value: int,
):
    unsigned_item = _item(contracts.CanonicalLifecycle.PENDING)
    if nested_field == "timing":
        object.__setattr__(unsigned_item.timing, "fold", invalid_value)
    else:
        object.__setattr__(
            unsigned_item.ordering_facts,
            "source_ordinal",
            invalid_value,
        )
    provider = _CountingKeyProvider()

    with pytest.raises(
        shadow.ShadowSigningError,
        match="unsigned_shadow_item_invalid",
    ) as exc_info:
        shadow.bind_signed_shadow_item_key(
            unsigned_item,
            manifest_identity=shadow.ShadowManifestIdentity(
                schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
                owner_id="42",
                local_day=LOCAL_DAY,
            ),
            key_provider=provider,
        )
    assert provider.calls == 0
    assert exc_info.value.__suppress_context__


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


def test_typed_public_signatures_match_hardcoded_golden_in_fresh_process():
    script = textwrap.dedent(
        """
        from datetime import UTC, date, datetime, timedelta
        from app.services import health_day_shadow as shadow
        from app.services import health_day_shadow_contracts as contracts

        class Provider:
            def read_key(self):
                return "golden_v1", bytes(range(32))

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
        source_token = shadow.sign_shadow_source_payload(source, Provider())
        bundle = shadow.build_digest_bound_shadow_bundle(manifest, Provider())
        manifest_token = shadow.sign_shadow_manifest(bundle.manifest, Provider())
        manifest_identity = shadow.ShadowManifestIdentity(
            schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
            owner_id="42",
            local_day=date(2026, 8, 15),
        )
        item_identity = contracts.ShadowItemIdentity(
            storage_namespace=contracts.StorageNamespace.MEDICATION_ROW,
            source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
            source_id="7",
            local_day=date(2026, 8, 15),
            slot_local_minute=480,
            dose_ordinal=0,
            projection_role=contracts.ProjectionRole.SCHEDULE,
        )
        item_token = shadow.sign_shadow_item_identity(
            manifest_identity,
            item_identity,
            Provider(),
        )
        print(source_token)
        print(bundle.manifest.sources[0].payload_digest)
        print(manifest_token)
        print(bundle.shadow_manifest_digest)
        print(item_token)
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
    assert result.stdout.splitlines() == [
        "golden_v1.0ce4a8b4d3054fdb3c0d5e4384281b78c9582490f070b31dd88fcf420692fcad",
        "golden_v1.0ce4a8b4d3054fdb3c0d5e4384281b78c9582490f070b31dd88fcf420692fcad",
        "golden_v1.1f9ff16571684c14d20697763b2c050560aee7595cfddd88576ec05886158b46",
        "golden_v1.1f9ff16571684c14d20697763b2c050560aee7595cfddd88576ec05886158b46",
        "golden_v1.1a0e876119d45b5b4fe0469b59a84164b8d5e63e1befecf7320335fa07fc8f87",
    ]


def test_signers_revalidate_mutated_contract_invariants_before_using_key():
    transaction_manifest = _signing_manifest()
    object.__setattr__(transaction_manifest.transaction, "read_only", False)
    provider = _CountingKeyProvider()
    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_contract_revalidation_failed",
    ):
        shadow.build_digest_bound_shadow_bundle(transaction_manifest, provider)
    assert provider.calls == 0

    medication_slots = _medication_source()
    slots_source = _signing_source(
        source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
        value=(medication_slots,),
    )
    object.__setattr__(medication_slots, "normalized_slots", (None,))

    medication_namespace = _medication_source()
    namespace_source = _signing_source(
        source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
        value=(medication_namespace,),
    )
    object.__setattr__(
        medication_namespace,
        "storage_namespace",
        contracts.StorageNamespace.SUPPLEMENT_DEFINITION,
    )

    calendar = _calendar_knowledge()
    calendar_source = _signing_source(
        source_kind=contracts.HealthDaySourceKind.CALENDAR,
        value=calendar,
    )
    object.__setattr__(calendar.intervals[0], "fold_start", 2)

    protocol_event = _protocol_event()
    event_source = _signing_source(
        source_kind=contracts.HealthDaySourceKind.PROTOCOL_EVENTS,
        value=(protocol_event,),
    )
    object.__setattr__(
        protocol_event,
        "status",
        contracts.CanonicalLifecycle.UNKNOWN,
    )

    for malformed_source in (
        slots_source,
        namespace_source,
        calendar_source,
        event_source,
    ):
        provider = _CountingKeyProvider()
        with pytest.raises(
            shadow.ShadowSigningError,
            match="shadow_contract_revalidation_failed",
        ) as exc_info:
            shadow.sign_shadow_source_payload(malformed_source, provider)
        assert provider.calls == 0
        assert exc_info.value.__suppress_context__


def test_verifier_rejects_foreign_bundle_owned_payload_graph_before_using_key():
    first = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    second = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    object.__setattr__(first, "payloads", second.payloads)
    provider = _CountingKeyProvider()

    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_digest_verification_failed:bundle_ownership",
    ) as exc_info:
        shadow.verify_digest_bound_shadow_bundle(first, provider)
    assert provider.calls == 0
    assert exc_info.value.__suppress_context__


def test_verifier_rejects_forged_plain_object_ownership_capability_before_key():
    bundle = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    forged_ownership = object()
    object.__setattr__(bundle, "_bundle_ownership", forged_ownership)
    object.__setattr__(bundle.manifest, "_bundle_ownership", forged_ownership)
    for payload in bundle.payloads:
        object.__setattr__(payload, "_bundle_ownership", forged_ownership)
    provider = _CountingKeyProvider()

    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_digest_verification_failed:bundle_ownership",
    ) as exc_info:
        shadow.verify_digest_bound_shadow_bundle(bundle, provider)
    assert provider.calls == 0
    assert exc_info.value.__suppress_context__


@pytest.mark.parametrize(
    "mutation",
    ("manifest_owner", "transaction", "source_result", "payload_value"),
)
def test_verifier_rejects_all_unkeyed_structure_before_reading_key(mutation: str):
    bundle = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(),
        _CountingKeyProvider(),
    )
    if mutation == "manifest_owner":
        object.__setattr__(bundle.manifest, "owner_id", "")
    elif mutation == "transaction":
        object.__setattr__(bundle.manifest.transaction, "read_only", False)
    elif mutation == "source_result":
        object.__setattr__(bundle.manifest.sources[0], "revision", "bad revision")
    else:
        object.__setattr__(
            bundle.payloads[0].value,
            "workout_target_minutes",
            "private-invalid-health-value",
        )
    provider = _CountingKeyProvider()

    with pytest.raises(
        shadow.ShadowSigningError,
        match="shadow_digest_verification_failed:structure",
    ) as exc_info:
        shadow.verify_digest_bound_shadow_bundle(bundle, provider)
    assert provider.calls == 0
    assert "private-invalid-health-value" not in str(exc_info.value)
    assert exc_info.value.__suppress_context__


class _ExplodingTimezone(tzinfo):
    def utcoffset(self, _candidate):
        raise RuntimeError("private-tzinfo-payload-must-not-leak")

    def dst(self, _candidate):
        return None


def test_signing_boundary_time_and_owner_failures_are_controlled_and_redacted():
    exploding_source = _signing_source()
    object.__setattr__(
        exploding_source,
        "acquired_at",
        datetime(2026, 8, 15, 12, 0, tzinfo=_ExplodingTimezone()),
    )
    oversized_timezone = "private-timezone/" + ("x" * 5000)
    huge_owner = "9" * 5000
    min_utc = datetime.min.replace(tzinfo=UTC)

    def invalid_timezone_input() -> object:
        return replace(_signing_manifest(), timezone=oversized_timezone)

    def overflowing_local_day_input() -> object:
        return replace(
            _signing_manifest(),
            local_day=date.min,
            timezone="America/New_York",
            as_of=min_utc,
        )

    cases = (
        (
            lambda: shadow.sign_shadow_source_payload(
                exploding_source,
                _CountingKeyProvider(),
            ),
            "private-tzinfo-payload-must-not-leak",
        ),
        (invalid_timezone_input, oversized_timezone),
        (overflowing_local_day_input, "date value out of range"),
    )
    for operation, secret in cases:
        with pytest.raises(shadow.ShadowSigningError) as exc_info:
            operation()
        formatted = "".join(
            traceback.format_exception(
                type(exc_info.value),
                exc_info.value,
                exc_info.value.__traceback__,
            )
        )
        assert secret not in formatted
        assert exc_info.value.__suppress_context__

    huge_owner_manifest = _signing_manifest()
    object.__setattr__(huge_owner_manifest, "owner_id", huge_owner)
    provider = _CountingKeyProvider()
    with pytest.raises(shadow.ShadowSigningError) as owner_exc:
        shadow.build_digest_bound_shadow_bundle(huge_owner_manifest, provider)
    assert provider.calls == 0
    assert huge_owner not in str(owner_exc.value)
    assert owner_exc.value.__suppress_context__


def test_jcs_subset_rejects_cycles_and_excessive_depth_with_controlled_errors():
    cyclic: list[object] = []
    cyclic.append(cyclic)
    with pytest.raises(
        shadow.ShadowSigningError,
        match="jcs_cycle_detected",
    ) as cycle_exc:
        shadow.canonical_shadow_jcs_subset_bytes(cyclic)
    assert cycle_exc.value.__suppress_context__

    deeply_nested: object = None
    for _ in range(65):
        deeply_nested = [deeply_nested]
    with pytest.raises(
        shadow.ShadowSigningError,
        match="jcs_nesting_too_deep",
    ) as depth_exc:
        shadow.canonical_shadow_jcs_subset_bytes(deeply_nested)
    assert depth_exc.value.__suppress_context__


def test_timestamp_projection_zero_pads_year_one_without_platform_strftime():
    assert shadow._timestamp(
        datetime(1, 2, 3, 4, 5, 6, 7, tzinfo=UTC),
        "test.timestamp",
    ) == "0001-02-03T04:05:06.000007Z"
    timestamp_tree = ast.parse(inspect.getsource(shadow._timestamp))
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "strftime"
        for node in ast.walk(timestamp_tree)
    )


def test_all_composition_relevant_nested_tuple_orders_change_source_digest():
    daily_plan = _daily_plan_subset()
    daily_plan_reorders = (
        replace(
            daily_plan,
            interventions=tuple(reversed(daily_plan.interventions)),
        ),
        replace(
            daily_plan,
            existing_dop=replace(
                daily_plan.existing_dop,
                actions=tuple(reversed(daily_plan.existing_dop.actions)),
            ),
        ),
    )
    baseline_daily = shadow.sign_shadow_source_payload(
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
            value=daily_plan,
        ),
        _CountingKeyProvider(),
    )
    for reordered in daily_plan_reorders:
        assert (
            shadow.sign_shadow_source_payload(
                _signing_source(
                    source_kind=contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET,
                    value=reordered,
                ),
                _CountingKeyProvider(),
            )
            != baseline_daily
        )

    medication = _medication_source()
    baseline_medication = shadow.sign_shadow_source_payload(
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
            value=(medication,),
        ),
        _CountingKeyProvider(),
    )
    assert (
        shadow.sign_shadow_source_payload(
            _signing_source(
                source_kind=contracts.HealthDaySourceKind.MEDICATIONS,
                value=(
                    replace(
                        medication,
                        normalized_slots=tuple(reversed(medication.normalized_slots)),
                    ),
                ),
            ),
            _CountingKeyProvider(),
        )
        != baseline_medication
    )

    protocols = (
        _protocols()[0],
        replace(_protocols()[0], protocol_id="protocol:2"),
    )
    baseline_protocols = shadow.sign_shadow_source_payload(
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.PROTOCOLS,
            value=protocols,
        ),
        _CountingKeyProvider(),
    )
    assert (
        shadow.sign_shadow_source_payload(
            _signing_source(
                source_kind=contracts.HealthDaySourceKind.PROTOCOLS,
                value=tuple(reversed(protocols)),
            ),
            _CountingKeyProvider(),
        )
        != baseline_protocols
    )

    calendar = _calendar_knowledge()
    baseline_calendar = shadow.sign_shadow_source_payload(
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.CALENDAR,
            value=calendar,
        ),
        _CountingKeyProvider(),
    )
    for reordered_calendar in (
        replace(calendar, sources=tuple(reversed(calendar.sources))),
        replace(calendar, intervals=tuple(reversed(calendar.intervals))),
    ):
        assert (
            shadow.sign_shadow_source_payload(
                _signing_source(
                    source_kind=contracts.HealthDaySourceKind.CALENDAR,
                    value=reordered_calendar,
                ),
                _CountingKeyProvider(),
            )
            != baseline_calendar
        )

    two_reasons = replace(
        contracts.SafetySeamDTO(
            availability=contracts.SourceAvailability.UNKNOWN,
            disposition=contracts.SafetyDisposition.UNKNOWN,
            reason_codes=(
                contracts.ShadowReasonCode.SAFETY_SNAPSHOT_UNAVAILABLE,
                contracts.ShadowReasonCode.UNSUPPORTED_CURRENT_COMPOSER,
            ),
        ),
    )
    baseline_safety = shadow.sign_shadow_source_payload(
        _signing_source(
            source_kind=contracts.HealthDaySourceKind.SAFETY,
            value=two_reasons,
        ),
        _CountingKeyProvider(),
    )
    assert (
        shadow.sign_shadow_source_payload(
            _signing_source(
                source_kind=contracts.HealthDaySourceKind.SAFETY,
                value=replace(
                    two_reasons,
                    reason_codes=tuple(reversed(two_reasons.reason_codes)),
                ),
            ),
            _CountingKeyProvider(),
        )
        != baseline_safety
    )


def test_hardcoded_two_member_tuple_inventory_is_byte_order_sensitive():
    def source_digest(
        source_kind: contracts.HealthDaySourceKind,
        value: contracts.SourcePayloadValue,
    ) -> str:
        return shadow.sign_shadow_source_payload(
            _signing_source(source_kind=source_kind, value=value),
            _CountingKeyProvider(),
        )

    collection_payloads = _two_member_collection_payloads()
    assert set(collection_payloads) == {
        contracts.HealthDaySourceKind.PROGRAM_INVENTORY,
        contracts.HealthDaySourceKind.PROTOCOLS,
        contracts.HealthDaySourceKind.PROTOCOL_EVENTS,
        contracts.HealthDaySourceKind.PROBLEM_FOLLOWUPS,
        contracts.HealthDaySourceKind.MEDICATIONS,
        contracts.HealthDaySourceKind.MEDICATION_EXECUTIONS,
        contracts.HealthDaySourceKind.SUPPLEMENTS,
        contracts.HealthDaySourceKind.SUPPLEMENT_EXECUTIONS,
    }
    for source_kind, value in collection_payloads.items():
        assert type(value) is tuple and len(value) == 2
        assert source_digest(source_kind, value) != source_digest(
            source_kind,
            (value[1], value[0]),
        )

    daily_plan = _daily_plan_subset()
    terminal_actions = (
        daily_plan.terminal_actions[0],
        replace(
            daily_plan.terminal_actions[0],
            record_id="terminal:2",
            action_key="action:skipped",
            status=contracts.CanonicalLifecycle.SKIPPED,
            completion_provenance=contracts.CompletionProvenance.OTHER_TERMINAL,
        ),
    )
    daily_plan = replace(
        daily_plan,
        terminal_actions=terminal_actions,
        reason_codes=(
            contracts.ShadowReasonCode.DAILY_PLAN_ADVICE_GUARD_UNSUPPORTED,
            contracts.ShadowReasonCode.DAILY_PLAN_INPUTS_INCOMPLETE,
        ),
    )
    daily_kind = contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET
    daily_baseline = source_digest(daily_kind, daily_plan)
    daily_reorders = (
        replace(
            daily_plan,
            interventions=(
                daily_plan.interventions[1],
                daily_plan.interventions[0],
            ),
        ),
        replace(
            daily_plan,
            terminal_actions=(terminal_actions[1], terminal_actions[0]),
        ),
        replace(
            daily_plan,
            existing_dop=replace(
                daily_plan.existing_dop,
                actions=(
                    daily_plan.existing_dop.actions[1],
                    daily_plan.existing_dop.actions[0],
                ),
            ),
        ),
        replace(
            daily_plan,
            reason_codes=(daily_plan.reason_codes[1], daily_plan.reason_codes[0]),
        ),
    )
    for reordered in daily_reorders:
        assert source_digest(daily_kind, reordered) != daily_baseline

    medication = _medication_source()
    medication_kind = contracts.HealthDaySourceKind.MEDICATIONS
    assert source_digest(medication_kind, (medication,)) != source_digest(
        medication_kind,
        (
            replace(
                medication,
                normalized_slots=(
                    medication.normalized_slots[1],
                    medication.normalized_slots[0],
                ),
            ),
        ),
    )

    calendar = replace(
        _calendar_knowledge(),
        reason_codes=(
            contracts.ShadowReasonCode.CALENDAR_SYNC_STALE,
            contracts.ShadowReasonCode.CALENDAR_SYNC_FAILED,
        ),
    )
    calendar_kind = contracts.HealthDaySourceKind.CALENDAR
    calendar_baseline = source_digest(calendar_kind, calendar)
    calendar_reorders = (
        replace(calendar, sources=(calendar.sources[1], calendar.sources[0])),
        replace(calendar, intervals=(calendar.intervals[1], calendar.intervals[0])),
        replace(
            calendar,
            reason_codes=(calendar.reason_codes[1], calendar.reason_codes[0]),
        ),
    )
    for reordered in calendar_reorders:
        assert source_digest(calendar_kind, reordered) != calendar_baseline


def test_every_explicit_contract_projector_reads_every_exact_dto_field():
    projector_contracts = {
        "_project_transaction": ("transaction", contracts.HealthDayTransaction),
        "_project_source_result": ("source", contracts.HealthDaySourceResult),
        "_project_manifest": ("manifest", contracts.HealthDayShadowManifest),
        "_project_profile_schedule": ("profile", contracts.ProfileScheduleDTO),
        "_project_body_weight": ("body_weight", contracts.BodyWeightSubsetDTO),
        "_project_lab_anchor": ("lab_anchor", contracts.LabAnchorSubsetDTO),
        "_project_recovery_wearable": (
            "wearable",
            contracts.RecoveryWearableFactDTO,
        ),
        "_project_acute": ("acute", contracts.AcuteSubsetDTO),
        "_project_recovery": ("recovery", contracts.RecoverySubsetDTO),
        "_project_intervention": (
            "intervention",
            contracts.InterventionSubsetDTO,
        ),
        "_project_terminal_action": (
            "terminal",
            contracts.TerminalActionSubsetDTO,
        ),
        "_project_active_cycle": ("cycle", contracts.ActiveCycleSubsetDTO),
        "_project_existing_dop_action": (
            "action",
            contracts.ExistingDOPActionFact,
        ),
        "_project_existing_dop": ("dop", contracts.ExistingDOPDiagnosticDTO),
        "_project_daily_plan_subset": (
            "daily_plan",
            contracts.DailyPlanSubsetFactsDTO,
        ),
        "_project_program_inventory": ("program", contracts.ProgramInventoryDTO),
        "_project_protocol": ("protocol", contracts.ProtocolDTO),
        "_project_protocol_event": ("event", contracts.ProtocolEventDTO),
        "_project_problem_followup": ("problem", contracts.ProblemFollowUpDTO),
        "_project_medication_source": (
            "medication",
            contracts.MedicationSourceDTO,
        ),
        "_project_medication_execution": (
            "execution",
            contracts.MedicationExecutionDTO,
        ),
        "_project_supplement_source": (
            "supplement",
            contracts.SupplementSourceDTO,
        ),
        "_project_supplement_execution": (
            "execution",
            contracts.SupplementExecutionDTO,
        ),
        "_project_calendar_source": ("source", contracts.CalendarSourceFact),
        "_project_calendar_interval": (
            "interval",
            contracts.CalendarIntervalFact,
        ),
        "_project_calendar_knowledge": (
            "calendar",
            contracts.CalendarKnowledgeDTO,
        ),
        "_project_safety_seam": ("safety", contracts.SafetySeamDTO),
    }
    module = ast.parse(
        Path(shadow.__file__).read_text(encoding="utf-8"),
        filename=shadow.__file__,
    )
    functions = {
        node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
    }

    assert set(projector_contracts) <= set(functions)
    for function_name, (root_name, contract_type) in projector_contracts.items():
        projector = functions[function_name]
        actual_reads = {
            node.attr
            for node in ast.walk(projector)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == root_name
        }
        expected_reads = {
            contract_field.name for contract_field in fields(contract_type)
        }
        assert actual_reads == expected_reads, function_name


def test_every_projected_key_is_bound_to_its_exact_same_name_dto_attribute():
    # This inventory is deliberately hand-written rather than derived from the
    # dataclasses or production projector registry. A dead read or field swap
    # must not satisfy the return-value binding check.
    same_root_fields = {
        "_project_transaction": (
            "transaction",
            "dialect isolation read_only",
        ),
        "_project_source_signing_input": (
            "source_input",
            "source_kind source_role revision acquired_at cutoff freshness "
            "availability error_code tombstone_state value",
        ),
        "_project_source_result": (
            "source",
            "source_kind source_role revision payload_digest acquired_at cutoff "
            "freshness availability error_code tombstone_state",
        ),
        "_project_manifest": (
            "manifest",
            "schema_version owner_id local_day timezone as_of transaction sources",
        ),
        "_project_profile_schedule": (
            "profile",
            "timezone detected_timezone manual_timezone usual_sleep_time "
            "usual_wake_time work_start_time work_end_time workout_pref_window "
            "workout_target_minutes",
        ),
        "_project_body_weight": (
            "body_weight",
            "record_date weight_decimal availability competition reason_codes",
        ),
        "_project_lab_anchor": (
            "lab_anchor",
            "availability anchor_missing anchor_stale reason_codes",
        ),
        "_project_recovery_wearable": (
            "wearable",
            "fact_kind record_date value_decimal freshness competition reason_codes",
        ),
        "_project_acute": (
            "acute",
            "has_active_illness suspected_cold fever_reported should_rest "
            "guardrail_code severity_max classification_status classifier_version "
            "classifier_policy_digest availability reason_codes",
        ),
        "_project_recovery": (
            "recovery",
            "sleep readiness acute poor_recovery availability reason_codes",
        ),
        "_project_intervention": (
            "intervention",
            "action_key priority created_at expires_at metric_key "
            "target_value_decimal evidence_level check_back_date "
            "classification_status training_like classifier_version "
            "classifier_policy_digest domain availability reason_codes",
        ),
        "_project_terminal_action": (
            "terminal",
            "record_id action_key status completion_provenance",
        ),
        "_project_active_cycle": (
            "cycle",
            "cycle_id cycle_type start_date planned_end_date primary_metric_code "
            "outcome_status availability reason_codes",
        ),
        "_project_existing_dop_action": (
            "action",
            "action_key domain when_code",
        ),
        "_project_existing_dop": (
            "dop",
            "plan_id status actions availability reason_codes",
        ),
        "_project_daily_plan_subset": (
            "daily_plan",
            "body_weight lab_anchor recovery interventions terminal_actions "
            "active_cycle existing_dop reason_codes",
        ),
        "_project_program_inventory": (
            "program",
            "program_id program_type problem_id started_on target_end_on "
            "availability reason_codes",
        ),
        "_project_protocol": (
            "protocol",
            "protocol_id domain mechanism cadence time_window completion_mode "
            "can_default_complete manual_track_allowed program_id source_model "
            "source_id trigger_date availability reason_codes",
        ),
        "_project_protocol_event": (
            "event",
            "event_id protocol_id event_date status track snoozed_until reason_codes",
        ),
        "_project_problem_followup": (
            "problem",
            "problem_id risk_level status last_checkup cadence next_due reason_codes",
        ),
        "_project_medication_source": (
            "medication",
            "storage_namespace medication_id times_per_day normalized_slots domain "
            "domain_classification_provenance domain_classifier_version "
            "domain_classifier_policy_digest timing_relation meal_anchor start_date "
            "end_date occurrence_availability reason_codes",
        ),
        "_project_medication_execution": (
            "execution",
            "record_id medication_id taken_date raw_slot_present normalized_slot "
            "status match_disposition reason_codes",
        ),
        "_project_supplement_source": (
            "supplement",
            "storage_namespace supplement_definition_id timing_label "
            "timing_precision_status sort_order reason_codes",
        ),
        "_project_supplement_execution": (
            "execution",
            "record_id supplement_definition_id record_date normalized_time taken "
            "reason_codes",
        ),
        "_project_calendar_source": (
            "source",
            "source_id provider_code sync_enabled last_sync_at sync_failed",
        ),
        "_project_calendar_interval": (
            "interval",
            "event_id source_id start_utc end_utc all_day local_start_minute "
            "local_end_minute utc_offset_start_minutes utc_offset_end_minutes "
            "fold_start fold_end crosses_midnight reason_codes",
        ),
        "_project_calendar_knowledge": (
            "calendar",
            "state effective_timezone day_start_utc day_end_utc sources intervals "
            "reason_codes",
        ),
        "_project_safety_seam": (
            "safety",
            "availability disposition reason_codes",
        ),
    }
    expected_bindings = {
        function_name: {
            field_name: (root_name, field_name)
            for field_name in field_names.split()
        }
        for function_name, (root_name, field_names) in same_root_fields.items()
    }
    expected_bindings["_project_item_identity"] = {
        "schema_version": ("manifest_identity", "schema_version"),
        "owner_id": ("manifest_identity", "owner_id"),
        "local_day": ("manifest_identity", "local_day"),
        "storage_namespace": ("item_identity", "storage_namespace"),
        "source_kind": ("item_identity", "source_kind"),
        "source_id": ("item_identity", "source_id"),
        "slot_local_minute": ("item_identity", "slot_local_minute"),
        "dose_ordinal": ("item_identity", "dose_ordinal"),
        "projection_role": ("item_identity", "projection_role"),
    }

    module = ast.parse(
        Path(shadow.__file__).read_text(encoding="utf-8"),
        filename=shadow.__file__,
    )
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
    }
    for function_name, bindings in expected_bindings.items():
        projector = functions[function_name]
        return_node = next(
            node
            for node in projector.body
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict)
        )
        returned = {
            key.value: value
            for key, value in zip(return_node.value.keys, return_node.value.values)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        assert set(returned) == set(bindings), function_name

        aliases: dict[str, set[tuple[str, str]]] = {}
        for node in projector.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                expression = node.value
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                expression = node.value
            else:
                continue
            if isinstance(target, ast.Name) and expression is not None:
                aliases[target.id] = {
                    (attribute.value.id, attribute.attr)
                    for attribute in ast.walk(expression)
                    if isinstance(attribute, ast.Attribute)
                    and isinstance(attribute.value, ast.Name)
                }

        for projected_key, expected_binding in bindings.items():
            expression = returned[projected_key]
            actual_bindings = {
                (attribute.value.id, attribute.attr)
                for attribute in ast.walk(expression)
                if isinstance(attribute, ast.Attribute)
                and isinstance(attribute.value, ast.Name)
            }
            for name in ast.walk(expression):
                if isinstance(name, ast.Name):
                    actual_bindings.update(aliases.get(name.id, set()))
            assert expected_binding in actual_bindings, (
                function_name,
                projected_key,
                actual_bindings,
            )


def test_every_explicit_contract_projector_revalidates_its_exact_frozen_dto():
    expected_revalidation_roots = {
        "_project_transaction": {"transaction"},
        "_project_source_result": {"source"},
        "_project_manifest": {"manifest"},
        "_project_item_identity": {"item_identity"},
        "_project_profile_schedule": {"profile"},
        "_project_body_weight": {"body_weight"},
        "_project_lab_anchor": {"lab_anchor"},
        "_project_recovery_wearable": {"wearable"},
        "_project_acute": {"acute"},
        "_project_recovery": {"recovery"},
        "_project_intervention": {"intervention"},
        "_project_terminal_action": {"terminal"},
        "_project_active_cycle": {"cycle"},
        "_project_existing_dop_action": {"action"},
        "_project_existing_dop": {"dop"},
        "_project_daily_plan_subset": {"daily_plan"},
        "_project_program_inventory": {"program"},
        "_project_protocol": {"protocol"},
        "_project_protocol_event": {"event"},
        "_project_problem_followup": {"problem"},
        "_project_medication_source": {"medication"},
        "_project_medication_execution": {"execution"},
        "_project_supplement_source": {"supplement"},
        "_project_supplement_execution": {"execution"},
        "_project_calendar_source": {"source"},
        "_project_calendar_interval": {"interval"},
        "_project_calendar_knowledge": {"calendar"},
        "_project_safety_seam": {"safety"},
    }
    module = ast.parse(
        Path(shadow.__file__).read_text(encoding="utf-8"),
        filename=shadow.__file__,
    )
    functions = {
        node.name: node for node in module.body if isinstance(node, ast.FunctionDef)
    }

    for function_name, expected_roots in expected_revalidation_roots.items():
        actual_roots = {
            call.args[0].id
            for call in ast.walk(functions[function_name])
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_revalidate_frozen_contract"
            and call.args
            and isinstance(call.args[0], ast.Name)
        }
        assert actual_roots == expected_roots, function_name


def test_projection_code_preserves_every_composition_tuple_without_sorting():
    expected_nested_tuple_fields = {
        "BodyWeightSubsetDTO.reason_codes",
        "LabAnchorSubsetDTO.reason_codes",
        "RecoveryWearableFactDTO.reason_codes",
        "AcuteSubsetDTO.reason_codes",
        "RecoverySubsetDTO.reason_codes",
        "InterventionSubsetDTO.reason_codes",
        "ActiveCycleSubsetDTO.reason_codes",
        "ExistingDOPDiagnosticDTO.actions",
        "ExistingDOPDiagnosticDTO.reason_codes",
        "DailyPlanSubsetFactsDTO.interventions",
        "DailyPlanSubsetFactsDTO.terminal_actions",
        "DailyPlanSubsetFactsDTO.reason_codes",
        "ProgramInventoryDTO.reason_codes",
        "ProtocolDTO.reason_codes",
        "ProtocolEventDTO.reason_codes",
        "ProblemFollowUpDTO.reason_codes",
        "MedicationSourceDTO.normalized_slots",
        "MedicationSourceDTO.reason_codes",
        "MedicationExecutionDTO.reason_codes",
        "SupplementSourceDTO.reason_codes",
        "SupplementExecutionDTO.reason_codes",
        "CalendarIntervalFact.reason_codes",
        "CalendarKnowledgeDTO.sources",
        "CalendarKnowledgeDTO.intervals",
        "CalendarKnowledgeDTO.reason_codes",
        "SafetySeamDTO.reason_codes",
    }
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
    actual_nested_tuple_fields = {
        f"{contract_type.__name__}.{contract_field.name}"
        for contract_type in source_dto_types
        for contract_field in fields(contract_type)
        if str(get_type_hints(contract_type)[contract_field.name]).startswith("tuple[")
    }
    assert actual_nested_tuple_fields == expected_nested_tuple_fields

    module = ast.parse(
        Path(shadow.__file__).read_text(encoding="utf-8"),
        filename=shadow.__file__,
    )
    source_projection_functions = (
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
        and (node.name.startswith("_project_") or node.name == "_reason_codes")
    )
    for projector in source_projection_functions:
        forbidden_order_operations = [
            call
            for call in ast.walk(projector)
            if (
                isinstance(call, ast.Call)
                and (
                    isinstance(call.func, ast.Name)
                    and call.func.id in {"sorted", "reversed", "set"}
                    or isinstance(call.func, ast.Attribute)
                    and call.func.attr == "sort"
                )
            )
            or (
                isinstance(call, ast.Subscript)
                and isinstance(call.slice, ast.Slice)
                and isinstance(call.slice.step, ast.UnaryOp)
                and isinstance(call.slice.step.op, ast.USub)
            )
        ]
        if projector.name != "_project_manifest":
            assert forbidden_order_operations == [], projector.name

    collection_projectors = {
        "_project_program_inventory_source",
        "_project_protocols_source",
        "_project_protocol_events_source",
        "_project_problem_followups_source",
        "_project_medications_source",
        "_project_medication_executions_source",
        "_project_supplements_source",
        "_project_supplement_executions_source",
    }
    functions = {
        node.name: node
        for node in module.body
        if isinstance(node, ast.FunctionDef)
    }
    for function_name in collection_projectors:
        projector = functions[function_name]
        direct_iterations = [
            comprehension.iter
            for comprehension in ast.walk(projector)
            if isinstance(comprehension, ast.comprehension)
        ]
        assert len(direct_iterations) == 1, function_name
        assert isinstance(direct_iterations[0], ast.Name), function_name
        assert direct_iterations[0].id == "value", function_name


def test_typed_public_signing_paths_match_independent_full_protocol_golden():
    source_input = _signing_source()
    provider = _CountingKeyProvider(key_id="golden_v1")
    source_token = shadow.sign_shadow_source_payload(source_input, provider)
    assert provider.calls == 1

    bundle_provider = _CountingKeyProvider(key_id="golden_v1")
    bundle = shadow.build_digest_bound_shadow_bundle(
        _signing_manifest(sources=(source_input,)),
        bundle_provider,
    )
    assert bundle_provider.calls == 1

    manifest_provider = _CountingKeyProvider(key_id="golden_v1")
    manifest_token = shadow.sign_shadow_manifest(bundle.manifest, manifest_provider)
    assert manifest_provider.calls == 1

    manifest_identity = shadow.ShadowManifestIdentity(
        schema_version=contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        owner_id="42",
        local_day=LOCAL_DAY,
    )
    item_provider = _CountingKeyProvider(key_id="golden_v1")
    item_token = shadow.sign_shadow_item_identity(
        manifest_identity,
        _identity(),
        item_provider,
    )
    assert item_provider.calls == 1

    expected_source_canonical = (
        b'{"key_id":"golden_v1","payload":{"acquired_at":"2026-08-15T11:55:00.000000Z",'
        b'"availability":"available","cutoff":"2026-08-15T12:00:00.000000Z",'
        b'"error_code":null,"freshness":"current","revision":"revision:v1",'
        b'"source_kind":"profile_schedule","source_role":"candidate",'
        b'"tombstone_state":"unknown","value":{"detected_timezone":null,'
        b'"manual_timezone":null,"timezone":"Asia/Shanghai","usual_sleep_time":null,'
        b'"usual_wake_time":null,"work_end_time":null,"work_start_time":null,'
        b'"workout_pref_window":null,"workout_target_minutes":null}},'
        b'"purpose":"source-payload","schema_version":"health_day_shadow.v1"}'
    )
    expected_source_frame_hex = (
        "000000146865616c74682d6461792d736861646f772d763100000254"
        "7b226b65795f6964223a22676f6c64656e5f7631222c227061796c6f6164223a"
        "7b2261637175697265645f6174223a22323032362d30382d31355431313a35353a"
        "30302e3030303030305a222c22617661696c6162696c697479223a22617661696c"
        "61626c65222c226375746f6666223a22323032362d30382d31355431323a30303a"
        "30302e3030303030305a222c226572726f725f636f6465223a6e756c6c2c2266"
        "726573686e657373223a2263757272656e74222c227265766973696f6e223a2272"
        "65766973696f6e3a7631222c22736f757263655f6b696e64223a2270726f66696c"
        "655f7363686564756c65222c22736f757263655f726f6c65223a2263616e646964"
        "617465222c22746f6d6273746f6e655f7374617465223a22756e6b6e6f776e222c"
        "2276616c7565223a7b2264657465637465645f74696d657a6f6e65223a6e756c6c"
        "2c226d616e75616c5f74696d657a6f6e65223a6e756c6c2c2274696d657a6f6e"
        "65223a22417369612f5368616e67686169222c22757375616c5f736c6565705f74"
        "696d65223a6e756c6c2c22757375616c5f77616b655f74696d65223a6e756c6c"
        "2c22776f726b5f656e645f74696d65223a6e756c6c2c22776f726b5f7374617274"
        "5f74696d65223a6e756c6c2c22776f726b6f75745f707265665f77696e646f7722"
        "3a6e756c6c2c22776f726b6f75745f7461726765745f6d696e75746573223a6e75"
        "6c6c7d7d2c22707572706f7365223a22736f757263652d7061796c6f6164222c22"
        "736368656d615f76657273696f6e223a226865616c74685f6461795f736861646f"
        "772e7631227d"
    )
    expected_manifest_canonical = (
        b'{"key_id":"golden_v1","payload":{"as_of":"2026-08-15T12:00:00.000000Z",'
        b'"local_day":"2026-08-15","owner_id":"42","schema_version":"health_day_shadow.v1",'
        b'"sources":[{"acquired_at":"2026-08-15T11:55:00.000000Z",'
        b'"availability":"available","cutoff":"2026-08-15T12:00:00.000000Z",'
        b'"error_code":null,"freshness":"current","payload_digest":"golden_v1.'
        b'0ce4a8b4d3054fdb3c0d5e4384281b78c9582490f070b31dd88fcf420692fcad",'
        b'"revision":"revision:v1","source_kind":"profile_schedule",'
        b'"source_role":"candidate","tombstone_state":"unknown"}],'
        b'"timezone":"Asia/Shanghai","transaction":{"dialect":"postgresql",'
        b'"isolation":"repeatable_read","read_only":true}},'
        b'"purpose":"manifest-digest","schema_version":"health_day_shadow.v1"}'
    )
    expected_manifest_frame_hex = (
        "000000146865616c74682d6461792d736861646f772d7631000002c0"
        "7b226b65795f6964223a22676f6c64656e5f7631222c227061796c6f6164223a7b"
        "2261735f6f66223a22323032362d30382d31355431323a30303a30302e3030303030"
        "305a222c226c6f63616c5f646179223a22323032362d30382d3135222c226f776e65"
        "725f6964223a223432222c22736368656d615f76657273696f6e223a226865616c74"
        "685f6461795f736861646f772e7631222c22736f7572636573223a5b7b2261637175"
        "697265645f6174223a22323032362d30382d31355431313a35353a30302e3030303030"
        "305a222c22617661696c6162696c697479223a22617661696c61626c65222c22637574"
        "6f6666223a22323032362d30382d31355431323a30303a30302e3030303030305a222c"
        "226572726f725f636f6465223a6e756c6c2c2266726573686e657373223a2263757272"
        "656e74222c227061796c6f61645f646967657374223a22676f6c64656e5f76312e3063"
        "653461386234643330353466646233633064356534333834323831623738633935383234"
        "3930663037306233316464383866636634323036393266636164222c227265766973696f"
        "6e223a227265766973696f6e3a7631222c22736f757263655f6b696e64223a2270726f66"
        "696c655f7363686564756c65222c22736f757263655f726f6c65223a2263616e64696461"
        "7465222c22746f6d6273746f6e655f7374617465223a22756e6b6e6f776e227d5d2c22"
        "74696d657a6f6e65223a22417369612f5368616e67686169222c227472616e7361637469"
        "6f6e223a7b226469616c656374223a22706f737467726573716c222c2269736f6c617469"
        "6f6e223a2272657065617461626c655f72656164222c22726561645f6f6e6c79223a7472"
        "75657d7d2c22707572706f7365223a226d616e69666573742d646967657374222c227363"
        "68656d615f76657273696f6e223a226865616c74685f6461795f736861646f772e763122"
        "7d"
    )
    expected_item_canonical = (
        b'{"key_id":"golden_v1","payload":{"dose_ordinal":0,'
        b'"local_day":"2026-08-15","owner_id":"42","projection_role":"schedule",'
        b'"schema_version":"health_day_shadow.v1","slot_local_minute":480,'
        b'"source_id":"7","source_kind":"medications",'
        b'"storage_namespace":"medication_row"},"purpose":"item-key",'
        b'"schema_version":"health_day_shadow.v1"}'
    )
    expected_item_frame_hex = (
        "000000146865616c74682d6461792d736861646f772d763100000147"
        "7b226b65795f6964223a22676f6c64656e5f7631222c227061796c6f6164223a7b"
        "22646f73655f6f7264696e616c223a302c226c6f63616c5f646179223a2232303236"
        "2d30382d3135222c226f776e65725f6964223a223432222c2270726f6a656374696f"
        "6e5f726f6c65223a227363686564756c65222c22736368656d615f76657273696f6e"
        "223a226865616c74685f6461795f736861646f772e7631222c22736c6f745f6c6f63"
        "616c5f6d696e757465223a3438302c22736f757263655f6964223a2237222c22736f"
        "757263655f6b696e64223a226d656469636174696f6e73222c2273746f726167655f"
        "6e616d657370616365223a226d656469636174696f6e5f726f77227d2c2270757270"
        "6f7365223a226974656d2d6b6579222c22736368656d615f76657273696f6e223a22"
        "6865616c74685f6461795f736861646f772e7631227d"
    )

    source_canonical = shadow._canonical_signing_envelope_bytes(
        shadow._project_source_signing_input(source_input),
        purpose="source-payload",
        key_id="golden_v1",
    )
    manifest_canonical = shadow._canonical_signing_envelope_bytes(
        shadow._project_manifest(bundle.manifest),
        purpose="manifest-digest",
        key_id="golden_v1",
    )
    item_canonical = shadow._canonical_signing_envelope_bytes(
        shadow._project_item_identity(manifest_identity, _identity()),
        purpose="item-key",
        key_id="golden_v1",
    )

    assert source_canonical == expected_source_canonical
    assert shadow._frame_shadow_envelope(source_canonical).hex() == (
        expected_source_frame_hex
    )
    assert manifest_canonical == expected_manifest_canonical
    assert shadow._frame_shadow_envelope(manifest_canonical).hex() == (
        expected_manifest_frame_hex
    )
    assert item_canonical == expected_item_canonical
    assert shadow._frame_shadow_envelope(item_canonical).hex() == (
        expected_item_frame_hex
    )
    assert shadow._derive_purpose_key(bytes(range(32)), "source-payload").hex() == (
        "1f02b1ebc70527189c16b9fcc0a253e5d65befa1727e3c2af7c50771784cdc99"
    )
    assert shadow._derive_purpose_key(bytes(range(32)), "manifest-digest").hex() == (
        "ba0572e3ddc4fd0d5b3cc46754914f8108c0fe9cbea7389821269086f73ff5da"
    )
    assert shadow._derive_purpose_key(bytes(range(32)), "item-key").hex() == (
        "424a2ef27bebe3a501090e5417296eb24319f40410a36425bba317a5f99b3882"
    )
    assert source_token == (
        "golden_v1.0ce4a8b4d3054fdb3c0d5e4384281b78c9582490f070b31dd88fcf420692fcad"
    )
    assert bundle.manifest.sources[0].payload_digest == source_token
    assert manifest_token == (
        "golden_v1.1f9ff16571684c14d20697763b2c050560aee7595cfddd88576ec05886158b46"
    )
    assert bundle.shadow_manifest_digest == manifest_token
    assert item_token == (
        "golden_v1.1a0e876119d45b5b4fe0469b59a84164b8d5e63e1befecf7320335fa07fc8f87"
    )


def test_complex_multisource_typed_bundle_matches_independent_layered_golden():
    expected_source_tokens = (
        "golden_v1.aa2397df955e0150b13ba45a93c5f63e39e506813b8a5e31fa64465e7e0ef83b",
        "golden_v1.7005d5bcccca828d1fcf5aab952eb9803c159681c94b5c0d58521d6941ffd00c",
        "golden_v1.c6c1e44e7c2ebfff194bc59f49a2cee5440aebf4a604480f88f3b6b2891478cd",
        "golden_v1.cb13e3c897f183f204595f078e38e472d67c197d4908ae282b892c1d4cd4f0a9",
    )
    expected_manifest_token = (
        "golden_v1.162b37d7d7539ba6da490e5872e82398429fa1ef8df0cff5bc1faae81a5aac42"
    )
    expected_envelope_lengths = (3928, 1269, 920, 1733)
    expected_envelope_hashes = (
        "d6da8f35a96edf7fd8b3b85ef21cdb602f7ae246076e2031bf478441a68f1900",
        "c83d7e533690a5490fe416182295df4748a8b2521903b687e7a20cf121348db9",
        "fe4f4286988e9ac87f93e8eab7a5254e691f7bcdefff0a3dabc76f82570a4f17",
        "f1a9116a77cea5c6e64046ef4dc8f23cf25776957bb76e3c1f9733954747a0b4",
    )
    expected_frame_hashes = (
        "f4d2a0720f178f6a829cf86b609bfa648582eaf16671175d828514ddd37a56a9",
        "80dcd2cb77785724e230fbb626be2bb00227145d620f8c7cd39461656c04164c",
        "3d8326e1ab655fdae8d2f7c54598cdcc9e1330d165954139eec442c1d6eb6de1",
        "8e2b93877492ffa4033e5151fd87f3b2c37edce0cfd4d599920550caf9647527",
    )
    domain = b"health-day-shadow-v1"

    def independent_canonical(payload: object, purpose: str) -> bytes:
        return json.dumps(
            {
                "key_id": "golden_v1",
                "payload": payload,
                "purpose": purpose,
                "schema_version": "health_day_shadow.v1",
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def independent_frame(canonical: bytes) -> bytes:
        return (
            len(domain).to_bytes(4, "big")
            + domain
            + len(canonical).to_bytes(4, "big")
            + canonical
        )

    manifest_input = _complex_golden_manifest()
    expected_sources = _complex_golden_expected_source_primitives()
    assert len(manifest_input.sources) == len(expected_sources) == 4
    direct_source_tokens = []
    for index, (source_input, expected_source) in enumerate(
        zip(manifest_input.sources, expected_sources)
    ):
        expected_canonical = independent_canonical(
            expected_source,
            "source-payload",
        )
        expected_frame = independent_frame(expected_canonical)
        actual_canonical = shadow._canonical_signing_envelope_bytes(
            shadow._project_source_signing_input(source_input),
            purpose="source-payload",
            key_id="golden_v1",
        )
        assert actual_canonical == expected_canonical
        assert len(actual_canonical) == expected_envelope_lengths[index]
        assert hashlib.sha256(actual_canonical).hexdigest() == (
            expected_envelope_hashes[index]
        )
        assert shadow._frame_shadow_envelope(actual_canonical) == expected_frame
        assert hashlib.sha256(expected_frame).hexdigest() == expected_frame_hashes[index]
        direct_source_tokens.append(
            shadow.sign_shadow_source_payload(
                source_input,
                _CountingKeyProvider(key_id="golden_v1"),
            )
        )
    assert tuple(direct_source_tokens) == expected_source_tokens

    bundle = shadow.build_digest_bound_shadow_bundle(
        manifest_input,
        _CountingKeyProvider(key_id="golden_v1"),
    )
    assert tuple(source.payload_digest for source in bundle.manifest.sources) == (
        expected_source_tokens
    )
    expected_manifest_sources = []
    for source, token in zip(expected_sources, expected_source_tokens):
        expected_manifest_sources.append(
            {
                key: value
                for key, value in source.items()
                if key != "value"
            }
            | {"payload_digest": token}
        )
    expected_manifest = {
        "schema_version": "health_day_shadow.v1",
        "owner_id": "42",
        "local_day": "2026-08-15",
        "timezone": "Asia/Shanghai",
        "as_of": "2026-08-15T12:00:00.123456Z",
        "transaction": {
            "dialect": "postgresql",
            "isolation": "repeatable_read",
            "read_only": True,
        },
        "sources": expected_manifest_sources,
    }
    expected_manifest_canonical = independent_canonical(
        expected_manifest,
        "manifest-digest",
    )
    expected_manifest_frame = independent_frame(expected_manifest_canonical)
    actual_manifest_canonical = shadow._canonical_signing_envelope_bytes(
        shadow._project_manifest(bundle.manifest),
        purpose="manifest-digest",
        key_id="golden_v1",
    )
    assert actual_manifest_canonical == expected_manifest_canonical
    assert len(actual_manifest_canonical) == 1841
    assert hashlib.sha256(actual_manifest_canonical).hexdigest() == (
        "36dd86cfa1739137ae0aeb3e5d8201892cd098bc9c59d3e5fe2886844fac01b8"
    )
    assert shadow._frame_shadow_envelope(actual_manifest_canonical) == (
        expected_manifest_frame
    )
    assert hashlib.sha256(expected_manifest_frame).hexdigest() == (
        "4d058631e74fba1c20689e1a0b7021bb4cb4e4d5e9ec33fbda40e2ff5da542d7"
    )
    assert shadow.sign_shadow_manifest(
        bundle.manifest,
        _CountingKeyProvider(key_id="golden_v1"),
    ) == expected_manifest_token
    assert bundle.shadow_manifest_digest == expected_manifest_token

    script = textwrap.dedent(
        """
        import json
        from health_day_shadow_tests.test_health_day_composer import (
            _CountingKeyProvider,
            _complex_golden_manifest,
        )
        from app.services import health_day_shadow as shadow

        manifest_input = _complex_golden_manifest()
        direct = [
            shadow.sign_shadow_source_payload(
                source,
                _CountingKeyProvider(key_id="golden_v1"),
            )
            for source in manifest_input.sources
        ]
        bundle = shadow.build_digest_bound_shadow_bundle(
            manifest_input,
            _CountingKeyProvider(key_id="golden_v1"),
        )
        print(json.dumps(
            direct
            + [source.payload_digest for source in bundle.manifest.sources]
            + [
                shadow.sign_shadow_manifest(
                    bundle.manifest,
                    _CountingKeyProvider(key_id="golden_v1"),
                ),
                bundle.shadow_manifest_digest,
            ]
        ))
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
    assert json.loads(result.stdout) == [
        *expected_source_tokens,
        *expected_source_tokens,
        expected_manifest_token,
        expected_manifest_token,
    ]
