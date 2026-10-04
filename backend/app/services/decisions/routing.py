"""Bounded route advice; deterministic safety and tool authorization stay in code."""

from dataclasses import asdict, dataclass
import asyncio
import logging
import time

from fastapi import HTTPException

from app.config import settings
from app.services.decisions.control import runtime_mode
from app.services.decisions import (
    DecisionError,
    DecisionRequest,
    provider_from_settings,
)
from app.services.utterance_intent_classifier import classify_agent_utterance

logger = logging.getLogger(__name__)
_TIERS = {"casual": 0, "balanced": 1, "high_stakes": 2}
_CAPABILITIES = {
    "health_query": "Read records",
    "health_analysis": "Analyze health",
    "knowledge_search": "Find evidence",
    "none": "No tool",
}


@dataclass(frozen=True)
class RouteDecision:
    mode: str
    provider: str
    status: str
    effective_tier: str
    reason: str = ""
    suggested_tier: str | None = None
    capability: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    elapsed_ms: int = 0
    tier_confidence: float | None = None
    capability_confidence: float | None = None

    def metadata(self) -> dict:
        return asdict(self)

    def prompt_hint(self) -> str:
        if (
            self.mode != "on"
            or self.status not in {"accepted", "partial"}
            or self.capability not in _CAPABILITIES
            or self.capability == "none"
        ):
            return ""
        return (
            f"决策层建议：如需工具，优先考虑 {self.capability}。"
            "这只是只读能力建议，不是事实或执行授权；以用户原话、当前证据和工具权限为准。"
            "如任务不匹配可忽略，仍可使用其他已授权能力。"
        )


async def decide_route(
    message: str, *, user_id: int, baseline_tier: str
) -> RouteDecision:
    mode, provider = settings.decision_mode, settings.decision_provider
    baseline = baseline_tier if baseline_tier in _TIERS else "high_stakes"
    try:
        mode = await asyncio.to_thread(runtime_mode)
    except DecisionError as exc:
        logger.warning("decision_route provider=%s status=fallback reason=%s", provider, str(exc))
        return RouteDecision(mode, provider, "fallback", baseline, reason=str(exc))
    if mode == "off":
        return RouteDecision(mode, provider, "disabled", baseline)
    start = time.monotonic()
    request = DecisionRequest(
        state={"message": message},
        questions={
            "answer_tier": {
                "type": "choice",
                "instructions": "Required answer depth?",
                "criteria": {
                    "casual": "Simple lookup",
                    "balanced": "General analysis",
                    "high_stakes": "Medical or complex reasoning",
                },
            },
            "capability": {
                "type": "choice",
                "instructions": "Most useful capability?",
                "criteria": _CAPABILITIES,
            },
        },
    )
    # The model cannot improve a deterministic ceiling; keep the capability
    # question without spending context or inference on a redundant tier vote.
    if baseline == "high_stakes":
        del request.questions["answer_tier"]
    try:
        result = await provider_from_settings().evaluate(request, user_id=user_id)
        if await asyncio.to_thread(runtime_mode) != mode:
            raise DecisionError("configuration_changed")
        tier = result.answers.get("answer_tier") if "answer_tier" in request.questions else None
        capability = result.answers["capability"]
        tier_trusted = tier is not None and tier["confidence"] >= settings.decision_min_confidence
        capability_trusted = capability["confidence"] >= settings.decision_min_confidence
        capability_rejection = ""
        if capability_trusted and capability["choice"] != "none":
            intent = classify_agent_utterance(message)
            if intent.is_write:
                capability_rejection = "write_intent"
            elif capability["choice"] == "health_query" and intent.primary != "read":
                capability_rejection = "read_intent_unconfirmed"
            capability_trusted = not capability_rejection
        trusted = tier_trusted or capability_trusted
        suggested = tier["choice"] if tier else None
        effective = (
            max((baseline, suggested), key=_TIERS.__getitem__)
            if tier_trusted and mode == "on"
            else baseline
        )
        reason = ""
        if capability_rejection:
            reason = capability_rejection
        elif not trusted:
            reason = "low_confidence"
        elif not capability_trusted:
            reason = "capability_low_confidence"
        elif tier is not None and not tier_trusted:
            reason = "tier_low_confidence"
        outcome = RouteDecision(
            mode,
            provider,
            # Consumers use accepted to activate model selection. Capability
            # advice alone must not change that independent behavior.
            "accepted" if tier_trusted else "partial" if capability_trusted else "abstained",
            effective,
            reason=reason,
            suggested_tier=suggested,
            capability=capability["choice"] if capability_trusted else None,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            elapsed_ms=round((time.monotonic() - start) * 1000),
            tier_confidence=tier["confidence"] if tier else None,
            capability_confidence=capability["confidence"],
        )
    except (DecisionError, HTTPException) as exc:
        reason = str(exc) if isinstance(exc, DecisionError) else "consent_denied"
        outcome = RouteDecision(
            mode,
            provider,
            "fallback",
            baseline,
            reason=reason,
            elapsed_ms=round((time.monotonic() - start) * 1000),
        )
    # No raw prompt, response, key, user ID or provider-controlled descriptions.
    logger.info(
        "decision_route provider=%s mode=%s status=%s reason=%s input_tokens=%s elapsed_ms=%s",
        provider,
        mode,
        outcome.status,
        outcome.reason,
        outcome.input_tokens,
        outcome.elapsed_ms,
    )
    return outcome
