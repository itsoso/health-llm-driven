"""Structured Mobile continuation must preserve server-owned clinical routing."""

from datetime import UTC, datetime
import json

import pytest

from app.services.health_evidence import (
    RiskLevel,
    SafetyProfileContext,
    classify_health_intent,
    compile_health_evidence_turn,
)
from app.services.health_evidence.continuation import (
    parse_health_evidence_continuation,
    resolve_health_evidence_continuation_query,
)
from app.twin.schema import HealthTwin, TwinMeta


NOW = datetime(2026, 7, 29, tzinfo=UTC)


def _context(answers, **overrides):
    payload = {
        "version": "health-evidence-continuation.v1",
        "parent_intent_id": "health_advice.symptom.low_back_pain",
        "parent_message_id": 912,
        "parent_turn_id": "turn-mobile-1",
        "answers": answers,
        **overrides,
    }
    return json.dumps(
        {"health_evidence_continuation": payload},
        ensure_ascii=False,
    )


def _intent(extra_context):
    parsed = parse_health_evidence_continuation(extra_context)
    return parsed, classify_health_intent(
        parsed.clinical_query("我的回答已提交")
    )


@pytest.mark.parametrize(
    ("discriminator_id", "expected_risk"),
    [
        ("low_back.cauda_equina", RiskLevel.EMERGENCY),
        (
            "low_back.progressive_neurologic_deficit",
            RiskLevel.EMERGENCY,
        ),
        ("low_back.major_trauma", RiskLevel.HIGH),
        ("low_back.systemic_red_flag", RiskLevel.HIGH),
    ],
)
def test_affirmative_structured_answer_stays_health_and_escalates(
    discriminator_id,
    expected_risk,
):
    parsed, intent = _intent(
        _context(
            [{"discriminator_id": discriminator_id, "answer": "yes"}]
        )
    )

    assert parsed.continuation is not None
    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.risk_level == expected_risk


def test_negative_answers_close_only_the_answered_discriminators():
    parsed, intent = _intent(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                },
                {
                    "discriminator_id": "low_back.major_trauma",
                    "answer": "no",
                },
            ]
        )
    )
    turn = compile_health_evidence_turn(
        twin=HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW)),
        intent=intent,
        authority_results=[],
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
    )

    assert parsed.continuation is not None
    assert {
        item["id"] for item in turn.missing_discriminators
    } == {
        "low_back.progressive_neurologic_deficit",
        "low_back.systemic_red_flag",
    }


def test_unknown_answer_remains_an_explicit_missing_discriminator():
    parsed, intent = _intent(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "unknown",
                }
            ]
        )
    )
    turn = compile_health_evidence_turn(
        twin=HealthTwin(meta=TwinMeta(user_id=7, generated_at=NOW)),
        intent=intent,
        authority_results=[],
        safety_profile=SafetyProfileContext(population="adults_16_plus"),
    )

    assert parsed.continuation is not None
    assert "low_back.cauda_equina" in {
        item["id"] for item in turn.missing_discriminators
    }


def test_structured_population_answer_compiles_to_server_owned_age_band():
    parsed, intent = _intent(
        _context(
            [
                {
                    "discriminator_id": "low_back.population_adult_16_plus",
                    "answer": "yes",
                }
            ]
        )
    )

    assert parsed.continuation is not None
    assert "本人已满16岁" in parsed.continuation.canonical_query()
    assert intent.intent_id == "health_advice.symptom.low_back_pain"


@pytest.mark.parametrize(
    "payload",
    [
        _context(
            [{"discriminator_id": "low_back.cauda_equina", "answer": "maybe"}]
        ),
        _context(
            [{"discriminator_id": "other.symptom", "answer": "yes"}]
        ),
        _context(
            [{"discriminator_id": "low_back.cauda_equina", "answer": "yes"}],
            parent_intent_id="general.chat",
        ),
        _context(
            [{"discriminator_id": "low_back.cauda_equina", "answer": "yes"}],
            parent_message_id=None,
            parent_turn_id=None,
        ),
        _context(
            [{"discriminator_id": "low_back.cauda_equina", "answer": "yes"}],
            parent_message_id=None,
        ),
    ],
)
def test_malformed_attempt_never_falls_through_to_general_chat(payload):
    parsed, intent = _intent(payload)

    assert parsed.attempted is True
    assert parsed.continuation is None
    assert parsed.error
    assert intent.intent_id == "health_advice.symptom.low_back_pain"
    assert intent.risk_level == RiskLevel.MEDIUM


def test_unrelated_extra_context_does_not_change_normal_intent():
    parsed = parse_health_evidence_continuation(
        json.dumps({"client": "mac", "model_id": "qwen3.7-max"})
    )

    assert parsed.attempted is False
    assert parsed.clinical_query("你好") == "你好"


def test_cross_user_parent_message_fails_closed(
    db,
    auth_user_and_headers,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.user import User

    current_user, _headers = auth_user_and_headers
    other_user = User(name="other continuation owner")
    db.add(other_user)
    db.flush()
    conversation = AgentConversation(
        user_id=other_user.id,
        title="other user health turn",
    )
    db.add(conversation)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content="腰痛，是否需要做 MRI？",
            client_turn_id="other-turn",
        )
    )
    parent = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="请补充警示征象。",
        meta={
            "client_turn_id": "other-turn",
            "health_evidence_manifest": {
                "intent": {
                    "intent_id": (
                        "health_advice.symptom.low_back_pain"
                    )
                }
            },
        },
    )
    db.add(parent)
    db.commit()

    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                }
            ],
            parent_message_id=parent.id,
            parent_turn_id="other-turn",
        )
    )

    assert resolve_health_evidence_continuation_query(
        db,
        user_id=current_user.id,
        parsed=parsed,
        fallback_query="已提交",
    ) == "腰痛；已提交"


