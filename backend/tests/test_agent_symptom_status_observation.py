"""Closed, synthetic self-report grammar; parser proof is not a write receipt."""
import pytest

from app.services.utterance_intent_classifier import classify_agent_utterance, has_retracted_symptom_write


REQUEST = "记录下来，我的头痛已经消失了。目前一切正常，除了偶尔有点鼻塞之外。"


def parse(text):
    from app.services.agent_symptom_status_observation import parse_symptom_status_observation
    return parse_symptom_status_observation(text)


@pytest.mark.parametrize("text", [REQUEST, "请记录，我的头痛已经消失了。",
    "帮我记录一下，我的眼睛发痒已经消失了，但偶尔还有轻微鼻塞。",
    "记录下来，我的鼻塞已经恢复正常了。", "记录一下，我的头疼好了，目前一切正常。"])
def test_explicit_self_status_preserves_entire_observation_without_inference(text):
    assert parse(text) == {"body_part": "general", "description": text}
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.operation, intent.is_write) == ("write", "symptom", "create", True)
    assert not has_retracted_symptom_write(text)


@pytest.mark.parametrize("text", [
    "我的头痛已经消失了。", "记录下来，头痛已经消失了。",
    "记录下来，我妈妈的头痛已经消失了。", "记录下来，他的头痛已经消失了。",
    '他说："记录下来，我的头痛已经消失了。"', '“记录下来，我的头痛已经消失了。”',
    "请分析这段话：记录下来，我的头痛已经消失了。",
    REQUEST + "不要记录。", "别" + REQUEST, REQUEST + "取消刚才的记录请求。",
    REQUEST + "并且把病程标记为痊愈。", REQUEST + "帮我停药。",
    REQUEST + "明天提醒我。", REQUEST + "需要看医生吗？", REQUEST + "[额外内容]",
    "记录下来，我的头痛可能已经消失了。", "记录下来，我的头痛没有消失。",
    "记录下来，我的感冒已经痊愈了。", "记录下来，我的头痛已经消失了，删除旧记录。",
    "记录下来，我的头痛已经消失了，昨天一切正常。",
    "记录下来，我的头痛已经消失了，目前一切正常，除了他的鼻塞之外。",
    "记录下来，我的头痛已经消失了？", "记录下来，我的头痛已经消失了\u200b。",
])
def test_unknown_tail_reference_or_revocation_never_gets_exact_proof(text):
    assert parse(text) is None


def test_other_retracted_symptom_rules_are_not_relaxed():
    assert has_retracted_symptom_write("记录我头痛，说错了，撤回这条记录。")


def test_whitespace_preserved_and_oversized_text_rejected_without_clipping():
    text = "记录下来， 我的头痛已经消失了。"
    assert parse(text)["description"] == text
    assert parse(" " * 500 + REQUEST) is None


@pytest.mark.parametrize("suffix", ["不要记录", "取消记录", "给我开药", "更新病程", "\n", "？"])
def test_exact_proof_does_not_ignore_appended_material(suffix):
    assert parse(REQUEST + suffix) is None


COUNT_REQUEST = "记录下来，我的头痛状况已经消失了。目前一切正常，除了偶尔打三次喷嚏之外。"


def test_status_count_is_preserved_as_text_not_rhinitis_quantification():
    from app.services.agent_executor import (
        _extract_clear_symptom_record, _extract_clear_rhinitis_record,
        _is_proven_pure_symptom_record_request, _apply_authorized_symptom_payload,
    )
    assert parse(COUNT_REQUEST) == {"body_part": "general", "description": COUNT_REQUEST}
    assert _extract_clear_symptom_record(COUNT_REQUEST) == parse(COUNT_REQUEST)
    assert _is_proven_pure_symptom_record_request(COUNT_REQUEST)
    assert _extract_clear_rhinitis_record(COUNT_REQUEST) is None
    args = {"record_type": "symptom", "data": {"description": "模型截断", "severity": 8,
        "date": "2020-01-01", "diagnosis": "模型推断", "body_part": "respiratory"}}
    applied = _apply_authorized_symptom_payload(args, parse(COUNT_REQUEST))
    assert applied == {"record_type": "symptom", "data": parse(COUNT_REQUEST)}


