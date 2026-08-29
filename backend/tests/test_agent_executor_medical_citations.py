from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from tests.conftest import create_authenticated_user


def test_terminal_bmi_answer_exposes_and_persists_clickable_medical_citations(
    db,
    auth_user_and_headers,
):
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conversation = service.get_or_create_conversation(
        user.id,
        None,
        title="帮我算我的 BMI",
    )
    assistant = service.save_message(
        conversation.id,
        "assistant",
        "BMI = 70 / (1.75 × 1.75) = 22.9，属于正常范围。",
        meta={"completion_status": "complete"},
    )

    event = AgentExecutor(db)._attach_medical_citations_to_terminal_event(
        {
            "event": "done",
            "data": {
                "conversation_id": conversation.id,
                "message_id": assistant.id,
                "completion_status": "complete",
            },
        },
        user_id=user.id,
        user_message="帮我算我的 BMI",
    )

    assert event["data"]["medical_citation_required"] is True
    assert event["data"]["medical_citation_topics"] == ["bmi"]
    urls = [item["url"] for item in event["data"]["medical_citations"]]
    assert urls == [
        (
            "https://www.nhc.gov.cn/ylyjs/zcwj/202412/"
            "75cb79c171c94def9e768193e65484f7/files/"
            "1736390749000_59785.pdf"
        ),
        "https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html",
    ]

    db.expire_all()
    persisted = db.query(AgentMessage).filter(AgentMessage.id == assistant.id).one()
    assert persisted.meta["medical_citation_required"] is True
    assert persisted.meta["medical_citations"] == event["data"]["medical_citations"]


def test_incomplete_terminal_event_never_claims_medical_citations(
    db,
    auth_user_and_headers,
):
    user, _ = auth_user_and_headers
    event = AgentExecutor(db)._attach_medical_citations_to_terminal_event(
        {
            "event": "done",
            "data": {
                "conversation_id": None,
                "message_id": None,
                "completion_status": "error",
            },
        },
        user_id=user.id,
        user_message="帮我算我的 BMI",
    )

    assert "medical_citations" not in event["data"]


def test_terminal_citation_persistence_cannot_modify_another_users_message(
    db,
    auth_user_and_headers,
):
    user, _ = auth_user_and_headers
    other_user, _ = create_authenticated_user(db)
    service = AgentConversationService(db)
    other_conversation = service.get_or_create_conversation(
        other_user.id,
        None,
        title="other user",
    )
    other_assistant = service.save_message(
        other_conversation.id,
        "assistant",
        "BMI 是 22.9。",
        meta={"completion_status": "complete"},
    )

    AgentExecutor(db)._attach_medical_citations_to_terminal_event(
        {
            "event": "done",
            "data": {
                "conversation_id": other_conversation.id,
                "message_id": other_assistant.id,
                "completion_status": "complete",
            },
        },
        user_id=user.id,
        user_message="帮我算我的 BMI",
    )

    db.expire_all()
    persisted = db.query(AgentMessage).filter(
        AgentMessage.id == other_assistant.id,
    ).one()
    assert persisted.meta == {"completion_status": "complete"}
