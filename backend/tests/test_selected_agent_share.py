"""Server-owned selected Agent conversation sharing."""

from __future__ import annotations

import hashlib

import pytest

from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.shared_conversation import SharedConversation
from app.models.user import User
from app.services.health_evidence import delivery
from app.services.health_evidence.authority import LOW_BACK_CLAIM_POLICY
from app.services.health_evidence.verifier import health_manifest_sha256


_HEALTH_QUERY = "我腰疼，应该怎么处理？"
_HEALTH_ANSWER = "保持适度活动，并留意需要紧急就医的警示征象。"


def _verified_health_meta(released_text: str) -> dict:
    claim_id = "claim:c_low_back_self_management_activity_boundary"
    manifest = {
        "version": "health-evidence.v1",
        "intent": {
            "version": "health-intent.v1",
            "intent_id": "health_advice.symptom.low_back_pain",
            "intent": "health_advice",
            "domain": "low_back_pain",
            "risk_level": "medium",
            "requires_authority": True,
        },
        "risk_level": "medium",
        "sufficiency": "sufficient",
        "verifier_verdict": "pass",
        "evidence_refs": [claim_id],
        "authority_evidence_refs": [claim_id],
        "authority_artifacts": [
            {
                "doc_id": claim_id,
                "sha256": LOW_BACK_CLAIM_POLICY[claim_id].artifact_sha256,
            }
        ],
    }
    return {
        "health_evidence_manifest": manifest,
        "health_evidence_verification": {
            "verdict": "pass",
            "reasons": [],
            "evidence_refs_used": [claim_id],
            "released_text_sha256": hashlib.sha256(
                released_text.encode("utf-8")
            ).hexdigest(),
            "manifest_sha256": health_manifest_sha256(manifest),
        },
    }


def _conversation_with_messages(db, user_id: int, rows: list[dict]):
    conversation = AgentConversation(
        user_id=user_id,
        title="selected share",
        session_key=f"selected-share-{user_id}-{len(rows)}",
    )
    db.add(conversation)
    db.flush()
    messages = [
        AgentMessage(conversation_id=conversation.id, **row)
        for row in rows
    ]
    db.add_all(messages)
    db.commit()
    for message in messages:
        db.refresh(message)
    return conversation, messages


def test_selected_agent_share_hides_support_user_and_revalidates_on_get(
    client,
    db,
    auth_user_and_headers,
    monkeypatch,
):
    user, headers = auth_user_and_headers
    conversation, messages = _conversation_with_messages(
        db,
        user.id,
        [
            {"role": "user", "content": _HEALTH_QUERY},
            {
                "role": "assistant",
                "content": _HEALTH_ANSWER,
                "meta": _verified_health_meta(_HEALTH_ANSWER),
            },
            {"role": "user", "content": "不相关的下一轮"},
            {"role": "assistant", "content": "不相关回答"},
        ],
    )
    current = {"value": True}
    monkeypatch.setattr(
        delivery,
        "is_current_health_evidence_artifact",
        lambda *_args, **_kwargs: current["value"],
    )

    created = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[1].id],
        },
    )

    assert created.status_code == 200
    shared = (
        db.query(SharedConversation)
        .filter(SharedConversation.share_token == created.json()["share_token"])
        .one()
    )
    assert [item["role"] for item in shared.messages_snapshot] == [
        "user",
        "assistant",
    ]
    assert shared.messages_snapshot[0]["private_support"] is True
    assert shared.messages_snapshot[0]["selected"] is False
    assert shared.messages_snapshot[1]["selected"] is True
    assert _HEALTH_QUERY not in client.get(
        f"/api/v1/shared/{shared.share_token}?count_view=false"
    ).text

    before = client.get(
        f"/api/v1/shared/{shared.share_token}?count_view=false"
    )
    assert before.status_code == 200
    assert before.json()["messages"] == [
        {
            "role": "assistant",
            "content": _HEALTH_ANSWER,
            "created_at": messages[1].created_at.isoformat(),
            "image_url": None,
        }
    ]

    current["value"] = False
    after = client.get(
        f"/api/v1/shared/{shared.share_token}?count_view=false"
    )
    assert after.status_code == 200
    assert len(after.json()["messages"]) == 1
    assert after.json()["messages"][0]["role"] == "assistant"
    assert _HEALTH_ANSWER not in after.text
    assert _HEALTH_QUERY not in after.text


def test_selected_agent_share_public_order_is_conversation_order(
    client,
    db,
    auth_user_and_headers,
):
    user, headers = auth_user_and_headers
    conversation, messages = _conversation_with_messages(
        db,
        user.id,
        [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "第一答"},
            {"role": "user", "content": "第二问"},
            {"role": "assistant", "content": "第二答"},
        ],
    )

    created = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[3].id, messages[0].id],
        },
    )

    assert created.status_code == 200
    public = client.get(
        f"/api/v1/shared/{created.json()['share_token']}?count_view=false"
    )
    assert [item["content"] for item in public.json()["messages"]] == [
        "第一问",
        "第二答",
    ]


