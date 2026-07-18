"""Shared semantic intent frame builder for XiaoBa surfaces."""
from __future__ import annotations

from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, IntentFrame
from app.services.utterance_intent_classifier import classify_agent_utterance


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
    intent = classify_agent_utterance(text)
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
    if intent.scope:
        evidence.extend(f"scope:{key}={value}" for key, value in sorted(intent.scope.items()))

    return IntentFrame(
        raw=intent.raw,
        normalized=intent.normalized,
        primary=intent.primary,
        domain=intent.domain,
        operation=intent.operation,
        confidence=intent.confidence,
        evidence=tuple(evidence),
        ambiguity=tuple(ambiguity),
        scope=dict(intent.scope),
        is_write=intent.is_write,
        requires_reliable_tool_model=intent.requires_reliable_tool_model,
    )
