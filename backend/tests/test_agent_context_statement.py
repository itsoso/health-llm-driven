"""Synthetic travel statements: same intent, no health authority, durable reply."""
import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_conversation_service import AgentConversationService
from app.services.agent_executor import AgentExecutor
from app.services.utterance_intent_classifier import classify_agent_utterance
from tests.conftest import create_authenticated_user


STATEMENTS = [
    "落地成都", "我刚落地上海了。", "我已经抵达杭州市", "今天到北京了",
    "我在成都出差", "今天住在成都示例酒店。", "我已入住示例酒店",
    "成都示例天府酒店 是我今天差旅居住地。",
    "我今天的差旅住处是成都示例酒店。",
]


@pytest.mark.parametrize("message", STATEMENTS)
def test_context_statement_has_one_shared_nonwriting_intent(message):
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.operation) == ("chat", "context", "none")
    assert intent.reason == ("context_statement_candidate" if "酒店" in message else "context_statement")
    assert not intent.is_write


@pytest.mark.parametrize("message", [
    "落地成都胸痛", "落地成都，喘不上气", "我落地成都后头晕怎么办",
    "我刚落地成都需要吃药吗", "今天住在胸闷酒店", "落地成都心慌",
    "落地成都。每天两片可以吗", "成都酒店是我今天差旅居住地，帮我查昨晚睡眠",
    "成都酒店是我今天差旅居住地，记录午餐", "记录落地成都",
    "帮我记住今天住成都酒店", "修改常住地址为成都", "明天落地成都",
    "如果落地成都", "我还没到成都", "我不是在成都出差", "朋友落地成都",
    "他说我已入住示例酒店", "翻译：落地成都", "“落地成都”", "落地成都？",
    "落地成都同步佳明", "今天住在示例酒店请停用鱼油", "落地成都删除记录",
    "我今天的差旅住处是成都示例酒店，昨晚没睡好", "落地成都\n胸痛",
    "落地成都咯血", "落地成都低烧", "落地成都拉肚子", "落地成都失眠",
    "落地成都浑身乏力", "落地成都记下行程", "到成都之前住上海酒店",
    "需要，我住在示例酒店", "我住在示例酒店，查一下天气",
    "我住在示例酒店，16:30提醒我出门", "我住在示例酒店，突然胸痛",
    "落地未知示例城市", "我在成都咯血出差",
    "到北京", "我到北京", "今天到北京",
])
def test_compound_clinical_quoted_and_write_inputs_are_not_acknowledgements(message):
    from app.services.agent_context_statement import parse_context_statement
    assert parse_context_statement(message) is None
    assert classify_agent_utterance(message).reason != "context_statement"


def _no_heavy_work(executor, monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("A plain context acknowledgement must not load health data or call a model/tool")
    for name in ("_build_system_prompt", "_build_system_knowledge_prompt_context", "_call_llm", "_call_llm_stream", "_execute_tool"):
        monkeypatch.setattr(executor, name, unexpected)


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["typed", "mobile", "mac"])
async def test_real_stream_after_meal_keeps_context_and_completes_without_model(db, auth_user_and_headers, monkeypatch, channel):
    user, _ = auth_user_and_headers
    service = AgentConversationService(db)
    conv = service.get_or_create_conversation(user.id, None, title="合成差旅场景")
    service.save_message(conv.id, "user", "记录午餐")
    service.save_message(conv.id, "assistant", "午餐记录已保存。")
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    for index, message in enumerate(("落地成都", "我在成都出差")):
        events = [e async for e in executor.run_stream(user_id=user.id, message=message,
            conversation_id=conv.id, channel=channel, client_turn_id=f"context-{channel}-{index}")]
        done = next(e["data"] for e in events if e.get("event") == "done")
        assert done["completion_status"] == "complete"
        assert done["turn_outcome"]["status"] == "complete"
        assert done["route"] == "context_statement"
        assert done["model_call_count"] == 0
        assert done["turn_outcome"]["verified_receipt_count"] == 0
        saved = db.get(AgentMessage, done["message_id"])
        streamed = "".join(e["data"]["content"] for e in events if e.get("event") == "token")
        assert streamed == saved.content
        assert "成都" in streamed
        assert not any(word in streamed for word in ("医生", "药师", "信息来源", "执行方案", "已记录", "已保存"))
        assert not any(e.get("event") in ("tool_result", "tool_call") for e in events)
    history = service.build_messages(conv.id)
    assert any(m["role"] == "user" and "成都出差" in m["content"] for m in history)


