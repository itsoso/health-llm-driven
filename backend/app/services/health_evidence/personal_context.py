"""Query-specific Personal Context Compiler.

The compiler is deliberately a pure transformation over a frozen HealthTwin plus
an explicit safety-profile supplement. It never opens a database session.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from typing import Any

from app.services.personal_evidence_matrix import build_personal_evidence_matrix
from app.twin.schema import HealthTwin

from .contracts import (
    ContextBudget,
    ContextGap,
    EvidenceConflict,
    GapState,
    HealthIntentEnvelope,
    PersonalEvidenceItem,
    PersonalEvidencePacket,
    RiskLevel,
    SafetyProfileContext,
    SafetyRiskSignal,
)

logger = logging.getLogger(__name__)

_LOW_BACK_MANDATORY_CATEGORIES = (
    "symptom",
    "active_problem",
    "medication",
    "allergy",
    "chronic_condition",
)
_FAILED_PARTITION_ALIASES = {
    "symptom": ("acute", "acute_health"),
    "active_problem": ("acute", "acute_health", "problem_red_lines"),
    "medication": ("medication",),
    "allergy": ("safety_profile",),
    "chronic_condition": ("chronic", "chronic_conditions", "collectors"),
}
_SAFETY_CRITICAL_PARTITIONS = frozenset(
    {
        "acute",
        "acute_health",
        "problem_red_lines",
        "medication",
        "safety_profile",
        "chronic",
        "chronic_conditions",
        "collectors",
    }
)


def compile_personal_context(
    *,
    twin: HealthTwin,
    intent: HealthIntentEnvelope,
    safety_profile: SafetyProfileContext | None = None,
    max_evidence_items: int = 12,
) -> PersonalEvidencePacket:
    """Compile the smallest deterministic personal packet for ``intent``."""

    mandatory = (
        _LOW_BACK_MANDATORY_CATEGORIES
        if intent.domain == "low_back_pain"
        else ()
    )
    if max_evidence_items < len(mandatory):
        raise ValueError(
            "max_evidence_items cannot be smaller than mandatory context categories"
        )

    profile = safety_profile or SafetyProfileContext()
    failed_partitions = tuple(sorted(set(twin.meta.failed_partitions)))
    generated_at = _aware(twin.meta.generated_at)
    evidence_specs: list[dict[str, Any]] = []
    gaps: list[ContextGap] = []
    safety_signals = _compile_safety_signals(
        twin,
        intent=intent,
        profile=profile,
    )

    if intent.domain == "low_back_pain":
        _append_low_back_safety_core(
            evidence_specs,
            gaps,
            twin=twin,
            intent=intent,
            profile=profile,
            failed_partitions=failed_partitions,
            generated_at=generated_at,
        )

    optional_specs = _matrix_candidates(
        twin,
        intent=intent,
        generated_at=generated_at,
    )
    optional_specs.extend(_conflict_evidence_candidates(twin, intent=intent))
    optional_specs.sort(
        key=lambda spec: (
            str(spec["category"]),
            str(spec.get("source_ref") or ""),
            str(spec["kind"]),
        )
    )

    remaining = max_evidence_items - len(evidence_specs)
    selected_specs = evidence_specs + optional_specs[:remaining]
    evidence = _materialize_evidence(selected_specs)
    conflicts = _compile_conflicts(twin, intent=intent)

    return PersonalEvidencePacket(
        generated_at=generated_at,
        intent=intent,
        mandatory_categories=mandatory,
        evidence=tuple(evidence),
        gaps=tuple(sorted(gaps, key=lambda gap: (gap.category, gap.gap_id))),
        failed_partitions=failed_partitions,
        conflicts=tuple(conflicts),
        safety_signals=safety_signals,
        budget=ContextBudget(
            max_items=max_evidence_items,
            selected_items=len(evidence),
            truncated=len(optional_specs) > remaining,
        ),
    )


def _compile_safety_signals(
    twin: HealthTwin,
    *,
    intent: HealthIntentEnvelope,
    profile: SafetyProfileContext,
) -> tuple[SafetyRiskSignal, ...]:
    """Run deterministic safety rules on query + frozen Twin without mutating it."""

    selected = list(profile.risk_signals)
    if intent.domain != "low_back_pain":
        return _deduplicate_safety_signals(selected)
    if _SAFETY_CRITICAL_PARTITIONS.intersection(twin.meta.failed_partitions):
        selected.append(
            SafetyRiskSignal(
                signal_id="twin:safety_context_incomplete",
                risk_level=RiskLevel.HIGH,
                category="safety",
                detail=(
                    "本轮安全相关个人上下文未完整构建，不能把空值解释为正常或不存在。"
                ),
                source_kind="health_twin",
                source_ref="twin.meta.failed_partitions",
            )
        )

    # Guardian rules inspect Twin symptom state. Overlay the current utterance onto
    # a structural copy so a current low-back query can combine with a recent
    # bladder/neurologic symptom without mutating the frozen turn snapshot.
    symptom_texts = list(
        dict.fromkeys(
            text.strip()
            for text in (intent.query, *twin.acute.symptom_texts_all)
            if isinstance(text, str) and text.strip()
        )
    )
    guard_twin = twin.model_copy(
        update={
            "acute": twin.acute.model_copy(
                update={"symptom_texts_all": symptom_texts}
            )
        }
    )

    try:
        from app.agents.safety_guardian import engine

        alerts, failed_rule_count = engine.evaluate_rules_with_status(guard_twin)
    except Exception as exc:  # noqa: BLE001 - safety gate must fail closed
        logger.warning(
            "[health_evidence] guardian evaluation failed error_type=%s",
            type(exc).__name__,
        )
        alerts = []
        failed_rule_count = 1

    counts: dict[str, int] = {}
    for alert in sorted(
        alerts,
        key=lambda item: (
            str(item.rule_id),
            -int(item.severity),
            str(item.category),
        ),
    ):
        severity_value = int(alert.severity)
        if severity_value < 3:
            continue
        risk_level = (
            RiskLevel.EMERGENCY
            if severity_value >= 4
            else RiskLevel.HIGH
        )
        base_id = f"guardian:{alert.rule_id}"
        counts[base_id] = counts.get(base_id, 0) + 1
        signal_id = (
            base_id
            if counts[base_id] == 1
            else f"{base_id}:{counts[base_id]}"
        )
        detail_parts = [
            str(alert.title or "").strip(),
            str(alert.message or "").strip(),
            str(alert.action or "").strip(),
        ]
        selected.append(
            SafetyRiskSignal(
                signal_id=signal_id,
                risk_level=risk_level,
                category=str(alert.category or "safety"),
                detail="；".join(part for part in detail_parts if part),
                source_kind="safety_guardian",
                source_ref=str(alert.rule_id),
                discriminator_id=_guardian_discriminator_id(
                    str(alert.rule_id)
                ),
            )
        )

    if failed_rule_count:
        selected.append(
            SafetyRiskSignal(
                signal_id="guardian:safety.evaluation_incomplete",
                risk_level=RiskLevel.HIGH,
                category="safety",
                detail=(
                    "本轮自动安全规则未能完整评估，不能把未命中解释为安全。"
                ),
                source_kind="safety_guardian",
                source_ref="safety.evaluation_incomplete",
            )
        )
    return _deduplicate_safety_signals(selected)


def _guardian_discriminator_id(rule_id: str) -> str | None:
    return {
        "symptoms.cauda_equina_warning": "low_back.cauda_equina",
        "symptoms.red_flag_persistent_warning": (
            "low_back.systemic_red_flag"
        ),
    }.get(rule_id)


def _deduplicate_safety_signals(
    signals: list[SafetyRiskSignal],
) -> tuple[SafetyRiskSignal, ...]:
    rank = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.EMERGENCY: 3,
    }
    by_id: dict[str, SafetyRiskSignal] = {}
    for signal in signals:
        current = by_id.get(signal.signal_id)
        if current is None or rank[signal.risk_level] > rank[current.risk_level]:
            by_id[signal.signal_id] = signal
    return tuple(by_id[key] for key in sorted(by_id))


def _append_low_back_safety_core(
    evidence_specs: list[dict[str, Any]],
    gaps: list[ContextGap],
    *,
    twin: HealthTwin,
    intent: HealthIntentEnvelope,
    profile: SafetyProfileContext,
    failed_partitions: tuple[str, ...],
    generated_at: datetime,
) -> None:
    symptom_values = tuple(
        dict.fromkeys(
            value.strip()
            for value in (intent.query, *twin.acute.symptom_texts_all)
            if isinstance(value, str) and value.strip()
        )
    )
    _evidence_or_gap(
        evidence_specs,
        gaps,
        category="symptom",
        kind="current_and_recent",
        label="当前与近72小时症状",
        value=symptom_values,
        source_kind="current_utterance_and_twin",
        source_ref="twin.acute.symptom_texts_all",
        freshness="current",
        reliability="high",
        failed_partitions=failed_partitions,
    )

    problem_values = tuple(
        item.model_dump(mode="json")
        for item in twin.acute.problem_red_lines
    )
    _evidence_or_gap(
        evidence_specs,
        gaps,
        category="active_problem",
        kind="red_line",
        label="当前问题红线",
        value=problem_values,
        source_kind="health_twin",
        source_ref="twin.acute.problem_red_lines",
        freshness="current",
        reliability="high",
        failed_partitions=failed_partitions,
    )

    medication_observed_at = twin.freshness.medication
    _evidence_or_gap(
        evidence_specs,
        gaps,
        category="medication",
        kind="active_list",
        label="当前用药",
        value=tuple(twin.medication.active_meds),
        source_kind="health_twin",
        source_ref="twin.medication.active_meds",
        observed_at=medication_observed_at,
        freshness=_normalize_freshness(medication_observed_at, generated_at),
        reliability="high",
        failed_partitions=failed_partitions,
    )

    _evidence_or_gap(
        evidence_specs,
        gaps,
        category="allergy",
        kind="safety_profile",
        label="过敏与禁忌",
        value=profile.allergies,
        source_kind="safety_profile",
        source_ref="profile.allergies",
        freshness="long_term",
        reliability="high",
        failed_partitions=failed_partitions,
    )

    _evidence_or_gap(
        evidence_specs,
        gaps,
        category="chronic_condition",
        kind="active_list",
        label="慢性病与重要病史",
        value=tuple(twin.chronic.active_conditions),
        source_kind="health_twin",
        source_ref="twin.chronic.active_conditions",
        freshness="long_term",
        reliability="high",
        failed_partitions=failed_partitions,
    )


def _evidence_or_gap(
    evidence_specs: list[dict[str, Any]],
    gaps: list[ContextGap],
    *,
    category: str,
    kind: str,
    label: str,
    value: Any,
    source_kind: str,
    source_ref: str,
    freshness: str,
    reliability: str,
    failed_partitions: tuple[str, ...],
    observed_at: Any = None,
) -> None:
    failed_partition = _failed_partition_for(category, failed_partitions)
    if failed_partition is not None:
        gaps.append(
            ContextGap(
                gap_id=f"personal-gap:{category}",
                category=category,
                state=GapState.FAILED,
                detail="相关健康数据分区本轮不可用，不能据此推断不存在或正常。",
                failed_partition=failed_partition,
            )
        )
        return
    if not value:
        gaps.append(
            ContextGap(
                gap_id=f"personal-gap:{category}",
                category=category,
                state=GapState.ABSENT,
                detail="当前快照没有足够信息，需要补充或确认。",
            )
        )
        return
    evidence_specs.append(
        {
            "category": category,
            "kind": kind,
            "label": label,
            "value": value,
            "source_kind": source_kind,
            "source_ref": source_ref,
            "observed_at": _to_iso(observed_at),
            "freshness": freshness,
            "reliability": reliability,
        }
    )


def _matrix_candidates(
    twin: HealthTwin,
    *,
    intent: HealthIntentEnvelope,
    generated_at: datetime,
) -> list[dict[str, Any]]:
    if intent.domain != "low_back_pain":
        return []
    matrix = build_personal_evidence_matrix(twin)
    candidates: list[dict[str, Any]] = []
    observed_at = twin.freshness.sleep or twin.freshness.garmin
    for signal in matrix.get("signals", []):
        if signal.get("signal_type") != "wearable":
            continue
        candidates.append(
            {
                "category": "wearable",
                "kind": "measurement",
                "label": str(signal.get("label") or "可穿戴指标"),
                "value": signal.get("value"),
                "unit": signal.get("unit"),
                "source_kind": str(signal.get("source") or "health_twin"),
                "source_ref": str(signal.get("signal_id") or ""),
                "observed_at": _to_iso(observed_at),
                "freshness": _normalize_freshness(
                    observed_at or signal.get("freshness"),
                    generated_at,
                ),
                "reliability": str(signal.get("reliability") or "unknown"),
            }
        )
    return candidates


def _conflict_evidence_candidates(
    twin: HealthTwin,
    *,
    intent: HealthIntentEnvelope,
) -> list[dict[str, Any]]:
    if intent.domain != "low_back_pain":
        return []
    return [
        {
            "category": "wearable",
            "kind": "source_conflict",
            "label": divergence.label,
            "value": {
                "deviation_pct": divergence.deviation_pct,
                "trusted_source": divergence.trusted_source,
                "outlier_source": divergence.outlier_source,
            },
            "source_kind": "health_twin",
            "source_ref": f"twin.physiological.divergent_metrics.{divergence.metric}",
            "freshness": "current",
            "reliability": "low",
        }
        for divergence in twin.physiological.divergent_metrics
    ]


def _compile_conflicts(
    twin: HealthTwin,
    *,
    intent: HealthIntentEnvelope,
) -> list[EvidenceConflict]:
    if intent.domain != "low_back_pain":
        return []
    return [
        EvidenceConflict(
            conflict_id=f"personal-conflict:wearable:{index}",
            category="wearable",
            trusted_source=item.trusted_source,
            outlier_source=item.outlier_source,
            detail=item.hint,
        )
        for index, item in enumerate(
            sorted(
                twin.physiological.divergent_metrics,
                key=lambda divergence: (
                    divergence.metric,
                    divergence.trusted_source,
                    divergence.outlier_source,
                ),
            ),
            start=1,
        )
    ]


def _materialize_evidence(
    specs: list[dict[str, Any]],
) -> list[PersonalEvidenceItem]:
    counts: dict[str, int] = {}
    items: list[PersonalEvidenceItem] = []
    for spec in specs:
        category = str(spec["category"])
        counts[category] = counts.get(category, 0) + 1
        items.append(
            PersonalEvidenceItem(
                evidence_id=f"personal:{category}:{counts[category]}",
                category=category,
                kind=str(spec["kind"]),
                label=str(spec["label"]),
                value=spec.get("value"),
                unit=spec.get("unit"),
                observed_at=spec.get("observed_at"),
                freshness=str(spec.get("freshness") or "unknown"),
                reliability=str(spec.get("reliability") or "unknown"),
                source_kind=str(spec["source_kind"]),
                source_ref=spec.get("source_ref"),
            )
        )
    return items


def _failed_partition_for(
    category: str,
    failed_partitions: tuple[str, ...],
) -> str | None:
    aliases = _FAILED_PARTITION_ALIASES.get(category, ())
    return next(
        (partition for partition in failed_partitions if partition in aliases),
        None,
    )


def _normalize_freshness(value: Any, generated_at: datetime) -> str:
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower()
    if normalized in {"today", "current"}:
        return "current"
    if normalized in {"fresh", "recent"}:
        return "recent"
    if normalized in {"stale", "long_term", "unknown"}:
        return normalized
    try:
        parsed = datetime.fromisoformat(normalized.replace("z", "+00:00"))
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
        except ValueError:
            return "unknown"
        age_days = (generated_at.date() - parsed_date).days
    else:
        parsed = _aware(parsed)
        age_days = (generated_at.date() - parsed.date()).days
    if age_days <= 1:
        return "current"
    if age_days <= 30:
        return "recent"
    return "stale"


def _to_iso(value: Any) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
