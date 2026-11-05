"""Closed symptom writes use the real gateway/API/receipt without model work."""
import json

import pytest

from app.services import agent_executor as ae


@pytest.mark.parametrize("message", [
    "记录流鼻涕症状", "记录流鼻涕", "记录流鼻涕的症状",
    "请帮我记录鼻塞症状。",
])
def test_closed_symptom_suffix_keeps_current_turn_payload(message):
    assert ae._is_proven_pure_symptom_record_request(message)
    assert ae._extract_clear_symptom_record(message) == {
        "body_part": "respiratory", "description": message.rstrip("。"),
    }


@pytest.mark.parametrize("message", [
    "记录流鼻涕症状，怎么缓解", "记录流鼻涕症状，需要就医吗",
    "记录流鼻涕症状并分析原因", "记录流鼻涕症状和头痛",
    "不要记录流鼻涕症状", "记录妈妈流鼻涕症状", "记录流鼻涕症状给妈妈",
    "如果流鼻涕症状就记录", "他说记录流鼻涕症状", "‘记录流鼻涕症状’",
    "记录流鼻涕症状吗", "昨天记录流鼻涕症状", "记录流鼻涕症状，修改昨天的记录",
])
def test_unknown_tail_never_proves_closed_symptom(message):
    assert not ae._is_proven_pure_symptom_record_request(message)
    assert not ae._is_closed_nasal_symptom_record(message)


@pytest.mark.parametrize("message", [
    "记录胸痛症状", "记录呼吸困难", "记录头痛症状", "记录咳血症状",
    "记录流鼻涕症状，胸痛", "记录流鼻涕症状，不想活了", "记录流鼻涕症状，吃什么药",
    "记录流鼻涕症状，严重程度3", "记录昨天流鼻涕症状", "流鼻涕",
    "  记录流鼻涕症状", "记录流鼻涕症状\n", "记录流鼻涕症状\t",
])
def test_nasal_preplan_never_reclassifies_clinical_or_unknown_input(message):
    assert not ae._is_closed_nasal_symptom_record(message)


