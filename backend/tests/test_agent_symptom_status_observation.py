"""Closed, synthetic self-report grammar; parser proof is not a write receipt."""
import pytest

from app.services.utterance_intent_classifier import classify_agent_utterance, has_retracted_symptom_write


REQUEST = "记录下来，我的头痛已经消失了。目前一切正常，除了偶尔有点鼻塞之外。"
DIARRHEA_REQUEST = "记录下来，稍微有点拉肚子，跟昨天晚上吃海鲜有一定的关系。"
APPROX_REQUEST = "记录下来，我的感冒症状已经消失了。目前一切正常，除了偶尔打三四个喷嚏之外。"
ONGOING_PAIN_REQUEST = "下午仍然隐隐肚子痛"


@pytest.mark.parametrize("text", [
    ONGOING_PAIN_REQUEST, "我下午仍然隐隐肚子痛", "今天下午仍然隐隐肚子痛。",
    "下午我仍然隐隐肚子痛", "现在还是隐隐约约腹痛", "记录一下，我目前还有点胃痛。",
])
def test_current_abdominal_pain_is_exact_observation_not_illness_update(text):
    from app.services.agent_executor import _extract_clear_symptom_record, _apply_authorized_symptom_payload
    assert parse(text) == {"body_part": "digestive", "description": text}
    assert _extract_clear_symptom_record(text) == parse(text)
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.operation) == ("write", "symptom", "create")
    assert _apply_authorized_symptom_payload({"record_type": "symptom", "data": {
        "severity": 8, "occurred_at": "2020-01-01T15:00:00Z", "user_id": 999,
        "diagnosis": "模型推断", "description": "模型改写",
    }}, parse(text)) == {"record_type": "symptom", "data": parse(text)}


@pytest.mark.parametrize("text", [
    "妈妈下午仍然隐隐肚子痛", "我朋友下午仍然隐隐肚子痛", "下午他仍然隐隐肚子痛",
    "如果下午仍然隐隐肚子痛", "明天下午仍然隐隐肚子痛", "昨天下午仍然隐隐肚子痛",
    "下午没有肚子痛", "下午不再肚子痛", "下午可能仍然隐隐肚子痛",
    "下午仍然隐隐肚子痛？", "下午仍然隐隐肚子痛怎么办", "下午仍然隐隐肚子痛，需要就医吗？",
    "他说：下午仍然隐隐肚子痛", "“下午仍然隐隐肚子痛”", "翻译：下午仍然隐隐肚子痛",
    ONGOING_PAIN_REQUEST + "，不要记录", ONGOING_PAIN_REQUEST + "，不是我，是妈妈",
    ONGOING_PAIN_REQUEST + "，更新病程", ONGOING_PAIN_REQUEST + "，删除饮食记录",
    ONGOING_PAIN_REQUEST + "，诊断为胃炎", ONGOING_PAIN_REQUEST + "\u200b",
])
def test_current_pain_proof_rejects_unknown_owner_time_and_tail(text):
    assert parse(text) is None


def parse(text):
    from app.services.agent_symptom_status_observation import parse_symptom_status_observation
    return parse_symptom_status_observation(text)


