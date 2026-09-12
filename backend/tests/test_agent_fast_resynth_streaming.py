# -*- coding: utf-8 -*-
"""Fast 直接正文丢弃后，流式收集强模型重合成，再经完整正文检查释放。

不变量:
  1. fast 模型正文从未下发给用户;
  2. 强模型仍使用流式供应方，但用户 token 在生成完成前不得释放;
  3. 强模型答案完整释放，不沿用 fast 工具轮的正文抑制。
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
@pytest.mark.parametrize("message,uses_fast_tool_round", [
    ("分析一下我最近的运动记录", True),
    ("我胃还有点痛，怎么办？", False),
])
async def test_quality_answer_buffers_before_release(
    db, auth_user_and_headers, monkeypatch, message, uses_fast_tool_round,
):
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)

    strong_deltas = ["综合", "分析", "结论"]
    state = {"strong_finished": False}
    called_models = []

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            called_models.append(self.model)
            if self.model == "qwen3.6-flash":
                # 低风险工具轮直接输出正文，无 tool_call 时必须丢弃。
                yield {"type": "content", "text": "FAST PROSE (must not reach user)"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            # 强模型重合成: 多 delta 流式。
            for d in strong_deltas:
                yield {"type": "content", "text": d}
            state["strong_finished"] = True
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            raise AssertionError("resynthesis must consume the streaming provider")

    _wire(executor, monkeypatch, lambda mid: FakeProvider(mid),
          user_provider=FakeProvider("qwen3.7-max"))

    events = []
    async for event in executor.run_stream(
        user_id=user.id, message=message, user_auth_token="test-token"
    ):
        if event.get("event") == "token" and event["data"].get("content"):
            assert state["strong_finished"], "unreviewed partial prose leaked"
        events.append(event)
    token_events = [e for e in events if e.get("event") == "token" and e["data"].get("content")]
    rendered = "".join(e["data"]["content"] for e in token_events)

    # (1) fast 正文从未下发
    assert "FAST PROSE" not in rendered
    assert "must not reach user" not in rendered
    # (2) 强模型答案完整
    assert rendered == "综合分析结论"
    done = events[-1]["data"]
    if uses_fast_tool_round:
        assert called_models == ["qwen3.6-flash", "qwen3.7-max"]
        assert "fast_tool_round_direct_answer_resynthesized" in done["fallback_reasons"]
    else:
        # Clinical questions now stay on the strong model from the first round.
        assert called_models == ["qwen3.7-max"]
        assert "fast_tool_round_direct_answer_resynthesized" not in done["fallback_reasons"]