def test_invalid_parent_preserves_current_emergency_text(
    db,
    auth_user_and_headers,
):
    user, _headers = auth_user_and_headers
    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                }
            ],
            parent_message_id=999_999_999,
        )
    )

    query = resolve_health_evidence_continuation_query(
        db,
        user_id=user.id,
        parsed=parsed,
        fallback_query="我现在排不出尿且会阴麻木",
    )

    assert "我现在排不出尿且会阴麻木" in query
    assert classify_health_intent(query).risk_level == RiskLevel.EMERGENCY


def test_malformed_payload_preserves_current_emergency_text():
    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "maybe",
                }
            ]
        )
    )

    query = parsed.clinical_query("我现在排不出尿且会阴麻木")

    assert "我现在排不出尿且会阴麻木" in query
    assert classify_health_intent(query).risk_level == RiskLevel.EMERGENCY


def test_production_client_turn_storage_key_restores_parent_focus(
    db,
    auth_user_and_headers,
):
    from app.models.agent_conversation import AgentConversation
    from app.services.agent_conversation_service import AgentConversationService

    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="production continuation binding",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    service = AgentConversationService(db)
    turn_id = "turn-mobile-production-1"
    user_message, created = service.save_user_message_once(
        conversation.id,
        user.id,
        "腰痛三个月了，是否需要做 MRI？",
        client_turn_id=turn_id,
    )
    assert created is True
    assert user_message.client_turn_id == f"{user.id}:{turn_id}"
    parent = service.save_message(
        conversation.id,
        "assistant",
        "请补充警示征象。",
        meta={
            "client_turn_id": turn_id,
            "health_evidence_manifest": {
                "intent": {
                    "intent_id": "health_advice.symptom.low_back_pain"
                }
            },
        },
    )
    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                }
            ],
            parent_message_id=parent.id,
            parent_turn_id=turn_id,
        )
    )

    query = resolve_health_evidence_continuation_query(
        db,
        user_id=user.id,
        parsed=parsed,
        fallback_query="已提交",
    )

    assert "腰痛三个月了，是否需要做 MRI？" in query
    assert "没有排尿困难" in query
    assert classify_health_intent(query).intent_id == (
        "health_advice.symptom.low_back_pain"
    )


def test_parent_turn_id_requires_exact_assistant_meta_binding(
    db,
    auth_user_and_headers,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_conversation_service import AgentConversationService

    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="missing parent turn binding",
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    service = AgentConversationService(db)
    turn_id = "turn-mobile-unbound"
    service.save_user_message_once(
        conversation.id,
        user.id,
        "腰痛，是否需要做 MRI？",
        client_turn_id=turn_id,
    )
    parent = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="请补充警示征象。",
        meta={
            "health_evidence_manifest": {
                "intent": {
                    "intent_id": "health_advice.symptom.low_back_pain"
                }
            },
        },
    )
    db.add(parent)
    db.commit()
    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                }
            ],
            parent_message_id=parent.id,
            parent_turn_id=turn_id,
        )
    )

    query = resolve_health_evidence_continuation_query(
        db,
        user_id=user.id,
        parsed=parsed,
        fallback_query="我现在排不出尿且会阴麻木",
    )

    assert "我现在排不出尿且会阴麻木" in query
    assert classify_health_intent(query).risk_level == RiskLevel.EMERGENCY


def test_current_message_red_flag_cannot_be_overridden_by_negative_buttons(
    db,
    auth_user_and_headers,
):
    from app.models.agent_conversation import AgentConversation, AgentMessage

    user, _headers = auth_user_and_headers
    conversation = AgentConversation(
        user_id=user.id,
        title="current symptom wins",
    )
    db.add(conversation)
    db.flush()
    db.add(
        AgentMessage(
            conversation_id=conversation.id,
            role="user",
            content="我腰疼怎么办",
            client_turn_id="same-user-turn",
        )
    )
    parent = AgentMessage(
        conversation_id=conversation.id,
        role="assistant",
        content="请补充警示征象。",
        meta={
            "client_turn_id": "same-user-turn",
            "health_evidence_manifest": {
                "intent": {
                    "intent_id": (
                        "health_advice.symptom.low_back_pain"
                    )
                }
            },
        },
    )
    db.add(parent)
    db.commit()
    parsed = parse_health_evidence_continuation(
        _context(
            [
                {
                    "discriminator_id": "low_back.cauda_equina",
                    "answer": "no",
                }
            ],
            parent_message_id=parent.id,
            parent_turn_id="same-user-turn",
        )
    )

    query = resolve_health_evidence_continuation_query(
        db,
        user_id=user.id,
        parsed=parsed,
        fallback_query="我现在排不出尿而且会阴麻木",
    )

    assert "我现在排不出尿而且会阴麻木" in query
    assert classify_health_intent(query).risk_level == RiskLevel.EMERGENCY
