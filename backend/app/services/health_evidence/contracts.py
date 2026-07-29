"""Immutable contracts shared by the health-evidence runtime."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EMERGENCY = "emergency"


class GapState(str, Enum):
    ABSENT = "absent"
    FAILED = "failed"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PublicHealthIntent(_FrozenContract):
    """Privacy-safe clinical semantics shared by every client."""

    version: str = "health-intent.v1"
    intent_id: str
    intent: str
    domain: str
    risk_level: RiskLevel
    mandatory_discriminator_ids: tuple[str, ...] = ()
    requires_personal_context: bool = False
    requires_authority: bool = False


class HealthIntentEnvelope(_FrozenContract):
    """Private, turn-scoped health intent.

    ``query`` intentionally exists only on the private envelope. Client identity is
    not part of the contract, so it cannot alter clinical semantics.
    """

    version: str = "health-intent.v1"
    query: str
    intent_id: str
    intent: str
    domain: str
    risk_level: RiskLevel
    mandatory_discriminator_ids: tuple[str, ...] = ()
    requires_personal_context: bool = False
    requires_authority: bool = False

    def to_public(self) -> PublicHealthIntent:
        return PublicHealthIntent(
            version=self.version,
            intent_id=self.intent_id,
            intent=self.intent,
            domain=self.domain,
            risk_level=self.risk_level,
            mandatory_discriminator_ids=self.mandatory_discriminator_ids,
            requires_personal_context=self.requires_personal_context,
            requires_authority=self.requires_authority,
        )


class SafetyRiskSignal(_FrozenContract):
    """Private deterministic safety result selected from the frozen turn state."""

    signal_id: str
    risk_level: RiskLevel
    category: str
    detail: str
    source_kind: str
    source_ref: str | None = None
    discriminator_id: str | None = None


class SafetyProfileContext(_FrozenContract):
    """Small explicit supplement for safety fields not yet represented in Twin."""

    allergies: tuple[str, ...] = ()
    population: Literal["adults_16_plus", "under_16"] | None = None
    risk_signals: tuple[SafetyRiskSignal, ...] = ()


class PersonalEvidenceItem(_FrozenContract):
    """One private, model-visible personal fact selected for this turn."""

    evidence_id: str
    category: str
    kind: str
    label: str
    value: Any
    unit: str | None = None
    observed_at: str | None = None
    freshness: str = "unknown"
    reliability: str = "unknown"
    source_kind: str
    source_ref: str | None = None


class ContextGap(_FrozenContract):
    gap_id: str
    category: str
    state: GapState
    detail: str
    failed_partition: str | None = None


class PublicContextGap(_FrozenContract):
    gap_id: str
    category: str
    state: GapState


class EvidenceConflict(_FrozenContract):
    conflict_id: str
    category: str
    trusted_source: str
    outlier_source: str
    detail: str


class PublicEvidenceConflict(_FrozenContract):
    conflict_id: str
    category: str


class ContextBudget(_FrozenContract):
    max_items: int
    selected_items: int
    truncated: bool


class PublicPersonalEvidenceManifest(_FrozenContract):
    """Privacy-safe trace. It intentionally contains no personal values."""

    version: str = "personal-context.v1"
    intent_id: str
    risk_level: RiskLevel
    context_categories_used: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    safety_signal_refs: tuple[str, ...] = ()
    gaps: tuple[PublicContextGap, ...] = ()
    conflicts: tuple[PublicEvidenceConflict, ...] = ()
    truncated: bool = False


class PersonalEvidencePacket(_FrozenContract):
    """Private, turn-scoped packet supplied to synthesis only."""

    version: str = "personal-context.v1"
    generated_at: datetime
    intent: HealthIntentEnvelope
    mandatory_categories: tuple[str, ...] = ()
    evidence: tuple[PersonalEvidenceItem, ...] = ()
    gaps: tuple[ContextGap, ...] = ()
    failed_partitions: tuple[str, ...] = ()
    conflicts: tuple[EvidenceConflict, ...] = ()
    safety_signals: tuple[SafetyRiskSignal, ...] = ()
    budget: ContextBudget

    @model_validator(mode="after")
    def _mandatory_evidence_or_gap(self) -> "PersonalEvidencePacket":
        covered = {item.category for item in self.evidence}
        covered.update(gap.category for gap in self.gaps)
        missing = set(self.mandatory_categories) - covered
        if missing:
            raise ValueError(
                "mandatory context must be represented as evidence or gap: "
                + ", ".join(sorted(missing))
            )
        return self

    def to_public_manifest(self) -> PublicPersonalEvidenceManifest:
        categories = tuple(dict.fromkeys(item.category for item in self.evidence))
        return PublicPersonalEvidenceManifest(
            intent_id=self.intent.intent_id,
            risk_level=self.intent.risk_level,
            context_categories_used=categories,
            evidence_refs=tuple(item.evidence_id for item in self.evidence),
            safety_signal_refs=tuple(
                signal.signal_id for signal in self.safety_signals
            ),
            gaps=tuple(
                PublicContextGap(
                    gap_id=gap.gap_id,
                    category=gap.category,
                    state=gap.state,
                )
                for gap in self.gaps
            ),
            conflicts=tuple(
                PublicEvidenceConflict(
                    conflict_id=conflict.conflict_id,
                    category=conflict.category,
                )
                for conflict in self.conflicts
            ),
            truncated=self.budget.truncated,
        )

    def render_private_prompt(self) -> str:
        """Render one bounded personal section without changing packet semantics."""

        lines = [
            "## 本轮个人健康证据（私有，仅用于当前回答）",
            f"intent={self.intent.intent_id}; risk={self.intent.risk_level.value}",
        ]
        if self.evidence:
            lines.append("evidence:")
            for item in self.evidence:
                value = json.dumps(
                    item.value,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                )
                if len(value) > 320:
                    value = value[:317].rstrip() + "..."
                observed = f"; observed_at={item.observed_at}" if item.observed_at else ""
                unit = f" {item.unit}" if item.unit else ""
                lines.append(
                    f"- [{item.evidence_id}] {item.category}/{item.kind}: "
                    f"{item.label}={value}{unit}; freshness={item.freshness}{observed}"
                )
        if self.safety_signals:
            lines.append("deterministic_safety_signals:")
            for signal in self.safety_signals:
                detail = signal.detail.strip()
                if len(detail) > 320:
                    detail = detail[:317].rstrip() + "..."
                discriminator = (
                    f"; discriminator={signal.discriminator_id}"
                    if signal.discriminator_id
                    else ""
                )
                lines.append(
                    f"- [{signal.signal_id}] risk={signal.risk_level.value}; "
                    f"category={signal.category}{discriminator}; {detail}"
                )
        if self.gaps:
            lines.append("gaps:")
            for gap in self.gaps:
                lines.append(
                    f"- [{gap.gap_id}] {gap.category}: {gap.state.value}; {gap.detail}"
                )
        if self.conflicts:
            lines.append("conflicts:")
            for conflict in self.conflicts:
                lines.append(
                    f"- [{conflict.conflict_id}] {conflict.category}: {conflict.detail}"
                )
        lines.append(
            "边界：只使用上列 evidence；gap/failed 不得推断为正常或不存在。"
        )
        return "\n".join(lines)