@pytest.mark.parametrize(
    ("message_ids", "expected_status"),
    [
        ([], 422),
        ([1, 1], 422),
        ([0], 422),
        ([-1], 422),
        (list(range(1, 102)), 422),
    ],
)
def test_selected_agent_share_rejects_invalid_id_lists(
    client,
    auth_user_and_headers,
    message_ids,
    expected_status,
):
    _user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": 1,
            "source_type": "agent",
            "message_ids": message_ids,
        },
    )

    assert response.status_code == expected_status


def test_selected_agent_share_rejects_ids_outside_owned_conversation(
    client,
    db,
    auth_user_and_headers,
):
    user, headers = auth_user_and_headers
    owned, owned_messages = _conversation_with_messages(
        db,
        user.id,
        [{"role": "user", "content": "我的对话"}],
    )
    other_owned, other_owned_messages = _conversation_with_messages(
        db,
        user.id,
        [{"role": "user", "content": "我的另一段对话"}],
    )
    other_user = User(
        name="other share user",
        username="other-share-user",
        email="other-share-user@example.test",
        hashed_password="not-used",
        is_active=True,
        is_approved=True,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)
    _foreign, foreign_messages = _conversation_with_messages(
        db,
        other_user.id,
        [{"role": "user", "content": "别人的对话"}],
    )

    for message_id in (
        other_owned_messages[0].id,
        foreign_messages[0].id,
        max(message.id for message in owned_messages) + 99_999,
    ):
        response = client.post(
            "/api/v1/shared/create",
            headers=headers,
            json={
                "conversation_id": owned.id,
                "source_type": "agent",
                "message_ids": [message_id],
            },
        )
        assert response.status_code == 400

    assert other_owned.id != owned.id


def test_selected_agent_share_rejects_unbound_assistant(
    client,
    db,
    auth_user_and_headers,
):
    user, headers = auth_user_and_headers
    conversation, messages = _conversation_with_messages(
        db,
        user.id,
        [{"role": "assistant", "content": "没有前序用户消息"}],
    )

    response = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[0].id],
        },
    )

    assert response.status_code == 400


@pytest.mark.parametrize("role", ["system", "tool", "developer"])
def test_selected_agent_share_rejects_non_conversation_roles(
    client,
    db,
    auth_user_and_headers,
    role,
):
    user, headers = auth_user_and_headers
    conversation, messages = _conversation_with_messages(
        db,
        user.id,
        [{"role": role, "content": "内部持久行不得公开"}],
    )

    response = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[0].id],
        },
    )

    assert response.status_code == 400


def test_selected_agent_shares_never_overwrite_each_other_or_full_share(
    client,
    db,
    auth_user_and_headers,
):
    user, headers = auth_user_and_headers
    conversation, messages = _conversation_with_messages(
        db,
        user.id,
        [
            {"role": "user", "content": "问题"},
            {"role": "assistant", "content": "回答"},
        ],
    )

    first = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[0].id],
        },
    )
    second = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
            "message_ids": [messages[1].id],
        },
    )
    full = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": conversation.id,
            "source_type": "agent",
        },
    )

    assert first.status_code == second.status_code == full.status_code == 200
    tokens = {
        first.json()["share_token"],
        second.json()["share_token"],
        full.json()["share_token"],
    }
    assert len(tokens) == 3
    assert [
        item["content"]
        for item in client.get(
            f"/api/v1/shared/{first.json()['share_token']}?count_view=false"
        ).json()["messages"]
    ] == ["问题"]
    assert [
        item["content"]
        for item in client.get(
            f"/api/v1/shared/{second.json()['share_token']}?count_view=false"
        ).json()["messages"]
    ] == ["回答"]


def test_message_ids_are_only_valid_for_agent_share(
    client,
    auth_user_and_headers,
):
    _user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": 1,
            "source_type": "health",
            "message_ids": [1],
        },
    )

    assert response.status_code == 422


@pytest.mark.parametrize("extra_key", ["content", "meta", "health_meta", "proof"])
def test_selected_agent_share_rejects_client_supplied_payloads(
    client,
    auth_user_and_headers,
    extra_key,
):
    _user, headers = auth_user_and_headers

    response = client.post(
        "/api/v1/shared/create",
        headers=headers,
        json={
            "conversation_id": 1,
            "source_type": "agent",
            "message_ids": [1],
            extra_key: {"untrusted": True},
        },
    )

    assert response.status_code == 422