@pytest.mark.parametrize("message", [
    "记录流鼻涕症状", "记录流鼻涕", "记录流鼻涕的症状", "记录鼻塞症状", "记录打喷嚏症状",
])
@pytest.mark.parametrize("history", [False, True])
async def test_closed_symptom_actual_pi_persists_once_without_model(
    db, client, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch,
    message, history,
):
    from app.config import settings
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.symptom_entry import SymptomEntry
    from app.models.user import User

    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(settings, "decision_mode", "on")

    async def unexpected_route(*args, **kwargs):
        raise AssertionError("closed nasal writes need no advisory route")

    monkeypatch.setattr("app.services.decisions.routing.decide_route", unexpected_route)
    user, headers = auth_user_and_headers
    other = User(username="symptom_other", email="symptom_other@example.invalid", name="Other")
    db.add(other)
    db.flush()
    old = SymptomEntry(user_id=other.id, body_part="head", description="合成旧症状")
    db.add(old)
    conversation_id = None
    if history:
        conv = AgentConversation(user_id=user.id, title="合成上下文")
        db.add(conv)
        db.flush()
        conversation_id = conv.id
        db.add_all([
            AgentMessage(conversation_id=conv.id, role="user", content="更正：昨天是鼻塞，没有流鼻涕。"),
            AgentMessage(conversation_id=conv.id, role="assistant", content="请确认是否更正昨天的症状。"),
        ])
    db.commit()
    ex = ae.AgentExecutor(db)
    calls = []
    posts = []

    async def model(messages, tools):
        calls.append(True)
        yield {"type": "content", "text": "本次未记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def post(url, request_headers, payload):
        assert url.endswith("/symptoms")
        posts.append(payload)
        response = client.post("/api/v1/symptoms", headers=headers, json=payload)
        assert response.status_code == 201
        return json.dumps(response.json(), ensure_ascii=False)

    monkeypatch.setattr(ex, "_call_llm_stream", model)
    monkeypatch.setattr(ex, "_api_post", post)
    events = [e async for e in ex.run_stream(
        user.id, message, conversation_id=conversation_id, channel="typed",
        user_auth_token=headers["Authorization"].split(" ", 1)[1],
        client_turn_id="synthetic-closed-symptom",
    )]
    done = next(e["data"] for e in events if e.get("event") == "done")
    rows = db.query(SymptomEntry).filter_by(user_id=user.id).all()
    assert len(rows) == len(posts) == 1
    assert rows[0].description == message
    assert rows[0].body_part == "respiratory" and rows[0].severity is None
    db.refresh(old)
    assert old.description == "合成旧症状"
    assert db.query(SymptomEntry).filter_by(user_id=other.id).count() == 1
    assert len(done["write_receipts"]) == 1 and done["write_receipts"][0]["verified"] is True
    reply = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")
    saved = db.get(AgentMessage, done["message_id"])
    symptom = next(word for word in ("流鼻涕", "鼻塞", "打喷嚏") if word in message)
    assert symptom in reply and saved.content == reply
    assert done["turn_outcome"]["status"] == "complete"
    assert not calls
    replay = [e async for e in ex.run_stream(
        user.id, message, conversation_id=done["conversation_id"], channel="typed",
        user_auth_token=headers["Authorization"].split(" ", 1)[1],
        client_turn_id="synthetic-closed-symptom",
    )]
    assert any(e.get("event") == "done" for e in replay)
    assert len(posts) == 1 and not calls
    assert db.query(SymptomEntry).filter_by(user_id=user.id).count() == 1


@pytest.mark.parametrize("boundary", [
    "disabled", "voice", "read_only", "runtime_block", "extra_context", "clinical", "attachment", "tier_failure",
])
async def test_nasal_preplan_respects_existing_turn_gates(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, boundary,
):
    from app.config import settings
    monkeypatch.setattr(settings, "domain_prompt_optimization", boundary != "disabled")
    if boundary == "tier_failure":
        def unavailable_tier(*args, **kwargs):
            raise RuntimeError("synthetic classification unavailable")
        monkeypatch.setattr("app.services.llm.task_routing.classify_answer_task_tier", unavailable_tier)
    user, headers = auth_user_and_headers
    ex = ae.AgentExecutor(db)
    calls, posts = [], []

    async def model(messages, tools):
        calls.append(True)
        yield {"type": "content", "text": "本次未记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def post(*args):
        posts.append(True)
        return "Error: synthetic unavailable"

    monkeypatch.setattr(ex, "_call_llm_stream", model)
    monkeypatch.setattr(ex, "_api_post", post)
    if boundary == "tier_failure":
        # The existing earlier classifier propagates this failure; it must not
        # silently fall through into the deterministic write path.
        with pytest.raises(RuntimeError, match="synthetic classification unavailable"):
            _ = [e async for e in ex.run_stream(user.id, "记录流鼻涕症状", channel="typed")]
        assert not posts and not calls
        return
    events = [e async for e in ex.run_stream(
        user.id, "记录流鼻涕症状" + ("，需要就医吗" if boundary == "clinical" else ""),
        channel="voice" if boundary == "voice" else "typed",
        user_auth_token=headers["Authorization"].split(" ", 1)[1],
        read_only_tools=boundary == "read_only",
        runtime_write_block_reason="synthetic_block" if boundary == "runtime_block" else None,
        extra_context="合成附加上下文" if boundary == "extra_context" else None,
        file_base64="c3ludGhldGlj" if boundary == "attachment" else None,
        file_name="synthetic.txt" if boundary == "attachment" else None,
    )]
    done = next(e["data"] for e in events if e.get("event") == "done")
    assert "nasal_symptom_record_preplanned" not in done.get("fallback_reasons", [])
    assert not done.get("write_receipts")
    if boundary in {"read_only", "runtime_block"}:
        assert not posts
    else:
        assert calls


@pytest.mark.parametrize("response", ["Error: synthetic unavailable", "{}"])
async def test_nasal_preplan_never_claims_success_without_verified_receipt(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, response,
):
    from app.config import settings
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    user, headers = auth_user_and_headers
    ex = ae.AgentExecutor(db)
    posts = []

    async def model(messages, tools):
        yield {"type": "content", "text": "已记录。"}
        yield {"type": "finish", "finish_reason": "stop"}

    async def post(*args):
        posts.append(True)
        return response

    monkeypatch.setattr(ex, "_call_llm_stream", model)
    monkeypatch.setattr(ex, "_api_post", post)
    events = [e async for e in ex.run_stream(
        user.id, "记录流鼻涕症状", channel="typed",
        user_auth_token=headers["Authorization"].split(" ", 1)[1],
    )]
    done = next(e["data"] for e in events if e.get("event") == "done")
    reply = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")
    assert len(posts) == 1
    assert not done.get("write_receipts")
    assert done["turn_outcome"]["status"] != "complete"
    assert "已记录" not in reply
