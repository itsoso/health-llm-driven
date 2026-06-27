from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProtocolDomain(StrEnum):
    metabolic = "metabolic"
    sleep = "sleep"
    movement = "movement"
    recovery = "recovery"
    supplement = "supplement"
    emotion = "emotion"
    measurement = "measurement"
    doctor_handoff = "doctor_handoff"


class RiskLevel(StrEnum):
    low = "low"
    moderate = "moderate"
    high = "high"


class EvidenceSourceType(StrEnum):
    guideline = "guideline"
    pubmed = "pubmed"
    dedao = "dedao"
    book = "book"
    course = "course"
    personal_outcome = "personal_outcome"
    model_inference = "model_inference"


class ExpectedDirection(StrEnum):
    increase = "increase"
    decrease = "decrease"
    stabilize = "stabilize"
    avoid = "avoid"


class ActionTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = Field(..., min_length=1, max_length=80)
    instruction: str = Field(..., min_length=1, max_length=1000)
    parameters: dict[str, Any] = Field(default_factory=dict)


class VerificationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, max_length=120)
    window_days: int = Field(..., ge=1, le=365)
    expected_direction: ExpectedDirection


class ProtocolFragment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str = Field(..., min_length=1, max_length=160)
    domain: ProtocolDomain
    title: str = Field(..., min_length=1, max_length=200)
    source_claims: list[str] = Field(..., min_length=1)
    source_types: list[EvidenceSourceType] = Field(default_factory=list)
    risk_level: RiskLevel
    applies_when: list[str] = Field(default_factory=list)
    forbidden_when: list[str] = Field(default_factory=list)
    action_template: ActionTemplate
    verification: VerificationSpec
    burden: dict[str, Any] = Field(default_factory=dict)
    claim_boundary: str = Field(..., min_length=1, max_length=1000)


class Contraindication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contraindication_id: str = Field(..., min_length=1, max_length=180)
    domain: ProtocolDomain
    severity: RiskLevel
    trigger: list[str] = Field(..., min_length=1)
    blocks: list[str] = Field(..., min_length=1)
    fallback: list[str] = Field(..., min_length=1)
    reason: str = Field(..., min_length=1, max_length=1000)


class EvalCaseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_query: str = Field(..., min_length=1)
    twin: dict[str, Any] = Field(default_factory=dict)


class EvalCaseExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    required_evidence_class: list[str] = Field(default_factory=list)


class EvalCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(..., min_length=1, max_length=180)
    domain: ProtocolDomain
    risk_level: RiskLevel
    input: EvalCaseInput
    expected: EvalCaseExpected

    @model_validator(mode="after")
    def require_high_risk_negative_boundaries(self) -> "EvalCaseSpec":
        if self.risk_level == RiskLevel.high and not self.expected.must_not_include:
            raise ValueError("high-risk eval cases require expected.must_not_include")
        return self
