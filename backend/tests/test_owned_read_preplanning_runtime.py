"""Runtime preplanning must preserve Pi authority, receipts and answer routing."""
import json
from types import SimpleNamespace
from dataclasses import replace
from datetime import timedelta

import pytest

from app.config import settings
from app.models.agent_conversation import AgentMessage
from app.models.daily_health import DietRecord, GarminData
from tests.test_agent_coherence_pi_trajectories import (
    clock as clock, owned_data as owned_data,
    _isolate_twin_cache as _isolate_twin_cache, script_executor,
)

QUERY = "分析我最近7天的睡眠和饮食记录。"
ANSWER = "本轮仅作已返回样本的有限观察，不能据此判断健康状态。"


@pytest.fixture(autouse=True)
def enable_preplanning(monkeypatch):
    monkeypatch.setattr(settings, "owned_read_preplanning", True)



@pytest.mark.asyncio
@pytest.mark.parametrize("days", [1, 7, 31])
@pytest.mark.parametrize("state", ["available", "empty", "read_failure"])
async def test_real_runtime_preplan_preserves_scope_result_persistence_and_call_accounting(
    db, owned_data, monkeypatch, clock, days, state,
):
    if state == "empty":
        db.query(DietRecord).filter(DietRecord.user_id == owned_data.id).delete()
        db.query(GarminData).filter(GarminData.user_id == owned_data.id).delete()
        db.commit()
    elif state == "read_failure":
        def fail(*args, **kwargs):
            raise RuntimeError("synthetic_unavailable")
        monkeypatch.setattr("app.services.agent_longitudinal_read.read_longitudinal_health_query", fail)
    before = (db.query(DietRecord).count(), db.query(GarminData).count())
    rows = []
    for enabled in (False, True):
        with monkeypatch.context() as patch:
            patch.setattr(settings, "domain_prompt_optimization", enabled)
            calls = [] if enabled else [("health_query_batch", {"queries": [
                {"dimension": d, "days": days} for d in ("diet", "sleep")]})]
            if state != "read_failure":
                calls.append(ANSWER)
            trace = script_executor(db, patch, calls)
            events = [e async for e in trace.executor.run_stream(
                owned_data.id, f"分析我最近{days}天的睡眠和饮食记录。", channel="typed")]
            done = events[-1]["data"]
            saved = db.get(AgentMessage, done["message_id"])
            assert not trace.unexpected
            assert done["perf"]["agent_kernel"] == "pi"
            assert done["turn_outcome"]["status"] == ("failed" if state == "read_failure" else "complete")
            assert done["perf"]["model_call_count"] == len(trace.calls)
            assert done["perf"]["owned_read_preplanned"] is enabled
            assert saved.content == "".join(e["data"]["content"] for e in events if e.get("event") == "token")
            assert (db.query(DietRecord).count(), db.query(GarminData).count()) == before
            expected_start = (clock[0].date() - timedelta(days=days-1)).isoformat()
            assert all(q["start_date"] == expected_start and q["end_date"] == clock[0].date().isoformat()
                       for q in trace.dispatches[0].arguments["queries"])
            rows.append((len(trace.calls), trace.dispatches[0].arguments, trace.results, saved.content))
    assert rows[0][0] == rows[1][0] + 1
    assert rows[0][1] == rows[1][1]
    assert [result for _, result in rows[0][2]] == [result for _, result in rows[1][2]]
    assert rows[0][3] == rows[1][3]


@pytest.mark.parametrize("boundary", [
    "eligible", "disabled", "preplan_disabled", "owner", "context_owner", "envelope", "attachment", "pending",
    "sealed", "round", "prior_user", "prior_assistant", "prior_tool", "sync", "daily",
    "repair", "force_synthesis", "removed_tool", "read_only", "references", "write",
])
def test_runtime_eligibility_fails_closed(db, owned_data, monkeypatch, boundary):
    monkeypatch.setattr(settings, "domain_prompt_optimization", boundary != "disabled")
    executor = script_executor(db, monkeypatch, []).executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = QUERY
    executor._start_agent_kernel_turn(user_id=owned_data.id, message=QUERY, channel="typed")
    messages = [{"role": "user", "content": QUERY}]
    tools = [{"function": {"name": "health_query_batch"}}]
    sealed, index = boundary == "sealed", int(boundary == "round")
    if boundary == "preplan_disabled": monkeypatch.setattr(settings, "owned_read_preplanning", False)
    if boundary == "owner": executor._current_user_id += 1
    if boundary == "context_owner":
        s = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(s, context=replace(s.context, user_id=owned_data.id+1))
    if boundary == "envelope":
        s = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(s, envelope=replace(s.envelope, text="不同原话"))
    if boundary == "attachment": executor._current_turn_has_attachment = True
    if boundary == "pending": executor._agent_kernel_pending_confirmation_tools = ["health_record"]
    if boundary == "sync": executor._turn_sync_attempted = True
    if boundary == "daily": executor._turn_daily_read_plan = object()
    if boundary == "repair": executor._read_repair_failures = 1
    if boundary == "force_synthesis": executor._force_no_tools_synthesis = True
    if boundary == "removed_tool": tools = []
    if boundary == "read_only": executor._read_only_turn = True
    if boundary.startswith("prior_"):
        messages.insert(0, {"role": boundary.removeprefix("prior_"), "content": "既往待处理内容"})
    if boundary == "references":
        from app.services.agent_kernel.types import ActionableReference
        s = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(s, actionable_references=(
            ActionableReference(kind="owned_read_task", source_message_id="1", data={}),))
    if boundary == "write":
        s = executor._agent_kernel_snapshot
        executor._agent_kernel_snapshot = replace(s, intent=replace(s.intent, is_write=True))
    calls = executor._preplanned_owned_read_calls(index, messages, tools, sealed=sealed)
    assert bool(calls) == (boundary == "eligible")
    if calls:
        queries = json.loads(calls[0]["function"]["arguments"])["queries"]
        assert {q["dimension"] for q in queries} == {"diet", "sleep"}


