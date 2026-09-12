# -*- coding: utf-8 -*-
"""Pi retains structured tools across turns; text never starts another tool loop."""
import json

import pytest

from app.services.agent_executor import AgentExecutor


def _wire(executor, monkeypatch, provider, tool_names=("health_record", "health_query")):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    # 关掉工具轮快路由, 隔离 A2 (合成轮 schema drop) 于 A1 (fast route) 之外。
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)
    tools = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": name,
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for name in tool_names
    ]
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda **k: tools)
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda uid, db, **k: provider
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")
    # 隔离 KB / twin, 只测 round loop 的 tool-schema 行为。
    monkeypatch.setattr(executor, "_build_system_knowledge_prompt_context", lambda *a, **k: "")
    monkeypatch.setattr(executor, "_build_system_knowledge_evidence_card", lambda *a, **k: None)


async def _run(executor, message, user_id):
    return [
        e
        async for e in executor.run_stream(
            user_id=user_id, message=message, user_auth_token="test-token"
        )
    ]


@pytest.mark.asyncio
async def test_pi_keeps_structured_tools_until_model_finishes(db, auth_user_and_headers, monkeypatch):
    """A read result alone does not prove the structured tool chain is finished."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []

    class FakeProvider:
        model = "qwen3.7-max"

        async def chat_stream(self, **kwargs):
            calls.append(bool(kwargs.get("tools")))
            if len(calls) == 1:
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "health_query",
                                 "arguments": json.dumps({"dimension": "diet"})},
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            yield {"type": "content", "text": "综合分析结论"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            calls.append(bool(kwargs.get("tools")))
            return {"content": "综合分析结论", "finish_reason": "stop"}

    async def _exec(name, args, token):
        return json.dumps({"message": "今天记录了早餐"}, ensure_ascii=False)

    _wire(executor, monkeypatch, FakeProvider())
    monkeypatch.setattr(executor, "_execute_tool", _exec)

    events = await _run(executor, "帮我分析一下最近的饮食", user.id)
    rendered = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")

    assert calls == [True, True]
    assert "综合分析结论" in rendered


@pytest.mark.asyncio
async def test_pi_text_tool_list_fails_without_another_model_or_write(
    db, auth_user_and_headers, monkeypatch
):
    """A text protocol list fails without reviving the former repair loop."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    calls = []
    executed = []

    class FakeProvider:
        model = "qwen3.7-max"

        async def chat_stream(self, **kwargs):
            calls.append(bool(kwargs.get("tools")))
            n = len(calls)
            if n == 1:
                # round0: 先调 health_query
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "health_query",
                                 "arguments": json.dumps({"dimension": "diet"})},
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            if n == 2:
                # Plain text does not grant another model/tool attempt.
                yield {"type": "content", "text": "Tool calls:\n- health_record"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            raise AssertionError("text must not trigger another model request")

        async def chat(self, **kwargs):
            calls.append(bool(kwargs.get("tools")))
            return {"content": "已完成", "finish_reason": "stop"}

    async def _exec(name, args, token):
        executed.append(name)
        return json.dumps({"message": "ok"}, ensure_ascii=False)

    _wire(executor, monkeypatch, FakeProvider())
    monkeypatch.setattr(executor, "_execute_tool", _exec)

    events = await _run(executor, "帮我分析一下最近的饮食", user.id)
    rendered = "".join(e["data"].get("content", "") for e in events if e.get("event") == "token")

    assert calls == [True, True]
    assert executed == ["health_query"]
    assert rendered.strip() and "没有完成" in rendered
    assert "Tool calls:" not in rendered and "health_record" not in rendered
    assert events[-1]["data"]["completion_status"] == "error"
    assert not events[-1]["data"].get("write_receipts")


@pytest.mark.asyncio
async def test_pi_continues_two_explicit_readonly_calls_before_answer(db, auth_user_and_headers, monkeypatch):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    requested = []
    executed = []
    class Provider:
        model = "qwen3.7-max"
        async def chat_stream(self, **kwargs):
            requested.append(bool(kwargs.get("tools")))
            turn = len(requested)
            if turn <= 2:
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": f"read-{turn}", "type": "function", "function": {
                        "name": "health_query", "arguments": json.dumps({"dimension": "diet" if turn == 1 else "sleep"}),
                    },
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
            else:
                assert sum(m.get("role") == "tool" for m in kwargs["messages"]) == 2
                yield {"type": "content", "text": "两项查询均未找到记录，暂时无法分析。"}
                yield {"type": "finish", "finish_reason": "stop"}
    async def execute(name, args, token):
        executed.append((name, json.loads(args)))
        return '{"records":[],"count":0}'
    _wire(executor, monkeypatch, Provider())
    monkeypatch.setattr(executor, "_execute_tool", execute)
    events = await _run(executor, "查询最近饮食和睡眠记录", user.id)
    assert requested == [True, True, True]
    assert executed == [("health_query", {"dimension": "diet"}), ("health_query", {"dimension": "sleep"})]
    assert events[-1]["data"]["completion_status"] == "complete"
    assert not events[-1]["data"].get("write_receipts")
