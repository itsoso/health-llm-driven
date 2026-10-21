"""Synthetic mixed-domain analysis: exact owned windows and real intake evidence."""

from dataclasses import replace
from datetime import datetime, date

import pytest

from app.services.agent_kernel.capability_policy import decide_tool_capability
from app.services.agent_kernel.intent_frame import build_intent_frame
from app.services.agent_kernel.read_task_scope import resolve_owned_read_scope
from app.services.agent_kernel.types import AgentEnvelope, ExecutionContext, ToolExecutionRequest, TurnSnapshot


def snapshot(text):
    envelope = AgentEnvelope(user_id=41, channel="typed", text=text)
    context = ExecutionContext(user_id=41, channel="typed", timezone="Asia/Taipei",
                               current_time=datetime.fromisoformat("2031-04-14T10:00:00+08:00"))
    return TurnSnapshot(envelope, context, build_intent_frame(envelope, context))


@pytest.mark.parametrize("text", [
    "查询我的过去十天饮食、补剂、服药记录并分析",
    "基于过去十天的饮食补剂服药记录 分析原因",
    "我腹痛还没好。基于过去十天的饮食、补剂、用药记录分析原因。",
    "肚子疼还没好 不是什么原因导致了胃肠疼痛 吃了三天合成药了 基于过去十天的饮食补剂服药记录 分析原因",
])
def test_mixed_analysis_binds_medication_with_same_calendar_window(text):
    state = snapshot(text)
    scope = resolve_owned_read_scope(state)
    assert scope is not None
    assert {q["dimension"] for q in scope.queries} == {"diet", "supplements", "medication"}
    for query in scope.queries:
        assert {k: v for k, v in query.items() if k != "days"} == {"dimension": query["dimension"],
                         "start_date": "2031-04-05", "end_date": "2031-04-14", "timezone": "Asia/Taipei"}
        assert query.get("days", 10) == 10
        result = decide_tool_capability(state, ToolExecutionRequest("health_query", dict(query)))
        assert result.action == "allow", result.reason
        assert result.normalized_args == query
    batch = decide_tool_capability(state, ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert batch.action == "allow", batch.reason


@pytest.mark.parametrize("text", [
    "不要查询我的过去十天饮食、补剂、服药记录并分析",
    "如果需要，查询我的过去十天饮食、补剂、服药记录并分析",
    "查询我朋友的过去十天饮食、补剂、服药记录并分析",
    "解释例句：‘查询我的过去十天饮食、补剂、服药记录并分析’",
    "基于过去十天的饮食补剂服药记录分析原因，只看服药后的记录",
    "基于过去十天的饮食补剂服药记录分析原因，删除旧记录",
])
def test_mixed_analysis_cannot_discard_authority_or_filters(text):
    state = snapshot(text)
    assert resolve_owned_read_scope(state) is None
    assert decide_tool_capability(state, ToolExecutionRequest("health_query", {"dimension": "medication", "days": 10})).action == "block"


@pytest.mark.parametrize("extra", [{"days": 31}, {"start_date": "2030-01-01"}, {"user_id": 42}, {"timezone": "UTC"}])
def test_medication_proposal_cannot_enlarge_owned_scope(extra):
    state = snapshot("查询我的过去十天饮食、补剂、服药记录并分析")
    assert decide_tool_capability(state, ToolExecutionRequest("health_query", {"dimension": "medication", "days": 10, **extra})).action == "block"


def test_analysis_does_not_grant_symptom_write():
    state = snapshot("我腹痛还没好。基于过去十天的饮食、补剂、用药记录分析原因。")
    assert decide_tool_capability(state, ToolExecutionRequest("health_record", {
        "record_type": "symptom", "data": {"symptom_name": "腹痛"},
    })).action == "block"


def continued_state(text):
    from app.services.agent_kernel.types import ActionableReference
    from app.services.agent_read_task_continuation import read_task_metadata
    initial = snapshot("我腹痛还没好。基于过去十天的饮食、补剂、用药记录分析原因。")
    scope = resolve_owned_read_scope(initial)
    meta = read_task_metadata(initial, scope, sync_status=False)
    assert meta is not None
    return replace(snapshot(text), actionable_references=(
        ActionableReference(kind="owned_read_task", source_message_id="123", data=meta),
    ))


@pytest.mark.parametrize("text", ["疼痛在肚脐周边 下腹部", "下午仍然隐约肚子痛", "疼痛大概是4分", "疼痛是10分",
                                  "现在还是隐隐约约腹痛", "有嗳气的感觉 大便正常 吃饭三个小时后开始疼", "2.5毫克 最近三天间或吃合成药"])
def test_symptom_followup_keeps_exact_scope_without_write_authority(text):
    state = continued_state(text)
    scope = resolve_owned_read_scope(state)
    assert scope is not None and scope.composite_advice
    assert {q["dimension"] for q in scope.queries} == {"diet", "supplements", "medication"}
    assert all(q["start_date"] == "2031-04-05" for q in scope.queries)
    result = decide_tool_capability(state, ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert result.action == "allow", result.reason
    assert decide_tool_capability(state, ToolExecutionRequest("health_query", {"dimension": "genetic"})).action == "block"
    assert decide_tool_capability(state, ToolExecutionRequest("health_record", {"record_type": "symptom", "data": {"symptom_name": "腹痛"}})).action == "block"


def test_oral_all_input_request_keeps_every_requested_domain_and_window():
    state = snapshot("基于过去8天的饮食运动 睡眠 补剂 药物 以及输入的所有内容 做推断 为啥我又开始肚子疼？")
    scope = resolve_owned_read_scope(state)
    assert scope is not None
    assert {q["dimension"] for q in scope.queries} == {"diet", "workout", "sleep", "supplements", "medication", "conversation"}
    assert all(q["days"] == 8 and q["start_date"] == "2031-04-07" for q in scope.queries)
    decision = decide_tool_capability(state, ToolExecutionRequest("health_query_batch", {"queries": list(scope.queries)}))
    assert decision.action == "allow", decision.reason


@pytest.mark.parametrize("text", [
    "查询我的原始对话并分析", "查询我的过去一年原始对话并分析",
    "基于过去8天的饮食以及我朋友的原始对话分析原因",
    "基于过去8天的饮食以及输入的所有内容分析原因，只查昨天下午",
    "不要查询，基于过去8天的饮食以及输入的所有内容分析原因",
    "吃了三天合成药之后 基于过去8天的饮食以及输入的所有内容分析原因",
])
def test_conversation_read_requires_explicit_owned_complete_calendar_scope(text):
    state = snapshot(text)
    assert resolve_owned_read_scope(state) is None
    decision = decide_tool_capability(state, ToolExecutionRequest("health_query", {"dimension": "conversation", "days": 8}))
    assert decision.action == "block"


@pytest.mark.parametrize("text", ["我朋友疼痛在下腹部", "疼痛在下腹部，查询过去一年", "疼痛在下腹部，删除记录", "不要再查询", "如果疼痛在下腹部", "‘疼痛在下腹部’"])
def test_symptom_followup_never_inherits_expanded_authority(text):
    from app.services.agent_read_task_continuation import resolve_read_task_continuation
    assert resolve_read_task_continuation(continued_state(text)) is None


def test_symptom_followup_needs_current_server_analysis_task():
    from app.services.agent_read_task_continuation import resolve_read_task_continuation
    state = continued_state("疼痛在下腹部")
    assert resolve_read_task_continuation(replace(state, actionable_references=())) is None
    ref = state.actionable_references[0]
    ordinary = replace(ref, data={**ref.data, "limitations": []})
    assert resolve_read_task_continuation(replace(state, actionable_references=(ordinary,))) is None
    stale = replace(ref, data={**ref.data, "created_at": "2031-04-12T10:00:00+08:00"})
    assert resolve_read_task_continuation(replace(state, actionable_references=(stale,))) is None
    assert resolve_read_task_continuation(replace(state, context=replace(state.context, user_id=42))) is None


def test_symptom_analysis_instructions_allow_clinical_clarification_but_not_diagnosis():
    from app.services.agent_composed_read_completion import read_scope_synthesis_instructions
    scope = resolve_owned_read_scope(continued_state("疼痛在下腹部"))
    instructions = read_scope_synthesis_instructions(scope)
    assert "支持与反对证据" in instructions
    assert "危险信号" in instructions
    assert "不能确诊" in instructions
    assert "不要要求用户补充" not in instructions


def test_symptom_analysis_preserves_conversation_for_clinical_synthesis(db):
    from app.services.agent_executor import AgentExecutor
    state = continued_state("疼痛在下腹部")
    executor = AgentExecutor(db)
    executor._agent_kernel_snapshot = state
    executor._force_no_tools_synthesis = False
    executor._turn_sync_attempted = False
    def compact_completion():
        pytest.fail("Symptom analysis must retain the clinical transcript, not compact to a lifestyle summary")
    executor._composed_read_completion = compact_completion
    assert executor._composed_synthesis_messages(41, 123, None, state.envelope.text) is None


def test_medication_history_has_owned_logs_including_inactive_medicine(db, auth_user_and_headers):
    from app.models.user import User
    from app.models.medication import Medication, MedicationLog
    from app.services.agent_longitudinal_read import read_longitudinal_health_query
    from app.services.agent_query_window import parse_query_window

    owner, _ = auth_user_and_headers
    other = User(username="mixed-analysis-other", name="Synthetic other", hashed_password="fixture")
    db.add(other); db.flush()
    active = Medication(user_id=owner.id, name="Synthetic active", is_active=True)
    inactive = Medication(user_id=owner.id, name="Synthetic stopped", is_active=False)
    foreign = Medication(user_id=other.id, name="Other owner", is_active=True)
    db.add_all([active, inactive, foreign]); db.flush()
    own_log = MedicationLog(user_id=owner.id, medication_id=inactive.id, taken_date=date(2031, 4, 8), status="taken", actual_dosage="1 tablet")
    db.add_all([own_log,
        MedicationLog(user_id=owner.id, medication_id=active.id, taken_date=date(2031, 3, 1), status="taken"),
        MedicationLog(user_id=other.id, medication_id=foreign.id, taken_date=date(2031, 4, 8), status="taken"),
        MedicationLog(user_id=owner.id, medication_id=foreign.id, taken_date=date(2031, 4, 9), status="taken"),
    ]); db.flush()
    window = parse_query_window({"start_date": "2031-04-05", "end_date": "2031-04-14", "timezone": "Asia/Taipei"})
    result = read_longitudinal_health_query(db, owner.id, "medication", window)
    assert result["window"] == window.as_dict()
    assert [r["id"] for r in result["records"]] == [own_log.id]
    assert result["records"][0]["medication_name"] == "Synthetic stopped"
    assert result["records"][0]["actual_dosage"] == "1 tablet"
    assert result["active_medications"] == []
    assert result["source_scope"] == "owned_medication_intake_logs"
    assert "Other owner" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("include_original_inputs", [False, True])
@pytest.mark.parametrize("last_followup", ["下午仍然隐隐肚子痛", "有嗳气的感觉 大便正常 吃饭三个小时后开始疼"])
async def test_real_pi_mixed_read_then_location_followup_keeps_evidence_and_no_writes(
    db, auth_user_and_headers, isolated_agent_protocol_transport, monkeypatch, include_original_inputs, last_followup,
):
    import json
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.agent_executor import AgentExecutor

    user, _ = auth_user_and_headers
    prior = AgentConversation(user_id=user.id)
    db.add(prior); db.flush()
    db.add_all([
        AgentMessage(conversation_id=prior.id, role="user", content="Synthetic prior report: a record request failed; this remains an unverified user report."),
        AgentMessage(conversation_id=prior.id, role="assistant", content="FORBIDDEN_ASSISTANT_HYPOTHESIS"),
    ]); db.commit()
    executor = AgentExecutor(db)
    calls, dispatched = [], []
    questions = ["我腹痛还没好。基于过去十天的饮食、补剂、用药记录分析原因。",
                 "疼痛在肚脐周边 下腹部", last_followup]
    expected = {"diet", "supplements", "medication"}
    if include_original_inputs:
        questions[0] = "基于过去8天的饮食运动 睡眠 补剂 药物 以及输入的所有内容 做推断 为啥我又开始肚子疼？"
        expected |= {"workout", "sleep", "conversation"}

    async def provider(messages, tools):
        calls.append(messages)
        if not executor._turn_composed_read_executions:
            scope = resolve_owned_read_scope(executor._ensure_agent_kernel_turn())
            assert scope is not None
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "synthetic-mixed-read", "type": "function", "function": {
                    "name": "health_query_batch", "arguments": json.dumps({"queries": list(scope.queries)}),
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "腹痛原因尚不确定，现有记录不足以确认药物或饮食相关。位置补充属于用户自述。若疼痛加重、伴发热或反复呕吐，请及时就医。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatched.append(request)
        assert request.tool_name == "health_query_batch"
        return await executor._exec_health_query_batch("http://synthetic.invalid/api/v1", {}, request.arguments)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "按工具证据回答，不确诊、不改药、不写记录。")
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    conversation_id = None
    scopes = []
    for index, question in enumerate(questions):
        events = [event async for event in executor.run_stream(
            user.id, question, conversation_id=conversation_id, client_turn_id=f"synthetic-mixed-{index}",
        )]
        done = next(e["data"] for e in reversed(events) if e.get("event") == "done")
        saved = db.get(AgentMessage, done["message_id"])
        conversation_id = saved.conversation_id
        assert not done.get("write_receipts")
        assert executor._agent_kernel_snapshot.intent.is_write is False
        assert done["turn_outcome"]["status"] == "complete", done["turn_outcome"]
        assert "查询未执行" not in saved.content
        scopes.append(saved.meta["read_task"]["queries"])
        assert {q["dimension"] for q in scopes[-1]} == expected
    assert scopes[0] == scopes[1] == scopes[2]
    assert len(dispatched) == 3
    assert all(question in json.dumps(calls[-1], ensure_ascii=False) for question in questions)
    serialized = json.dumps(calls[-1], ensure_ascii=False)
    assert "FORBIDDEN_ASSISTANT_HYPOTHESIS" not in serialized
    assert ("Synthetic prior report" in serialized) is include_original_inputs