@pytest.mark.parametrize("message", [
    "不要分析我最近7天的睡眠和饮食记录。", "假如分析我最近7天的睡眠和饮食记录。",
    "分析我妈妈最近7天的睡眠和饮食记录。", "分析我最近7天的睡眠和饮食记录，再记一杯水。",
    "分析我最近7天的睡眠和饮食记录，给用药建议。", "例句：分析我最近7天的睡眠和饮食记录。",
    "查询我最近7天的睡眠和饮食记录。", "分析我最近32天的睡眠和饮食记录。",
    "继续分析我最近7天的睡眠和饮食记录。",
])
def test_unproven_or_mixed_phrases_do_not_preplan(db, owned_data, monkeypatch, message):
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    executor = script_executor(db, monkeypatch, []).executor
    executor._current_user_id = owned_data.id
    executor._current_turn_user_message = message
    executor._start_agent_kernel_turn(user_id=owned_data.id, message=message, channel="typed")
    assert executor._preplanned_owned_read_calls(0, [{"role":"user", "content":message}],
        [{"function":{"name":"health_query_batch"}}]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("floor", ["balanced", "high_stakes"])
async def test_decision_on_preplan_preserves_requested_model_and_quality_floor(db, owned_data, monkeypatch, floor):
    from tests.test_decision_routing import wire, fake_result
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(settings, "decision_mode", "on")
    monkeypatch.setattr(settings, "decision_provider", "laya")
    monkeypatch.setattr(settings, "decision_admin_control_enabled", False)
    monkeypatch.setattr(settings, "staged_response_mode", "off")
    seen = wire(monkeypatch, fake_result("casual"))
    monkeypatch.setattr("app.services.llm.task_routing.classify_answer_task_tier", lambda *a, **k: floor)
    monkeypatch.setattr("app.services.llm.task_routing.pick_model_id_by_tier", lambda *a, **k: "quality-model")
    monkeypatch.setattr("app.services.llm.model_registry.get_model", lambda _: SimpleNamespace(speed_tier="fast"))
    selections = []
    for enabled in (False, True):
        with monkeypatch.context() as patch:
            patch.setattr(settings, "owned_read_preplanning", enabled)
            steps = [] if enabled else [("health_query_batch", {"queries": [
                {"dimension": d, "days": 7} for d in ("diet", "sleep")]})]
            trace = script_executor(db, patch, [*steps, ANSWER])
            events = [e async for e in trace.executor.run_stream(owned_data.id, QUERY, channel="typed",
                                                               extra_context=json.dumps({"model_id": "selected-fast"}))]
            assert len(trace.calls) == (1 if enabled else 2) and not trace.unexpected
            assert events[-1]["data"]["perf"]["owned_read_preplanned"] is enabled
            assert trace.executor._decision_route.effective_tier == floor
            selections.append(trace.executor._request_model_id)
    assert len(seen) == 2
    # Accepted non-casual Decision routes enforce the existing quality floor in both arms.
    assert selections == ["quality-model", "quality-model"]



@pytest.mark.asyncio
async def test_prior_correction_stays_model_first_in_real_pi(db, owned_data, monkeypatch):
    from app.models.agent_conversation import AgentConversation
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    conv = AgentConversation(user_id=owned_data.id)
    db.add(conv)
    db.flush()
    db.add(AgentMessage(conversation_id=conv.id, role="user", content="更正：此前的睡眠记录有误，不要据此判断恢复。"))
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content="已了解，这条更正没有修改任何记录。"))
    db.commit()
    trace = script_executor(db, monkeypatch, [("health_query_batch", {"queries": [
        {"dimension": d, "days": 7} for d in ("diet", "sleep")]}), ANSWER])
    events = [e async for e in trace.executor.run_stream(owned_data.id, QUERY, channel="typed", conversation_id=conv.id)]
    assert len(trace.calls) == 2 and not trace.unexpected
    assert not events[-1]["data"]["perf"]["owned_read_preplanned"]
    assert any("更正" in str(m.get("content")) for m in trace.calls[0][0])


@pytest.mark.parametrize("path", ["send", "stream"])
def test_preplanning_cannot_enter_without_ai_consent(client, db, auth_user_and_headers, monkeypatch, path):
    from unittest.mock import Mock
    from sqlalchemy.orm import sessionmaker
    from app.services import ai_consent
    _, headers = auth_user_and_headers
    monkeypatch.setattr(settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ai_consent, "SessionLocal", sessionmaker(bind=db.get_bind()))
    admit = Mock(side_effect=AssertionError("no Agent work before consent"))
    monkeypatch.setattr("app.api.agent._admit_agent_runtime", admit)
    response = client.post(f"/api/v1/agent/{path}", headers=headers,
                           json={"message": QUERY, "client_turn_id": f"preplan-consent-{path}"})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ai_consent_required"
    admit.assert_not_called()