@pytest.mark.asyncio
async def test_context_replay_is_idempotent_and_user_scoped(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    async def send(**kwargs):
        return [e async for e in executor.run_stream(user_id=user.id, message="落地成都",
            channel="typed", client_turn_id="synthetic-context-replay", **kwargs)]
    first = await send()
    first_done = next(e["data"] for e in first if e.get("event") == "done")
    second = await send(conversation_id=first_done["conversation_id"])
    second_done = next(e["data"] for e in second if e.get("event") == "done")
    assert second_done["message_id"] == first_done["message_id"]
    assert db.query(AgentMessage).filter(AgentMessage.conversation_id == first_done["conversation_id"]).count() == 2
    other, _ = create_authenticated_user(db)
    foreign = AgentExecutor(db)
    _no_heavy_work(foreign, monkeypatch)
    with pytest.raises(ValueError, match="对话不存在"):
        _ = [e async for e in foreign.run_stream(user_id=other.id, message="落地成都",
            conversation_id=first_done["conversation_id"], channel="typed")]


@pytest.mark.asyncio
@pytest.mark.parametrize("original,attachment", [
    ("落地成都\n[附图: 1张]", "synthetic-medical-image.jpg"),
    ("落地成都咯血", None),
    ("落地成都", None),
])
async def test_unfinished_source_turn_cannot_be_completed_from_replacement_caption(db, auth_user_and_headers, monkeypatch, original, attachment):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成源回合恢复")
    source, _ = svc.save_user_message_once(conv.id, user.id, original,
        client_turn_id="synthetic-recovered-context")
    source.image_url = attachment
    db.commit()
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["recovered_user_message"].id)
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    events = [e async for e in executor.run_stream(user_id=user.id, message="落地成都",
        conversation_id=conv.id, client_turn_id="synthetic-recovered-context")]
    assert calls == [source.id]
    assert not any(e.get("data", {}).get("route") == "context_statement" for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("prior", [
    "胸痛，喘不上气", "我想核对鱼油剂量", "我昨晚腰痛，腿麻", "我想自杀",
    "咯血了", "腿麻走不了", "我有抑郁症", "我好像中风了", "我正在流血", "我拉肚子三天了",
])
async def test_recent_medical_context_must_not_be_short_circuited(db, auth_user_and_headers, monkeypatch, prior):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成安全续问")
    svc.save_message(conv.id, "user", prior)
    svc.save_message(conv.id, "assistant", "你现在在哪里？")
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message="落地成都", conversation_id=conv.id)]
    assert calls == ["落地成都"]


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "落地成都咯血", "落地成都低烧", "落地成都拉肚子", "落地成都失眠",
    "落地成都浑身乏力", "落地成都记下行程", "到成都之前住上海酒店",
    "需要，我住在示例酒店", "我住在示例酒店，查一下天气",
    "我住在示例酒店，16:30提醒我出门", "我住在示例酒店，突然胸痛",
])
async def test_extra_semantics_reach_ordinary_stream(db, auth_user_and_headers, monkeypatch, message):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message=message)]
    assert calls == [message]


@pytest.mark.asyncio
@pytest.mark.parametrize("prior,answer", [
    ("咯血了", "收到，先确认目前环境。"),
    ("帮我安排一下", "你在哪里？"),
    ("落地成都", "请补充你入住的酒店。"),
    ("落地成都", "说一下你的位置"),
    ("落地成都", "你在哪"),
    ("落地成都", "烦请告知当前所在城市。"),
    ("落地成都", "麻烦报一下当前位置。"),
    ("落地成都", "描述目前所处的位置"),
    ("落地成都", "下一步需要结合当前环境判断。"),
])
async def test_unknown_history_or_open_question_retains_continuation(db, auth_user_and_headers, monkeypatch, prior, answer):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成未完成续问")
    svc.save_message(conv.id, "user", prior)
    svc.save_message(conv.id, "assistant", answer)
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message="落地成都", conversation_id=conv.id)]
    assert calls == ["落地成都"]


