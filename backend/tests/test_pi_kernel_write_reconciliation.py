"""Real Pi schema skips must reconcile the durable plan before user release."""
import json

import pytest

from app.models.agent_conversation import AgentMessage
from app.services.agent_executor import AgentExecutor


@pytest.fixture(autouse=True)
def _isolated_transports(isolated_agent_protocol_transport, monkeypatch):
    async def no_estimation(_food_items):
        return None
    monkeypatch.setattr("app.services.agent_executor._estimate_simple_diet_nutrition", no_estimation)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ordinary", "panel"])
@pytest.mark.parametrize("scenario", ["partial", "all_invalid", "invalid_record_type", "canonical_duplicate"])
async def test_pi_reconciles_skipped_writes_before_claiming_completion(
    db, auth_user_and_headers, monkeypatch, mode, scenario,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    valid = {"record_type": "diet", "data": {"food_items": "测试食物", "meal_type": "lunch"}}
    invalid = {"record_type": "diet", "data": "bad"}
    if scenario == "invalid_record_type":
        invalid = {"record_type": "not_a_record_type", "data": {}}
    elif scenario == "canonical_duplicate":
        valid = {"record_type": "weight", "weight": 70, "data": {}}
        invalid = {"record_type": "weight", "weight": 70, "data": "bad"}
    payloads = [invalid] if scenario in {"all_invalid", "invalid_record_type"} else [valid, invalid]
    requests = 0
    dispatched = []
    panel_calls = []

    async def lead(messages, tools):
        nonlocal requests
        requests += 1
        if requests == 1:
            return {
                "content": "", "finish_reason": "tool_calls", "tool_calls": [
                    {"id": f"schema-{index}", "type": "function", "function": {
                        "name": "health_record", "arguments": json.dumps(payload),
                    }} for index, payload in enumerate(payloads)
                ],
            }
        return {"content": "两项记录都已经保存好了。", "finish_reason": "stop"}

    async def stream(messages, tools):
        response = await lead(messages, tools)
        if response.get("tool_calls"):
            yield {"type": "tool_calls", "tool_calls": response["tool_calls"]}
        if response.get("content"):
            yield {"type": "content", "text": response["content"]}
        yield {"type": "finish", "finish_reason": response["finish_reason"]}

    async def execute(name, args, token):
        parsed = json.loads(args) if isinstance(args, str) else args
        dispatched.append(parsed)
        return json.dumps({
            "id": 701, "record_id": 701,
            "resource_type": f"{parsed['record_type']}_record",
            "status": "verified", "success": True,
        })

    class Provider:
        async def chat(self, **kwargs):
            panel_calls.append(kwargs)
            return {"content": "两项记录都已经保存好了。", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm", lead)
    monkeypatch.setattr(executor, "_call_llm_stream", stream)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    monkeypatch.setattr("app.services.llm.factory.create_provider_for_model_id", lambda *_: Provider())
    turn_id = f"pi-reconcile-{mode}-{scenario}"
    events = [event async for event in executor.run_stream(
        user.id, "记录两条健康数据，并综合分析", channel="typed", client_turn_id=turn_id,
        extra_context='{"multi_model":true}' if mode == "panel" else None,
    )]
    assert executor._agent_kernel_snapshot.goal.kind == "write"
    done = events[-1]["data"]
    rendered = "".join((event.get("data") or {}).get("content", "") for event in events if event.get("event") == "token")
    assert len(dispatched) == (0 if scenario in {"all_invalid", "invalid_record_type"} else 1)
    assert "两项记录都已经保存好了" not in rendered
    assert done["completion_status"] == "error"
    assert panel_calls == []
    assert len(done["write_receipts"]) == len(dispatched)
    saved_user = db.query(AgentMessage).filter_by(role="user").one()
    statuses = [operation["status"] for operation in saved_user.meta["write_operations"].values()]
    assert "planned" not in statuses
    assert "uncertain" not in statuses
    if scenario == "canonical_duplicate":
        assert statuses == ["verified"], "schema skip must not downgrade the same canonical verified operation"
    elif dispatched:
        assert sorted(statuses) == ["rejected", "verified"]
    else:
        assert statuses == ["rejected"]


@pytest.mark.asyncio
@pytest.mark.parametrize("same_operation", [False, True])
async def test_pi_terminal_uncertain_write_cancels_siblings_without_losing_uncertainty(
    db, auth_user_and_headers, monkeypatch, same_operation,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    dispatched = []
    model_calls = 0

    async def stream(messages, tools):
        nonlocal model_calls
        model_calls += 1
        yield {"type": "tool_calls", "tool_calls": [
            {"id": f"write-{index}", "type": "function", "function": {
                "name": "health_record",
                "arguments": json.dumps({"record_type": "water", "data": {"amount": amount}}),
            }} for index, amount in enumerate((300, 300 if same_operation else 500))
        ]}
        yield {"type": "finish", "finish_reason": "tool_calls"}

    async def execute(name, args, token):
        dispatched.append(json.loads(args))
        return "Error: upstream returned 500 after request dispatch"

    monkeypatch.setattr(executor, "_call_llm_stream", stream)
    monkeypatch.setattr(executor, "_execute_tool", execute)
    events = [event async for event in executor.run_stream(
        user.id, "记录两条健康数据，并综合分析", channel="typed",
        client_turn_id="pi-cancel-sibling-on-uncertain",
    )]
    done = events[-1]["data"]
    rendered = "".join((event.get("data") or {}).get("content", "") for event in events if event.get("event") == "token")
    assert model_calls == 1
    assert len(dispatched) == 1
    assert "可能已提交" in rendered
    assert "没有自动重试" in rendered
    assert done["completion_status"] == "error"
    assert done["turn_outcome"]["status"] == "reconciliation_required"
    saved_user = db.query(AgentMessage).filter_by(role="user").one()
    assert sorted(operation["status"] for operation in saved_user.meta["write_operations"].values()) == (
        ["uncertain"] if same_operation else ["rejected", "uncertain"]
    )
    assert saved_user.meta["write_state"]["status"] == "uncertain"
    # Simulate a worker losing the final assistant row after dispatch. Retrying
    # the same durable user turn must reconcile, never repeat the uncertain write.
    for assistant in db.query(AgentMessage).filter_by(
        role="assistant", conversation_id=saved_user.conversation_id,
    ).all():
        db.delete(assistant)
    db.commit()
    retry_executor = AgentExecutor(db)
    retry_calls = []

    async def no_retry_model(*args, **kwargs):
        retry_calls.append("model")
        raise AssertionError("uncertain write must not re-enter model execution")
        yield  # Preserve the stream protocol for a path that must never run.

    async def no_retry_tool(*args, **kwargs):
        retry_calls.append("tool")
        raise AssertionError("uncertain write must not be dispatched again")

    monkeypatch.setattr(retry_executor, "_build_system_prompt", lambda *_a, **_k: "SYS")
    monkeypatch.setattr(retry_executor, "_call_llm_stream", no_retry_model)
    monkeypatch.setattr(retry_executor, "_execute_tool", no_retry_tool)
    retry_events = [event async for event in retry_executor.run_stream(
        user.id, "记录两条健康数据，并综合分析", channel="typed",
        client_turn_id="pi-cancel-sibling-on-uncertain",
    )]
    assert retry_calls == []
    assert retry_events[-1]["data"]["completion_status"] == "error"
    retry_text = "".join((event.get("data") or {}).get("content", "") for event in retry_events if event.get("event") == "token")
    assert "没有自动重试" in retry_text
