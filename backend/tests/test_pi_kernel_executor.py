"""Real Pi package through the production executor, with a scripted provider."""

import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.agent_kernel.postconditions import PostconditionResult


@pytest.fixture(autouse=True)
def _isolate_twin_cache(isolated_agent_protocol_transport):
    """No live Redis or provider traffic in this runtime integration suite."""


@pytest.mark.asyncio
async def test_production_executor_uses_pi_for_tool_loop(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    dispatched = []

    async def provider(messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "query-1", "type": "function",
                "function": {"name": "health_query", "arguments": '{"dimension":"weight"}'},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            assert any(m.get("role") == "tool" and m.get("tool_call_id") == "query-1" for m in messages)
            yield {"type": "content", "text": "已完成查询，本次没有可用记录。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def execute(name, args, token):
        dispatched.append((name, json.loads(args) if isinstance(args, str) else args))
        return '{"records":[],"count":0}'

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use tools to read data.")
    def expose_test_error(error):
        raise error
    monkeypatch.setattr("app.services.agent_executor.safe_llm_error_message", expose_test_error)
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    events = [event async for event in executor.run_stream(user.id, "查询我的体重记录", client_turn_id="pi-loop")]
    done = events[-1]["data"]
    assert done["completion_status"] == "complete"
    assert done["perf"]["agent_kernel"] == "pi"
    assert len(calls) == 2
    assert dispatched == [("health_query", {"dimension": "weight"})]
    assert "health_query" in done["tools_used"]


@pytest.mark.asyncio
async def test_colloquial_diet_recall_reaches_gateway_and_returns_to_pi(
    db, auth_user_and_headers, monkeypatch,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls, dispatched = [], []

    async def provider(messages, tools):
        calls.append(messages)
        if len(calls) == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "diet-recall", "type": "function", "function": {
                    "name": "health_query", "arguments": '{"dimension":"diet","days":30}',
                },
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            assert any(m.get("role") == "tool" and "燕麦" in m.get("content", "") for m in messages)
            yield {"type": "content", "text": "今天记录了燕麦。"}
            yield {"type": "finish", "finish_reason": "stop"}

    async def dispatch(request, token):
        dispatched.append(request)
        return json.dumps({"records": [{"food_name": "燕麦"}], "availability": "available"}, ensure_ascii=False)

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "Use tools to read data.")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    # Keep the production executor and capability gateway; replace only data I/O.
    monkeypatch.setattr(executor, "_dispatch_tool_request", dispatch)
    events = [e async for e in executor.run_stream(user.id, "今天我吃了啥", client_turn_id="pi-diet-recall")]
    assert len(dispatched) == 1
    assert dispatched[0].tool_name == "health_query"
    args = dispatched[0].arguments
    assert args == {
        "dimension": "diet", "start_date": args["end_date"],
        "end_date": args["end_date"], "timezone": "Asia/Shanghai",
    }
    assert len(calls) == 2
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"
    assert events[-1]["data"]["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_plain_text_tool_instructions_never_dispatch(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    dispatched = []

    async def provider(messages, tools):
        yield {"type": "content", "text": 'Tool calls:\n- health_record {"record_type":"weight","data":{"weight":70}}'}
        yield {"type": "finish", "finish_reason": "stop"}

    async def execute(*args):
        dispatched.append(args)
        raise AssertionError("text is not a tool call")

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    events = [event async for event in executor.run_stream(user.id, "你好", client_turn_id="pi-no-text-tools")]
    assert not dispatched
    assert events[-1]["data"]["perf"]["agent_kernel"] == "pi"


@pytest.mark.asyncio
async def test_goal_verifier_rejects_partial_success_before_publication(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    verified = []

    async def provider(messages, tools):
        yield {"type": "tool_calls", "tool_calls": [{
            "id": "water-one", "type": "function", "function": {
                "name": "health_record", "arguments": '{"record_type":"water","data":{"amount":200}}',
            },
        }]}
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def execute(name, args, token):
        data = json.loads(args)["data"]
        return json.dumps({"id": 71, "resource_type": "water_record", "record_date": data["record_date"], "message": "已记录饮水"})

    def verify(goal, **kwargs):
        verified.append((goal, kwargs))
        return PostconditionResult(False, "missing_target")

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    monkeypatch.setattr("app.services.agent_executor.verify_goal_postconditions", verify)
    def expose_error(error):
        raise error
    monkeypatch.setattr("app.services.agent_executor.safe_llm_error_message", expose_error)
    events = [event async for event in executor.run_stream(user.id, "记录喝水五百毫升", channel="typed", client_turn_id="pi-goal-verify")]
    assert executor._agent_kernel_snapshot.goal.kind == "simple_health_record"
    assert events[-1]["data"]["write_receipts"]
    assert len(verified) == 1
    assert verified[0][1]["write_receipts"]
    assert events[-1]["data"]["completion_status"] == "error"
    text = "".join((event.get("data") or {}).get("content", "") for event in events if event.get("event") == "token")
    assert "不能确认已经全部完成" in text


@pytest.mark.asyncio
async def test_symptom_plan_and_verified_operation_use_identical_canonical_args(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    executed = []

    async def provider(messages, tools):
        yield {"type": "tool_calls", "tool_calls": [{
            "id": "symptom-one", "type": "function", "function": {
                "name": "health_record", "arguments": '{"record_type":"symptom","data":{}}',
            },
        }]}
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def execute(name, args, token):
        executed.append(json.loads(args))
        return json.dumps({"id": 81, "resource_type": "symptom_record", "record_date": executed[-1]["data"]["record_date"], "message": "已记录症状"})

    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    monkeypatch.setattr(executor, "_call_llm_stream", provider)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    events = [event async for event in executor.run_stream(user.id, "我头痛", channel="typed", client_turn_id="pi-canonical")]
    assert events[-1]["event"] == "done"
    assert executed and executed[0]["data"]["description"]
    from app.services.agent_conversation_service import AgentConversationService
    source = AgentConversationService(db).find_user_message_by_client_turn(user.id, "pi-canonical")
    assert source is not None
    operations = source.meta["write_operations"]
    assert set(source.meta["write_plan"]["fingerprints"]) == set(operations)
    assert all(operation["status"] == "verified" for operation in operations.values())
