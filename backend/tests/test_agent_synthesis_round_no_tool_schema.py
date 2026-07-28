# -*- coding: utf-8 -*-
"""A2 (plan rank4): 合成轮不再重发 18KB 工具 schema。

上一轮已执行过工具 → 本轮实际是合成轮, 对**所有**模型置 round_tools=[], 省 ~5k
tokens/轮 prefill。2+-round 回合 = 55% 的回合。

硬安全不变量 (本文件钉死):
  1. 合成轮不发 tools (省 schema), 但输出侧的文本式/内联工具调用抑制**照旧生效**
     (_detect_tools 用完整 tools 词表, 不随 round_tools 置空而失守);
  2. 自纠: 若合成轮模型其实还想再调工具 (文本式 "Tool calls:") → 重开 tools, 下一轮
     结构化调用, 多轮链式工具回合不被裁 (正确性 > 省 token);
  3. 首个工具决策轮仍带 tools (模型得以决策)。
"""
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
async def test_synthesis_round_after_tool_drops_tool_schema(db, auth_user_and_headers, monkeypatch):
    """核心: round0 调工具 → round1 合成轮不再带 tools (round_tools=[])。"""
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

    # round0 带 tools (决策), round1 合成轮**不**带 tools (省 18KB schema)。
    assert calls[0] is True, calls
    assert calls[1] is False, calls
    assert "综合分析结论" in rendered


@pytest.mark.asyncio
async def test_synthesis_round_self_corrects_on_botched_text_tool_call(
    db, auth_user_and_headers, monkeypatch
):
    """自纠: 合成轮 (无 tools) 模型吐文本式 "Tool calls:" → 检测(用完整词表)→ 重开
    tools → 下一轮结构化真调工具。链式工具回合不被 A2 裁掉, 且裸标记不外泄。"""
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
                # round1 (合成轮, 无 tools): 模型其实还想调工具, 但只会吐文本式清单
                yield {"type": "content", "text": "Tool calls:\n- health_record"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            if n == 3:
                # round2 (自纠后重开 tools): 结构化真调 health_record
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "c2", "type": "function",
                    "function": {"name": "health_record",
                                 "arguments": json.dumps({"record_type": "note", "data": {}})},
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            # round3: 写入后合成最终答案 (收尾, 不再链式)
            yield {"type": "content", "text": "已完成记录与分析"}
            yield {"type": "finish", "finish_reason": "stop"}

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

    # round0 tools, round1 合成轮无 tools (被 A2 置空), round2 自纠后重开 tools。
    assert calls[0] is True, calls
    assert calls[1] is False, calls
    assert calls[2] is True, calls  # keep_tools_after_synthesis_miss 生效
    # 分析请求是只读目标。模型即使在自纠轮结构化提出 health_record，也必须被
    # 目标守卫拒绝，随后进入无工具合成轮，而不是执行隐藏写入。
    assert calls[3] is False, calls
    assert executed == ["health_query"], executed
    assert "已完成记录与分析" in rendered
    # 裸 "Tool calls:" 文本清单绝不外泄给用户。
    assert "Tool calls:" not in rendered
