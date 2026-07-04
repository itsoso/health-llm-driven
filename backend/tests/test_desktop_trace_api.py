def test_desktop_trace_returns_conversation_metadata(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers

    from app.models.agent_conversation import AgentConversation, AgentMessage

    conv = AgentConversation(user_id=user.id, title="Trace test")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add(AgentMessage(
        conversation_id=conv.id,
        role="user",
        content="为什么 4.7 没回复？",
    ))
    db.add(AgentMessage(
        conversation_id=conv.id,
        role="assistant",
        content="这次是模型返回空内容。",
        meta={
            "model": "commercial/Claude-Opus-4.7",
            "elapsed_ms": 7100,
            "llm_rounds": 2,
            "finish_reason": "stop",
            "completion_status": "complete",
            "sources_used": ["系统知识库", "基因 (MTHFR)"],
            "tool_calls": [{"name": "knowledge_search", "success": True}],
            "cards": [{"type": "system_knowledge_evidence", "title": "HbA1c"}],
        },
    ))
    db.commit()

    resp = client.get(f"/api/v1/desktop/traces/{conv.id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation"]["id"] == conv.id
    assert body["assistant_message"]["model"] == "commercial/Claude-Opus-4.7"
    assert body["assistant_message"]["finish_reason"] == "stop"
    assert body["assistant_message"]["completion_status"] == "complete"
    assert body["assistant_message"]["llm_rounds"] == 2
    assert body["sources_used"] == ["系统知识库", "基因 (MTHFR)"]
    assert body["tool_calls"][0]["name"] == "knowledge_search"
    assert body["evidence_cards"][0]["title"] == "HbA1c"


def test_desktop_trace_is_scoped_to_current_user(client, db, auth_user_and_headers):
    _user, headers = auth_user_and_headers

    from app.models.agent_conversation import AgentConversation
    from app.models.user import User

    other = User(
        username="trace_other",
        email="trace_other@example.com",
        hashed_password="x",
        name="Other",
        is_active=True,
        is_approved=True,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    conv = AgentConversation(user_id=other.id, title="private")
    db.add(conv)
    db.commit()
    db.refresh(conv)

    resp = client.get(f"/api/v1/desktop/traces/{conv.id}", headers=headers)

    assert resp.status_code == 404