@pytest.mark.asyncio
@pytest.mark.parametrize("prior", ["落地成都", "记录午餐"])
async def test_recent_attachment_keeps_nontext_obligations(db, auth_user_and_headers, monkeypatch, prior):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成图像续问")
    # Avoid opening/decoding any image: the attachment presence alone must
    # retain the ordinary evidence-aware pipeline, regardless of its caption.
    db.add(AgentMessage(conversation_id=conv.id, role="user", content=prior,
                        image_url="synthetic-medical-image.jpg"))
    db.commit()
    svc.save_message(conv.id, "assistant", "图片中有需要处理的信息。", meta={})
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message="我在成都出差", conversation_id=conv.id)]
    assert calls == ["我在成都出差"]


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"images": [{"base64": "synthetic"}]}, {"extra_context": '{"multi_model":true}'}, {"file_base64": "synthetic"}])
async def test_context_caption_cannot_consume_attachment_or_entry_task(db, auth_user_and_headers, monkeypatch, extra):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs)
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message="落地成都", **extra)]
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("prefix", [
    "",
    "信息来源：用户陈述、模型推断。\n",
    "信息来源：用户陈述、已检索证据（未逐句核验）、模型推断。\n",
    "信息来源：上下文信息（未逐项核验）、模型推断。\n",
    "信息来源：上下文信息（未逐项核验）、已检索证据（未逐句核验）、模型推断。\n",
])
async def test_previous_offtopic_medical_refusal_is_not_user_medical_context(db, auth_user_and_headers, monkeypatch, prefix):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成偏题恢复")
    svc.save_message(conv.id, "user", "落地成都")
    from app.services.guidance_validator import _ADVICE_HOLD
    svc.save_message(conv.id, "assistant", prefix + _ADVICE_HOLD)
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    events = [e async for e in executor.run_stream(user_id=user.id,
        message="我在成都出差", conversation_id=conv.id)]
    done = next(e["data"] for e in events if e.get("event") == "done")
    assert done["route"] == "context_statement"


@pytest.mark.asyncio
@pytest.mark.parametrize("message", [
    "成都示例天府酒店是我今天差旅居住地。", "今天住在成都咯血酒店",
    "我已入住示例酒店", "我今天的差旅住处是成都记下行程酒店",
])
async def test_unverified_hotel_name_cannot_bypass_normal_safety_pipeline(db, auth_user_and_headers, monkeypatch, message):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message=message)]
    assert calls == [message]


def test_system_prompt_scopes_initiative_without_disabling_medical_rules(db):
    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=0, conv_id=0, user_auth_token=None, lite=True,
        intent_query="成都示例天府酒店是我今天差旅居住地。", static_rules_only=True,
    )
    assert "## 本轮任务边界" in prompt
    assert "普通抵达、出差、入住" in prompt
    assert "不能仅因出现城市或酒店就忽略" in prompt
    assert "不得用“已记录”或“已保存”代替“收到”" in prompt
    assert "不做诊断" in prompt


def test_system_prompt_does_not_expand_ambiguous_travel_followup(db):
    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=0, conv_id=0, user_auth_token=None, lite=True,
        intent_query="需要，我住在示例清河酒店", static_rules_only=True,
    )
    assert "多项可选动作" in prompt
    assert "不得把含糊同意解释为全部授权" in prompt
    assert "不主动查询天气或空气质量" in prompt
    assert "不复述内部写入接口或失败细节" in prompt
    assert "真实新发安全风险" in prompt
    assert "仅在上述含糊同意场景" in prompt
    assert "用户明确选中某项时继续该项" in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("meta", [
    {"pending_choice": {"status": "pending"}},
    {"turn_outcome": {"status": "waiting_for_user", "confirmation_required": True}},
    {"turn_outcome": {"status": "reconciliation_required"}},
])
async def test_unresolved_action_retains_ordinary_continuation(db, auth_user_and_headers, monkeypatch, meta):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title="合成待确认事项")
    svc.save_message(conv.id, "user", "记录行程")
    svc.save_message(conv.id, "assistant", "请补充地点。", meta=meta)
    executor = AgentExecutor(db)
    calls = []
    async def ordinary(**kwargs):
        calls.append(kwargs["message"])
        yield {"event": "done", "data": {"completion_status": "complete"}}
    monkeypatch.setattr(executor, "_run_stream_impl", ordinary)
    _ = [e async for e in executor.run_stream(user_id=user.id, message="落地成都", conversation_id=conv.id)]
    assert calls == ["落地成都"]