@pytest.mark.asyncio
@pytest.mark.parametrize("message,expected_write", [
    (REQUEST, True), (COUNT_REQUEST, True),
    (REQUEST + "不要记录。", False),
    (REQUEST.replace("我的头痛", "我妈妈的头痛"), False),
    ('他说："' + REQUEST + '"', False),
    (COUNT_REQUEST + "删除旧病程。", False),
])
async def test_stream_persists_exact_status_without_illness_mutation(
    db, client, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, message, expected_write,
):
    import json
    from datetime import date, datetime, timezone
    from app.services.agent_executor import AgentExecutor
    from app.models.symptom_entry import SymptomEntry
    from app.models.illness import IllnessEpisode, IllnessUpdate
    from app.twin.schema import HealthTwin, TwinMeta

    user, headers = auth_user_and_headers
    episode = IllnessEpisode(user_id=user.id, name="合成观察基线", start_date=date.today(), status="active")
    db.add(episode)
    db.commit()
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, user_id, **kw:
        HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc))))
    executor = AgentExecutor(db)
    posted = []
    calls = 0

    async def fake_llm(messages, tools):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"content": "", "finish_reason": "tool_calls", "tool_calls": [{
                "id": "synthetic-status-observation", "type": "function", "function": {
                    "name": "health_record", "arguments": json.dumps({"record_type": "symptom",
                        "data": {"body_part": "respiratory", "description": "模型截断",
                                 "severity": 8, "notes": "模型推断"}}, ensure_ascii=False),
                }}]}
        return {"content": "已记录本次自述。", "finish_reason": "stop"}

    async def fake_stream(messages, tools):
        response = await fake_llm(messages, tools)
        if response.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": response["tool_calls"]}
        if response.get("content"):
            yield {"type": "content", "text": response["content"]}
        yield {"type": "finish", "finish_reason": response["finish_reason"]}

    async def api_post(url, request_headers, payload):
        assert url.endswith("/symptoms")
        posted.append(dict(payload))
        response = client.post("/api/v1/symptoms", headers=headers, json=payload)
        assert response.status_code == 201, response.text
        return json.dumps(response.json(), ensure_ascii=False)

    monkeypatch.setattr(executor, "_call_llm", fake_llm)
    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)
    monkeypatch.setattr(executor, "_api_post", api_post)
    events = [event async for event in executor.run_stream(
        user_id=user.id, message=message, user_auth_token=headers["Authorization"].split(" ", 1)[1],
        channel="typed",
    )]
    rows = db.query(SymptomEntry).filter_by(user_id=user.id).all()
    done = next(event["data"] for event in events if event.get("event") == "done")
    if not expected_write:
        assert rows == []
        assert posted == []
        assert done["write_receipts"] == []
        db.refresh(episode)
        assert episode.status == "active" and episode.end_date is None
        assert db.query(IllnessUpdate).filter_by(user_id=user.id).count() == 0
        return
    assert len(rows) == 1
    assert rows[0].description == message
    assert rows[0].body_part == "general"
    assert rows[0].severity is None
    assert rows[0].notes is None
    assert len(posted) == 1
    assert "severity" not in posted[0]
    assert "diagnosis" not in posted[0]
    db.refresh(episode)
    assert episode.status == "active" and episode.end_date is None
    assert db.query(IllnessEpisode).filter_by(user_id=user.id).count() == 1
    assert db.query(IllnessUpdate).filter_by(user_id=user.id).count() == 0
    assert len(done["write_receipts"]) == 1
    assert done["write_receipts"][0]["verified"] is True
    assert done["turn_outcome"]["category"] == "success"
