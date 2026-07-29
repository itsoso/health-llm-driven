"""Strict parsing for structured Mobile health-discriminator continuations."""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Mapping


CONTINUATION_VERSION = "health-evidence-continuation.v1"
LOW_BACK_INTENT_ID = "health_advice.symptom.low_back_pain"
_LOW_BACK_DISCRIMINATORS = frozenset(
    {
        "low_back.cauda_equina",
        "low_back.progressive_neurologic_deficit",
        "low_back.major_trauma",
        "low_back.systemic_red_flag",
        "low_back.population_adult_16_plus",
    }
)
_ANSWERS = frozenset({"yes", "no", "unknown"})
_TURN_REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


@dataclass(frozen=True)
class DiscriminatorAnswer:
    discriminator_id: str
    answer: str


@dataclass(frozen=True)
class HealthEvidenceContinuation:
    parent_intent_id: str
    answers: tuple[DiscriminatorAnswer, ...]
    parent_message_id: int
    parent_turn_id: str | None = None

    def canonical_query(self) -> str:
        """Compile client data into server-owned clinical language.

        Downstream intent and safety rules consume this canonical text, never the
        button label or client-composed prose.
        """

        phrases = ["腰痛"]
        for item in self.answers:
            phrases.append(
                _CANONICAL_PHRASES[item.discriminator_id][item.answer]
            )
        return "；".join(phrase for phrase in phrases if phrase)


@dataclass(frozen=True)
class ContinuationParseResult:
    attempted: bool
    continuation: HealthEvidenceContinuation | None = None
    error: str | None = None

    def clinical_query(self, fallback_query: str) -> str:
        if self.continuation is not None:
            return self.continuation.canonical_query()
        if self.attempted:
            # A malformed health continuation must remain inside the health safety
            # runtime. Treat every discriminator as unknown and ask again, while
            # retaining current free text so a newly typed red flag can only raise
            # risk and is never erased by a broken/stale client payload.
            return _low_back_query_with_current_text(fallback_query)
        return str(fallback_query or "")


_CANONICAL_PHRASES: dict[str, dict[str, str]] = {
    "low_back.population_adult_16_plus": {
        "yes": "本人已满16岁",
        "no": "本人未满16岁",
        "unknown": "",
    },
    "low_back.cauda_equina": {
        "yes": (
            "排尿困难、膀胱/肠道控制改变或会阴感觉异常中至少一项为是"
        ),
        "no": (
            "没有排尿困难，没有尿失禁，没有大小便异常，"
            "没有会阴麻木，没有鞍区麻木"
        ),
        "unknown": "",
    },
    "low_back.progressive_neurologic_deficit": {
        "yes": "双腿明显或进行性麻木/无力警示线索中至少一项为是",
        "no": "没有双腿麻木或无力",
        "unknown": "",
    },
    "low_back.major_trauma": {
        "yes": "近期严重外伤警示线索为是",
        "no": "近期没有严重外伤或车祸",
        "unknown": "",
    },
    "low_back.systemic_red_flag": {
        "yes": "发热、不明原因体重下降或癌症/严重感染史中至少一项为是",
        "no": (
            "没有发热或严重感染，没有不明原因体重下降，"
            "没有癌症史"
        ),
        "unknown": "",
    },
}


def parse_health_evidence_continuation(
    extra_context: str | None,
) -> ContinuationParseResult:
    """Parse one private request payload without accepting arbitrary fields."""

    if not extra_context:
        return ContinuationParseResult(attempted=False)
    try:
        outer = json.loads(extra_context)
    except (TypeError, ValueError):
        return ContinuationParseResult(attempted=False)
    if not isinstance(outer, Mapping):
        return ContinuationParseResult(attempted=False)
    if "health_evidence_continuation" not in outer:
        return ContinuationParseResult(attempted=False)

    raw = outer.get("health_evidence_continuation")
    if not isinstance(raw, Mapping):
        return ContinuationParseResult(attempted=True, error="invalid_payload")
    if str(raw.get("version") or "") != CONTINUATION_VERSION:
        return ContinuationParseResult(attempted=True, error="invalid_version")
    if str(raw.get("parent_intent_id") or "") != LOW_BACK_INTENT_ID:
        return ContinuationParseResult(
            attempted=True,
            error="invalid_parent_intent",
        )

    parent_message_id = _positive_int(raw.get("parent_message_id"))
    parent_turn_id = _safe_turn_ref(raw.get("parent_turn_id"))
    if parent_message_id is None:
        return ContinuationParseResult(
            attempted=True,
            error="missing_parent_message",
        )

    raw_answers = raw.get("answers")
    if not isinstance(raw_answers, list) or not 1 <= len(raw_answers) <= 5:
        return ContinuationParseResult(attempted=True, error="invalid_answers")

    answers: list[DiscriminatorAnswer] = []
    seen: set[str] = set()
    for item in raw_answers:
        if not isinstance(item, Mapping):
            return ContinuationParseResult(
                attempted=True,
                error="invalid_answer_item",
            )
        discriminator_id = str(item.get("discriminator_id") or "").strip()
        answer = str(item.get("answer") or "").strip().lower()
        if discriminator_id not in _LOW_BACK_DISCRIMINATORS:
            return ContinuationParseResult(
                attempted=True,
                error="invalid_discriminator",
            )
        if answer not in _ANSWERS:
            return ContinuationParseResult(
                attempted=True,
                error="invalid_answer",
            )
        if discriminator_id in seen:
            return ContinuationParseResult(
                attempted=True,
                error="duplicate_discriminator",
            )
        seen.add(discriminator_id)
        answers.append(
            DiscriminatorAnswer(
                discriminator_id=discriminator_id,
                answer=answer,
            )
        )

    answers.sort(key=lambda item: item.discriminator_id)
    return ContinuationParseResult(
        attempted=True,
        continuation=HealthEvidenceContinuation(
            parent_intent_id=LOW_BACK_INTENT_ID,
            answers=tuple(answers),
            parent_message_id=parent_message_id,
            parent_turn_id=parent_turn_id,
        ),
    )


