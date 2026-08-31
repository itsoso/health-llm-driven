"""Shared semantic intent frame builder for XiaoBa surfaces."""
from __future__ import annotations

from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, IntentFrame
from app.services.agent_kernel.write_safety import is_explicit_write_cancellation
from app.services.utterance_intent_classifier import (
    classify_agent_utterance,
    has_retracted_symptom_write,
)


def build_intent_frame(
    envelope: AgentEnvelope,
    context: ExecutionContext,
) -> IntentFrame:
    """Build a typed intent frame from surface-normalized input.

    The current implementation wraps the existing semantic classifier and adds
    kernel-level evidence/ambiguity fields. Later phases can replace the
    classifier internals without changing callers.
    """
    text = envelope.text
    symptom_write_retracted = has_retracted_symptom_write(text)
    intent = classify_agent_utterance(text, reference_now=context.current_time)
    write_cancelled = is_explicit_write_cancellation(text)
    ambiguity: list[str] = []
    if intent.primary == "unknown" or intent.confidence < 0.6:
        ambiguity.append("low_confidence")
    if intent.is_write and intent.primary not in {"write", "mutate"}:
        ambiguity.append("write_flag_mismatch")
    if envelope.channel != context.channel:
        ambiguity.append("channel_mismatch")

    evidence = [
        f"classifier:{intent.reason}",
        f"channel:{envelope.channel}",
        f"timezone:{context.timezone}",
    ]
    if write_cancelled:
        evidence.append("safety:explicit_write_cancellation")
    if symptom_write_retracted:
        evidence.append("safety:symptom_write_retracted")
    if intent.scope:
        evidence.extend(f"scope:{key}={value}" for key, value in sorted(intent.scope.items()))

    cancelled_write_intent = write_cancelled and intent.is_write
    return IntentFrame(
        raw=intent.raw,
        normalized=intent.normalized,
        primary="chat" if cancelled_write_intent else intent.primary,
        domain=intent.domain,
        operation="none" if cancelled_write_intent else intent.operation,
        confidence=intent.confidence,
        evidence=tuple(evidence),
        ambiguity=tuple(ambiguity),
        scope=dict(intent.scope),
        is_write=False if write_cancelled else intent.is_write,
        requires_reliable_tool_model=(
            False if write_cancelled else intent.requires_reliable_tool_model
        ),
    )