@pytest.mark.asyncio
async def test_failed_persistence_never_emits_a_success_reply(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    def failed_save(*args, **kwargs):
        raise RuntimeError("synthetic persistence failure")
    monkeypatch.setattr(AgentConversationService, "save_message", failed_save)
    events = []
    with pytest.raises(RuntimeError, match="synthetic persistence failure"):
        async for event in executor.run_stream(user_id=user.id, message="落地成都"):
            events.append(event)
    assert not any(e.get("event") in {"token", "done"} for e in events)

# Synthetic stations, clocks and destinations; no real journey or account data.
_TRAVEL_TIMELINE = '赶上了7:10从示例站出发去示例机场T2的8号地铁 7:00从家里出发 7:07到达地铁口 冲下来才能赶上 6:40起床洗了个澡'


def test_completed_transit_timeline_is_nonwriting_context():
    from app.services.agent_context_statement import parse_context_statement
    parsed = parse_context_statement(_TRAVEL_TIMELINE)
    assert parsed is not None and parsed.allows_local_reply
    intent = classify_agent_utterance(_TRAVEL_TIMELINE)
    assert (intent.primary, intent.domain, intent.operation) == ('chat', 'context', 'none')
    assert not intent.is_write
    assert '7:10' in parsed.reply
    assert '已记录' not in parsed.reply


@pytest.mark.parametrize('suffix', ['，帮我查睡眠', '，胸痛喘不上气', '，记录行程', '，提醒我吃药', '？'])
def test_transit_timeline_does_not_swallow_requests_or_symptoms(suffix):
    from app.services.agent_context_statement import parse_context_statement
    assert parse_context_statement(_TRAVEL_TIMELINE + suffix) is None


@pytest.mark.asyncio
async def test_transit_timeline_after_failed_meal_does_not_query_health(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic transit context')
    svc.save_message(conv.id, 'user', '下午吃了两个苹果')
    svc.save_message(conv.id, 'assistant', '这次没有写入：营养估算未完成。')
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    events = [e async for e in executor.run_stream(user_id=user.id, message=_TRAVEL_TIMELINE, conversation_id=conv.id)]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['route'] == 'context_statement'
    assert done['model_call_count'] == 0
    assert not done.get('write_receipts')

@pytest.mark.parametrize('message', [
    '朋友' + _TRAVEL_TIMELINE,
    '他说：' + _TRAVEL_TIMELINE,
    '“' + _TRAVEL_TIMELINE + '”',
    '如果' + _TRAVEL_TIMELINE,
    _TRAVEL_TIMELINE.replace('7:10', '25:10'),
    _TRAVEL_TIMELINE.replace('示例站', '胸痛站'),
    _TRAVEL_TIMELINE.replace('示例站', '请停药站'),
])
def test_transit_admission_rejects_foreign_quoted_invalid_or_sensitive_slots(message):
    from app.services.agent_context_statement import parse_context_statement
    assert parse_context_statement(message) is None

@pytest.mark.parametrize('signal', ['抽搐', '窒息', '救命', '失明', '吞咽困难'])
def test_transit_sensitive_slots_retain_shared_health_safety_routing(signal):
    from app.services.agent_context_statement import parse_context_statement
    from app.services.llm.task_routing import has_sensitive_health_language
    assert has_sensitive_health_language(signal)
    assert parse_context_statement(_TRAVEL_TIMELINE.replace('示例站', signal)) is None
    assert parse_context_statement(_TRAVEL_TIMELINE.replace('示例机场', signal + '机场')) is None


@pytest.mark.parametrize('message', [
    '10:00 落地北京 10:20 打上车',
    '10：00落地北京，10：20上车了。',
    '我10:00到达上海，10:20坐上车',
])
def test_arrival_and_boarding_timeline_is_context_not_health_query(message):
    from app.services.agent_context_statement import parse_context_statement
    statement = parse_context_statement(message)
    assert statement is not None and statement.allows_local_reply
    intent = classify_agent_utterance(message)
    assert (intent.primary, intent.domain, intent.operation) == ('chat', 'context', 'none')
    assert not intent.is_write
    assert '10:00' in statement.reply and '10:20' in statement.reply
    assert '已记录' not in statement.reply


@pytest.mark.parametrize('message', [
    '10:00落地北京10:20打上车，胸痛',
    '10:00落地北京10:20打上车，帮我查睡眠',
    '记录10:00落地北京10:20打上车',
    '明天10:00落地北京10:20打上车',
    '朋友10:00落地北京10:20打上车',
    '如果10:00落地北京10:20打上车',
    '“10:00落地北京10:20打上车”',
    '25:00落地北京10:20打上车',
    '10:00落地胸痛10:20打上车',
    '10:00落地未知城市10:20打上车',
    '10:00落地北京10:20打上车？',
])
def test_arrival_boarding_does_not_swallow_other_intent(message):
    from app.services.agent_context_statement import parse_context_statement
    assert parse_context_statement(message) is None


@pytest.mark.asyncio
async def test_arrival_boarding_after_symptom_does_not_query_or_write(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    svc = AgentConversationService(db)
    conv = svc.get_or_create_conversation(user.id, None, title='Synthetic arrival context')
    svc.save_message(conv.id, 'user', '记录连续打了三个喷嚏')
    svc.save_message(conv.id, 'assistant', '已记录。若需要可以补充严重程度。')
    executor = AgentExecutor(db)
    _no_heavy_work(executor, monkeypatch)
    events = [e async for e in executor.run_stream(user_id=user.id,
        message='10:00 落地北京 10:20 打上车', conversation_id=conv.id)]
    done = next(e['data'] for e in events if e.get('event') == 'done')
    assert done['route'] == 'context_statement'
    assert done['model_call_count'] == 0
    assert not done.get('write_receipts')