def resolve_health_evidence_continuation_query(
    db: Any,
    *,
    user_id: int,
    parsed: ContinuationParseResult,
    fallback_query: str,
) -> str:
    """Bind structured answers to an owned, persisted health-evidence turn.

    The client supplies answer enums and a parent message identifier. The server
    reloads the original user question and validates the parent assistant manifest
    before preserving the decision focus, such as imaging or chronic care. Invalid
    or cross-user references fail closed to a fresh low-back screening turn.
    """

    continuation = parsed.continuation
    if continuation is None:
        return parsed.clinical_query(fallback_query)
    parent_query = _owned_parent_query(
        db,
        user_id=user_id,
        continuation=continuation,
    )
    if not parent_query:
        return _low_back_query_with_current_text(fallback_query)

    from .intent import classify_health_intent

    parent_intent = classify_health_intent(parent_query)
    if parent_intent.intent_id != continuation.parent_intent_id:
        return _low_back_query_with_current_text(fallback_query)
    current_query = str(fallback_query or "").strip()
    parts = [parent_query]
    if current_query and current_query != parent_query:
        # Current free text is untrusted but safety-relevant. Keeping it means an
        # affirmative symptom typed alongside stale/negative buttons can only
        # raise risk; it cannot be erased by the structured continuation.
        parts.append(current_query)
    parts.append(continuation.canonical_query())
    return "；".join(parts)


def _owned_parent_query(
    db: Any,
    *,
    user_id: int,
    continuation: HealthEvidenceContinuation,
) -> str | None:
    from app.models.agent_conversation import AgentConversation, AgentMessage

    parent = (
        db.query(AgentMessage)
        .join(
            AgentConversation,
            AgentConversation.id == AgentMessage.conversation_id,
        )
        .filter(
            AgentMessage.id == continuation.parent_message_id,
            AgentMessage.role == "assistant",
            AgentConversation.user_id == user_id,
        )
        .first()
    )
    if parent is None or not _is_matching_health_parent(
        getattr(parent, "meta", None),
        continuation=continuation,
    ):
        return None

    query = db.query(AgentMessage).filter(
        AgentMessage.conversation_id == parent.conversation_id,
        AgentMessage.role == "user",
        AgentMessage.id < parent.id,
    )
    if continuation.parent_turn_id:
        from app.services.agent_conversation_service import (
            AgentConversationService,
        )

        stored_turn_id = AgentConversationService._client_turn_storage_key(
            user_id,
            continuation.parent_turn_id,
        )
        query = query.filter(
            AgentMessage.client_turn_id.in_(
                (continuation.parent_turn_id, stored_turn_id)
            )
        )
    user_message = query.order_by(AgentMessage.id.desc()).first()
    if user_message is None:
        return None
    content = str(getattr(user_message, "content", "") or "").strip()
    return content or None


def _is_matching_health_parent(
    value: Any,
    *,
    continuation: HealthEvidenceContinuation,
) -> bool:
    if not isinstance(value, Mapping):
        return False
    manifest = value.get("health_evidence_manifest")
    if not isinstance(manifest, Mapping):
        return False
    intent = manifest.get("intent")
    if not isinstance(intent, Mapping):
        return False
    if str(intent.get("intent_id") or "") != continuation.parent_intent_id:
        return False
    persisted_turn_id = _safe_turn_ref(value.get("client_turn_id"))
    if continuation.parent_turn_id:
        return persisted_turn_id == continuation.parent_turn_id
    return True


def _low_back_query_with_current_text(fallback_query: str) -> str:
    current_query = str(fallback_query or "").strip()
    if not current_query or current_query == "腰痛":
        return "腰痛"
    return f"腰痛；{current_query}"


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_turn_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or _TURN_REF_RE.fullmatch(normalized) is None:
        return None
    return normalized
