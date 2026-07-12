# -*- coding: utf-8 -*-
"""A3: fast 工具轮直接答文本被丢弃后, 强模型重合成走**流式**路径 (tokens 逐 delta
下发), 消除 ttft≈total 空洞 (生产 turn 5960 ttft 39.5s ≈ total)。

不变量:
  1. fast 模型正文从未下发给用户;
  2. 强模型重合成的答案**分多个 token 事件流式**到达 (证明非一次性整块 emit);
  3. _tool_round_fast_routed 在合成轮已重置 → 强模型 tokens 不被抑制。
"""
import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


def _wire(executor, monkeypatch, provider_factory, *, user_provider):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda **k: [{
            "type": "function",
            "function": {"name": "health_record", "description": "r",
                         "parameters": {"type": "object", "properties": {}}},
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", provider_factory
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user", lambda uid, db, **k: user_provider
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


@pytest.mark.asyncio
async def test_fast_direct_answer_resynthesis_streams_token_by_token(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    strong_deltas = ["综合", "分析", "结论"]

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            if self.model == "qwen3.6-flash":
                # fast 工具轮直接答医疗正文 (无 tool_call) → 必被丢弃, 绝不外泄。
                yield {"type": "content", "text": "FAST PROSE (must not reach user)"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            # 强模型重合成: 多 delta 流式。
            for d in strong_deltas:
                yield {"type": "content", "text": d}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            # 若走到非流式 (不该), 整块返回 —— 测试会因 token 事件数=1 而失败, 暴露回退。
            return {"content": "".join(strong_deltas), "finish_reason": "stop"}

    _wire(executor, monkeypatch, lambda mid: FakeProvider(mid),
          user_provider=FakeProvider("qwen3.7-max"))

    events = [
        e async for e in executor.run_stream(
            user_id=user.id, message="我胃还有点痛，怎么办？", user_auth_token="test-token"
        )
    ]
    token_events = [e for e in events if e.get("event") == "token" and e["data"].get("content")]
    rendered = "".join(e["data"]["content"] for e in token_events)

    # (1) fast 正文从未下发
    assert "FAST PROSE" not in rendered
    assert "must not reach user" not in rendered
    # (2) 强模型答案完整
    assert rendered == "综合分析结论"
    # (3) 流式: 3 个 delta → >=2 个 token 事件 (整块 emit 只会有 1 个)
    assert len(token_events) >= 2, [e["data"]["content"] for e in token_events]
    done = events[-1]["data"]
    assert "fast_tool_round_direct_answer_resynthesized" in done["fallback_reasons"]