@pytest.mark.parametrize("text", [REQUEST, APPROX_REQUEST, "请记录，我的头痛已经消失了。",
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


def test_approximate_count_grammar_is_adjacent_and_never_numeric_severity():
    import re
    from app.services.agent_symptom_status_observation import _SNEEZE_COUNT
    assert re.fullmatch(_SNEEZE_COUNT, "一两")
    assert re.fullmatch(_SNEEZE_COUNT, "三四")
    assert not re.fullmatch(_SNEEZE_COUNT, "三六")
    assert not re.fullmatch(_SNEEZE_COUNT, "3;停药")


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
        _build_deterministic_symptom_tool_call,
    )
    assert parse(COUNT_REQUEST) == {"body_part": "general", "description": COUNT_REQUEST}
    assert _extract_clear_symptom_record(COUNT_REQUEST) == parse(COUNT_REQUEST)
    assert _is_proven_pure_symptom_record_request(COUNT_REQUEST)
    assert _extract_clear_rhinitis_record(COUNT_REQUEST) is None
    args = {"record_type": "symptom", "data": {"description": "模型截断", "severity": 8,
        "date": "2020-01-01", "diagnosis": "模型推断", "body_part": "respiratory"}}
    applied = _apply_authorized_symptom_payload(args, parse(COUNT_REQUEST))
    assert applied == {"record_type": "symptom", "data": parse(COUNT_REQUEST)}
    assert _build_deterministic_symptom_tool_call(COUNT_REQUEST, write_receipts=[], has_attachment=True) is None
    assert _build_deterministic_symptom_tool_call(COUNT_REQUEST, write_receipts=[{"verified": True}]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("model_behavior", ["symptom_tool", "no_tool", "wrong_tool"])
@pytest.mark.parametrize("message,expected_write,read_only", [
    ("后脑勺疼", True, False),
    ("做后脑勺疼", True, False),
    ("后脑勺疼", False, True),
    (ONGOING_PAIN_REQUEST, True, False),
    (ONGOING_PAIN_REQUEST, False, True),
    ("妈妈" + ONGOING_PAIN_REQUEST, False, False),
    (ONGOING_PAIN_REQUEST + "，不要记录", False, False),
    (DIARRHEA_REQUEST, True, False),
    (DIARRHEA_REQUEST.replace("稍微有点", "我妈妈稍微有点"), False, False),
    (DIARRHEA_REQUEST.replace("稍微有点", "没有"), False, False),
    ('“' + DIARRHEA_REQUEST + '”', False, False),
    (DIARRHEA_REQUEST + "不要记录。", False, False),
    (DIARRHEA_REQUEST, False, True), (REQUEST, True, False), (COUNT_REQUEST, True, False), (APPROX_REQUEST, True, False),
    (REQUEST + "不要记录。", False, False),
    (REQUEST.replace("我的头痛", "我妈妈的头痛"), False, False),
    ('他说："' + REQUEST + '"', False, False),
    (COUNT_REQUEST + "删除旧病程。", False, False),
    (REQUEST, False, True),
])
async def test_stream_persists_exact_status_without_illness_mutation(
    db, client, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, message, expected_write, model_behavior, read_only,
):
    import json
    from datetime import date, datetime, timezone
    from app.services.agent_executor import AgentExecutor
    from app.models.symptom_entry import SymptomEntry
    from app.models.daily_health import DietRecord
    from app.models.illness import IllnessEpisode, IllnessUpdate
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.models.user import User
    from app.twin.schema import HealthTwin, TwinMeta

    user, headers = auth_user_and_headers
    episode = IllnessEpisode(user_id=user.id, name="合成观察基线", start_date=date.today(), status="active")
    db.add(episode)
    historical_meal = DietRecord(user_id=user.id, record_date=date(2026, 1, 1), meal_type="晚餐", food_items="合成海鲜", calories=123)
    db.add(historical_meal)
    db.commit()
    conversation_id = None
    protected_symptoms = []
    if ONGOING_PAIN_REQUEST in message:
        other = User(username="pain-other", email="pain-other@example.test", name="Synthetic other", hashed_password="synthetic",
                     is_active=True, is_approved=True)
        db.add(other)
        db.flush()
        protected_symptoms = [SymptomEntry(user_id=owner, body_part="digestive", description="合成旧症状")
                              for owner in (user.id, other.id)]
        db.add_all(protected_symptoms)
        conversation = AgentConversation(user_id=user.id, title="合成饮食上下文")
        db.add(conversation)
        db.flush()
        conversation_id = conversation.id
        db.add_all([
            AgentMessage(conversation_id=conversation_id, role="user", content="记录午餐米饭"),
            AgentMessage(conversation_id=conversation_id, role="assistant", content="这餐尚未完成，可继续修正本餐。"),
        ])
        db.commit()
    monkeypatch.setattr("app.twin.builder.build_twin", lambda _db, user_id, **kw:
        HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.now(timezone.utc))))
    executor = AgentExecutor(db)
    posted = []
    calls = 0

    async def fake_llm(messages, tools):
        nonlocal calls
        calls += 1
        if model_behavior == "no_tool":
            return {"content": "本次记录尚未完成。", "finish_reason": "stop"}
        if calls == 1:
            return {"content": "", "finish_reason": "tool_calls", "tool_calls": [{
                "id": "synthetic-status-observation", "type": "function", "function": {
                    "name": "health_record", "arguments": json.dumps({"record_type": "rhinitis" if model_behavior == "wrong_tool" else "symptom",
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
        channel="typed", read_only_tools=read_only, conversation_id=conversation_id,
    )]
    protected_ids = {row.id for row in protected_symptoms}
    rows = [row for row in db.query(SymptomEntry).filter_by(user_id=user.id).all() if row.id not in protected_ids]
    for row in protected_symptoms:
        db.refresh(row)
        assert row.description == "合成旧症状" and row.severity is None
    assert db.query(SymptomEntry).count() == len(protected_symptoms) + len(rows)
    db.refresh(historical_meal)
    assert historical_meal.food_items == "合成海鲜" and historical_meal.calories == 123
    assert db.query(DietRecord).filter_by(user_id=user.id).count() == 1
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
    assert rows[0].body_part == (
        "head" if message in {"后脑勺疼", "做后脑勺疼"}
        else "digestive" if message == ONGOING_PAIN_REQUEST else "general"
    )
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
    assert "symptom_status_observation_preplanned" in done["fallback_reasons"]
    assert calls == 0


@pytest.mark.parametrize("text", [DIARRHEA_REQUEST, "记录一下，我现在有点腹泻，可能跟昨晚吃海鲜有关。"])
def test_self_diarrhea_with_user_suspected_food_context_is_symptom_not_meal(text):
    assert parse(text) == {"body_part": "general", "description": text}
    intent = classify_agent_utterance(text)
    assert (intent.primary, intent.domain, intent.operation) == ("write", "symptom", "create")


@pytest.mark.parametrize("text", [
    DIARRHEA_REQUEST.replace("稍微有点", "我妈妈稍微有点"),
    DIARRHEA_REQUEST.replace("稍微有点", "没有"),
    '“' + DIARRHEA_REQUEST + '”',
    "他说：" + DIARRHEA_REQUEST,
    DIARRHEA_REQUEST + "不要记录。",
    DIARRHEA_REQUEST + "顺便记录昨天晚餐。",
    DIARRHEA_REQUEST + "确诊食物中毒。",
    DIARRHEA_REQUEST.replace("稍微有点", "昨天稍微有点"),
    DIARRHEA_REQUEST.replace("跟昨天晚上吃海鲜有一定的关系", "跟妈妈昨天晚上吃海鲜有一定的关系"),
])
def test_diarrhea_context_never_proves_foreign_negated_or_extra_action(text):
    assert parse(text) is None


def test_diarrhea_food_association_never_compiles_a_diet_preplan():
    from app.services.agent_kernel.goal_spec import compile_goal_spec
    from app.services.agent_kernel.intent_frame import build_intent_frame
    from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext
    from app.services.agent_executor import _build_preplanned_simple_diet_tool_call
    context = ExecutionContext.for_test(user_id=17, channel="mobile")
    envelope = AgentEnvelope(user_id=17, channel="mobile", text=DIARRHEA_REQUEST)
    goal = compile_goal_spec(envelope=envelope, context=context, intent=build_intent_frame(envelope, context))
    assert goal is None or goal.domain != "diet"
    assert _build_preplanned_simple_diet_tool_call(goal, write_receipts=[]) is None

@pytest.mark.parametrize('food', ['牛奶', '烧烤', '辣椒'])
def test_other_suspected_food_is_not_a_diet_write_or_exact_symptom_proof(food):
    text = DIARRHEA_REQUEST.replace('海鲜', food)
    assert parse(text) is None
    intent = classify_agent_utterance(text)
    assert intent.domain == 'symptom'


def test_leading_meal_command_is_not_reclassified_by_later_symptom():
    assert classify_agent_utterance('记录午餐吃了米饭，另外有点腹泻。').domain == 'diet'

@pytest.mark.parametrize('text', ['拉肚子怎么办', '腹泻吃什么', '我妈妈拉肚子怎么办', '他说腹泻吃什么'])
def test_digestive_advice_never_authorizes_observation(text):
    assert not classify_agent_utterance(text).is_write
    assert parse(text) is None

@pytest.mark.parametrize('text', [
    '后脑勺疼', '左后脑勺疼', '做后脑勺疼', '我现在后脑勺疼。',
    '我的后脑勺疼', '右侧后脑勺痛', '记录一下，我的后脑勺疼。',
])
def test_current_posterior_head_pain_preserves_literal_user_description(text):
    from app.services.agent_executor import _extract_clear_symptom_record, _apply_authorized_symptom_payload
    expected = {'body_part': 'head', 'description': text}
    assert parse(text) == expected
    assert _extract_clear_symptom_record(text) == expected
    assert _apply_authorized_symptom_payload({'record_type': 'symptom', 'data': {'severity': 9, 'diagnosis': 'inferred'}}, expected) == {'record_type': 'symptom', 'data': expected}

@pytest.mark.parametrize('text', ['妈妈后脑勺疼', '明天后脑勺疼', '后脑勺不疼', '后脑勺疼怎么办', '后脑勺疼？', '他说后脑勺疼', '后脑勺疼，别记录', '后脑勺疼，替我停药', '现在好了'])
def test_posterior_head_pain_does_not_infer_owner_actions_or_resolution(text):
    assert parse(text) is None
