"""Public entry points for the backend-owned health-evidence runtime."""

from .contracts import (
    ContextBudget,
    ContextGap,
    EvidenceConflict,
    GapState,
    HealthIntentEnvelope,
    PersonalEvidenceItem,
    PersonalEvidencePacket,
    PublicHealthIntent,
    PublicPersonalEvidenceManifest,
    RiskLevel,
    SafetyProfileContext,
)
from .intent import (
    LOW_BACK_MANDATORY_DISCRIMINATOR_IDS,
    classify_health_intent,
)
from .personal_context import compile_personal_context
from .runtime import (
    HealthEvidenceTurn,
    build_health_evidence_turn,
    compile_health_evidence_turn,
)
from .verifier import HealthAnswerVerification, verify_health_answer

__all__ = [
    "ContextBudget",
    "ContextGap",
    "EvidenceConflict",
    "GapState",
    "HealthIntentEnvelope",
    "HealthAnswerVerification",
    "HealthEvidenceTurn",
    "LOW_BACK_MANDATORY_DISCRIMINATOR_IDS",
    "PersonalEvidenceItem",
    "PersonalEvidencePacket",
    "PublicHealthIntent",
    "PublicPersonalEvidenceManifest",
    "RiskLevel",
    "SafetyProfileContext",
    "classify_health_intent",
    "build_health_evidence_turn",
    "compile_health_evidence_turn",
    "compile_personal_context",
    "verify_health_answer",
]
