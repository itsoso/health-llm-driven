# -*- coding: utf-8 -*-
"""工具决策轮快路由 (延迟优化, task_tiered_routing 门控, fail-closed)。

生产实测: 「我胃还有点痛,怎么办?」的 tool 轮 34s (qwen3.7-max reasoning) 主导时延,
但该轮只需吐一个 health_record 结构化 tool_call。此特性把**该轮**降到 fast +
reliable_tool_calling 模型 (qwen3.6-flash), 合成/答案轮仍留在强模型。

硬安全不变量 (本文件钉死):
  1. 合成/答案轮 (无 tools) 恒不降 fast —— 面向用户的医疗正文绝不来自 fast 模型;
  2. 只有 reliable_tool_calling=True 的 fast 模型才用于工具轮;
  3. flag 关 → 逐字节现状 (工具轮仍在强模型);
  4. 显式 UI 选模型 → 不被快路由覆盖;
  5. 无 fast 可靠工具模型 → fail-open 到现状;
  6. fast 工具轮若直接答文本 (无 tool_call) → 丢弃该 fast 文本, 在强模型重合成,
     且该 fast 文本从未 live 下发给用户。
"""
import json
from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


# ──────────────────────────────────────────────────────────────
# 单元级: _maybe_fast_route_tool_round / _resolve_chat_provider
# ──────────────────────────────────────────────────────────────

def _executor():
    ex = AgentExecutor(db=MagicMock())
    ex._current_user_id = None
    ex._request_model_id = None
    ex._prefer_fast_record_model = False
    ex._fast_route_simple_turn = False
    ex._tool_round_fast_routed = False
    return ex


def test_flag_off_never_fast_routes_tool_round(monkeypatch):
    """flag 关 → _maybe_fast_route_tool_round 恒 None (零行为变更)。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)
    called = {"n": 0}
    monkeypatch.setattr(
        reg, "pick_reliable_tool_model_id",
        lambda **k: (called.__setitem__("n", called["n"] + 1), "qwen3.6-flash")[1],
    )
    ex = _executor()
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None
    assert called["n"] == 0  # flag 关 → 根本不去选 fast 模型
    assert ex._tool_round_fast_routed is False


def test_flag_on_fast_routes_default_path(monkeypatch):
    """flag 开 + 无显式模型 + 有 fast 可靠工具模型 → 换成 fast, 置 _tool_round_fast_routed。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    sentinel = MagicMock(name="fast_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: sentinel)

    ex = _executor()
    out = ex._maybe_fast_route_tool_round("qwen3.7-max")
    assert out is not None
    provider, fast_id = out
    assert provider is sentinel
    assert fast_id == "qwen3.6-flash"
    assert ex._tool_round_fast_routed is True
    assert "tool_round_fast_routed" in ex._model_fallback_reasons


def test_flag_on_fast_routes_tool_round_even_with_explicit_model_pick(monkeypatch):
    """A1: 显式 UI 选模型 (_request_model_id) → **工具决策轮**仍降 fast (不可见内部决策)。

    「选择器显示什么就用什么」只约束答案轮 —— 那由 _turn_any_tool_executed 门守住,
    此单元覆盖首个工具决策轮 (尚无工具执行) 被降 fast 的新行为。
    """
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    sentinel = MagicMock(name="fast_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: sentinel)

    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"  # 显式选了强模型
    out = ex._maybe_fast_route_tool_round("claude-opus-4.7")
    assert out is not None
    provider, fast_id = out
    assert provider is sentinel
    assert fast_id == "qwen3.6-flash"
    assert ex._tool_round_fast_routed is True
    assert "tool_round_fast_routed" in ex._model_fallback_reasons


def test_flag_on_explicit_model_after_tool_executed_no_fast_route(monkeypatch):
    """A1 安全门: 显式选模型 + 已跑过工具 → 合成/答案轮**不**降 fast (答案留在显式模型)。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    ex = _executor()
    ex._request_model_id = "claude-opus-4.7"
    ex._turn_any_tool_executed = True  # 工具后合成轮
    assert ex._maybe_fast_route_tool_round("claude-opus-4.7") is None
    assert ex._tool_round_fast_routed is False


def test_flag_on_does_not_stack_on_existing_whole_turn_fast_route(monkeypatch):
    """既有整轮快路由 (_prefer_fast_record_model / _fast_route_simple_turn) → 不叠加。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    ex = _executor()
    ex._prefer_fast_record_model = True
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None
    ex._prefer_fast_record_model = False
    ex._fast_route_simple_turn = True
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None


def test_fail_open_when_no_fast_reliable_model(monkeypatch):
    """无 fast 可靠工具模型 (pick 返回 balanced) → None = 维持现状 (fail-open)。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    # 只回退到 balanced 模型 (deepseek-v3.2 是 balanced)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.7-plus")  # balanced
    ex = _executor()
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None
    assert ex._tool_round_fast_routed is False


def test_fail_open_when_pick_returns_none(monkeypatch):
    """无任何可靠工具模型 (pick None) → None。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: None)
    ex = _executor()
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None


def test_fail_open_when_tier_not_authorized(monkeypatch):
    """单一真源不变量: 若 "tool_routing" 被移出白名单 → 快路由失守关闭 (None)。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    import app.services.llm.task_routing as tr
    monkeypatch.setattr(tr, "_FAST_ELIGIBLE_TIERS", frozenset())  # 撤销授权
    ex = _executor()
    assert ex._maybe_fast_route_tool_round("qwen3.7-max") is None


def test_synthesis_round_no_tools_never_fast_routes(monkeypatch):
    """合成轮 (无 tools → pass_tools falsy) 恒不进快路由分支。
    通过 _resolve_chat_provider(None) 端到端验证: pick 不被调用。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    called = {"n": 0}
    monkeypatch.setattr(
        reg, "pick_reliable_tool_model_id",
        lambda **k: (called.__setitem__("n", called["n"] + 1), "qwen3.6-flash")[1],
    )
    default = MagicMock(name="default_provider")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_user", lambda uid, db, **k: default)

    ex = _executor()
    ex._current_user_id = 1
    provider, pass_tools = ex._resolve_chat_provider(None)  # 合成轮: 无 tools
    assert provider is default
    assert pass_tools is None
    assert called["n"] == 0  # 合成轮从不选 fast
    assert ex._tool_round_fast_routed is False


def test_resolve_provider_tool_round_swaps_to_fast(monkeypatch):
    """_resolve_chat_provider(tools) 默认路径: flag 开 → provider 换成 fast 模型。"""
    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")
    default = MagicMock(name="strong")
    fast = MagicMock(name="fast")
    import app.services.llm.factory as factory
    monkeypatch.setattr(factory, "create_provider_for_user", lambda uid, db, **k: default)
    monkeypatch.setattr(factory, "create_provider_for_model_id", lambda mid: fast)

    ex = _executor()
    ex._current_user_id = 1
    provider, pass_tools = ex._resolve_chat_provider([{"type": "function"}])
    assert provider is fast
    assert pass_tools  # tools 仍下发
    assert ex._tool_round_fast_routed is True


# ──────────────────────────────────────────────────────────────
# 端到端: 工具轮 fast / 合成轮 strong (镜像 tool_gating 的 per-round 断言)
# ──────────────────────────────────────────────────────────────

def _wire(
    executor,
    monkeypatch,
    provider_factory,
    *,
    user_provider=None,
    tool_name="health_record",
):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda: [{
            "type": "function",
            "function": {
                "name": tool_name,
                "description": "test tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id", provider_factory
    )
    if user_provider is not None:
        monkeypatch.setattr(
            "app.services.llm.factory.create_provider_for_user",
            lambda uid, db, **k: user_provider,
        )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


async def _run(executor, message, user_id, extra_context=None):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            extra_context=extra_context,
        )
    ]


@pytest.mark.asyncio
async def test_advice_turn_tool_round_fast_synthesis_strong(db, auth_user_and_headers, monkeypatch):
    """核心: flag 开, advice 轮调工具 → 首个工具决策轮 fast (qwen3.6-flash), 工具后合成轮强模型。

    默认路径下合成轮仍带 tools, 但 _turn_any_tool_executed 一旦置位就不再降 fast ——
    所以 provider_calls 第二项虽 has_tools=True, model 是强模型 (工具后的合成轮)。
    """
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")

    strong = "qwen3.7-max"

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools"))})
            if self.model == "qwen3.6-flash":
                # 首个工具决策轮 (fast): 吐结构化 tool_call
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "r1", "type": "function",
                    "function": {
                        "name": "environment_check",
                        "arguments": json.dumps({"location": "北京"}),
                    },
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            # 工具后的合成轮 (strong): 直接写医疗正文, 不再调工具
            yield {"type": "content", "text": "STRONG SYNTHESIS"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):  # 非流式兜底 (本用例不该走到)
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools")),
                                   "nonstream": True})
            return {"content": "STRONG SYNTHESIS", "finish_reason": "stop"}

    async def fake_exec_tool(name, args, token):
        assert name == "environment_check"
        return "北京当前 19C 小雨，湿度 92%"

    user_provider = FakeProvider(strong)
    _wire(
        executor,
        monkeypatch,
        lambda mid: FakeProvider(mid),
        user_provider=user_provider,
        tool_name="environment_check",
    )
    monkeypatch.setattr(executor, "_execute_tool", fake_exec_tool)

    events = await _run(executor, "来北京之后有点头疼，怎么办？", user.id)
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )
    done = events[-1]["data"]

    # 首轮 = fast(qwen3.6-flash) 决策工具; 工具后合成轮 = strong(qwen3.7-max)。
    assert provider_calls[0] == {"model": "qwen3.6-flash", "has_tools": True}
    # 合成轮 (工具后) 落在强模型 —— 关键安全断言: 医疗正文来自强模型, 不是 fast。
    assert all(c["model"] == "qwen3.7-max" for c in provider_calls[1:]), provider_calls
    assert rendered == "STRONG SYNTHESIS"
    assert done["answer_model"] == "qwen3.7-max"          # 面向用户答案 = 强模型
    assert "qwen3.6-flash" in done["tool_models"]          # 工具轮 = fast (可观测)
    assert "tool_round_fast_routed" in done["fallback_reasons"]
    assert done["tools_used"] == ["environment_check"]


@pytest.mark.asyncio
async def test_flag_off_tool_round_stays_on_strong(db, auth_user_and_headers, monkeypatch):
    """flag 关 → 工具轮**不**降 fast, 全程强模型 (逐字节现状)。fast provider 从不被建。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []
    built_ids = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", False)
    # 若代码错误地去选 fast, 这个 stub 会被调 —— 断言它不被调。
    picked = {"n": 0}
    monkeypatch.setattr(
        reg, "pick_reliable_tool_model_id",
        lambda **k: (picked.__setitem__("n", picked["n"] + 1), "qwen3.6-flash")[1],
    )

    strong = "qwen3.7-max"

    # 首轮吐 tool_call, 工具后那轮吐文本 (无 tool) —— 由 round-level 计数区分, 不看 model。
    round_n = {"n": 0}

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools"))})
            round_n["n"] += 1
            if round_n["n"] == 1:
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "r1", "type": "function",
                    "function": {"name": "health_record",
                                 "arguments": json.dumps({"record_type": "symptom",
                                                          "data": {"description": "胃痛"}})},
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            yield {"type": "content", "text": "STRONG ALL"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools")),
                                   "nonstream": True})
            return {"content": "STRONG ALL", "finish_reason": "stop"}

    def factory(mid):
        built_ids.append(mid)
        return FakeProvider(mid)

    async def _ok(name, args, token):
        return "已记录"

    user_provider = FakeProvider(strong)
    _wire(executor, monkeypatch, factory, user_provider=user_provider)
    monkeypatch.setattr(executor, "_execute_tool", _ok)

    events = await _run(executor, "我胃还有点痛，怎么办？", user.id)
    done = events[-1]["data"]

    # flag 关: 两轮都在强模型上, 从未选 fast, 从未建 fast provider。
    assert all(c["model"] == "qwen3.7-max" for c in provider_calls), provider_calls
    assert "qwen3.6-flash" not in built_ids
    assert done["answer_model"] == "qwen3.7-max"


@pytest.mark.asyncio
async def test_fast_tool_round_direct_answer_discarded_and_resynthesized(
    db, auth_user_and_headers, monkeypatch
):
    """安全兜底: fast 工具轮直接答文本 (无 tool_call) → 丢弃 fast 文本, 强模型重合成,
    且 fast 文本从未下发给用户。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools"))})
            if self.model == "qwen3.6-flash":
                # fast 模型没调工具, 直接答了一段医疗正文 (禁止外泄)
                yield {"type": "content", "text": "FAST MEDICAL PROSE (must not reach user)"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            # 强模型重合成 (_call_llm 非流式路径也可能进这里; 用 chat 兜)
            yield {"type": "content", "text": "STRONG RESYNTH"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools")),
                                   "nonstream": True})
            return {"content": "STRONG RESYNTH", "finish_reason": "stop"}

    strong = FakeProvider("qwen3.7-max")
    _wire(executor, monkeypatch, lambda mid: FakeProvider(mid), user_provider=strong)

    events = await _run(executor, "我胃还有点痛，怎么办？", user.id)
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )

    # fast 模型的医疗正文绝不出现在用户可见流里
    assert "FAST MEDICAL PROSE" not in rendered
    assert "must not reach user" not in rendered
    # 强模型重合成的答案出现
    assert "STRONG RESYNTH" in rendered
    # 观测: 记录了丢弃+重合成的原因
    done = events[-1]["data"]
    assert "fast_tool_round_direct_answer_resynthesized" in done["fallback_reasons"]


# ──────────────────────────────────────────────────────────────
# A1: 显式 per-message 选模型时, 工具轮仍降 fast; 答案轮留在显式模型
# (生产: mac/mobile 每条消息带 model_id → 190/231 回合此前完全无路由)
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_explicit_model_tool_round_fast_answer_on_explicit(
    db, auth_user_and_headers, monkeypatch
):
    """A1 核心: 显式选 qwen3.7-max → 首个工具决策轮降 fast(qwen3.6-flash),
    工具后合成轮回到**显式选定的 qwen3.7-max** (答案模型 = 用户所选)。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools"))})
            if self.model == "qwen3.6-flash":
                yield {"type": "tool_calls", "tool_calls": [{
                    "id": "r1", "type": "function",
                    "function": {
                        "name": "environment_check",
                        "arguments": json.dumps({"location": "北京"}),
                    },
                }]}
                yield {"type": "finish", "finish_reason": "tool_calls"}
                return
            yield {"type": "content", "text": "EXPLICIT SYNTHESIS"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools")),
                                   "nonstream": True})
            return {"content": "EXPLICIT SYNTHESIS", "finish_reason": "stop"}

    async def fake_exec_tool(name, args, token):
        assert name == "environment_check"
        return "北京当前 19C 小雨，湿度 92%"

    # user_provider = 显式选定的 qwen3.7-max (create_provider_for_model_id 也据 mid 建)。
    _wire(
        executor,
        monkeypatch,
        lambda mid: FakeProvider(mid),
        user_provider=FakeProvider("qwen3.7-max"),
        tool_name="environment_check",
    )
    monkeypatch.setattr(executor, "_execute_tool", fake_exec_tool)

    events = await _run(
        executor, "来北京之后有点头疼，怎么办？", user.id,
        extra_context=json.dumps({"model_id": "qwen3.7-max"}),
    )
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )
    done = events[-1]["data"]

    # 首轮 = fast(qwen3.6-flash) 决策工具。
    assert provider_calls[0] == {"model": "qwen3.6-flash", "has_tools": True}
    # 工具后所有轮 = 显式选定的 qwen3.7-max —— 答案绝不来自 fast。
    assert all(c["model"] == "qwen3.7-max" for c in provider_calls[1:]), provider_calls
    assert rendered == "EXPLICIT SYNTHESIS"
    assert done["answer_model"] == "qwen3.7-max"       # 面向用户答案 = 显式模型
    assert "qwen3.6-flash" in done["tool_models"]        # 工具轮 = fast (可观测)
    assert "tool_round_fast_routed" in done["fallback_reasons"]


@pytest.mark.asyncio
async def test_explicit_model_fast_direct_answer_resynthesized_on_explicit(
    db, auth_user_and_headers, monkeypatch
):
    """A1 安全兜底: 显式选模型下, fast 工具轮直接答文本 → 丢弃 fast 文本,
    在**显式选定的模型**上重合成; fast 文本从未下发。"""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    provider_calls = []

    monkeypatch.setattr("app.services.agent_executor.settings.task_tiered_routing", True)
    monkeypatch.setattr(reg, "pick_reliable_tool_model_id", lambda **k: "qwen3.6-flash")

    class FakeProvider:
        def __init__(self, model_id):
            self.model = model_id

        async def chat_stream(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools"))})
            if self.model == "qwen3.6-flash":
                yield {"type": "content", "text": "FAST MEDICAL PROSE (must not reach user)"}
                yield {"type": "finish", "finish_reason": "stop"}
                return
            yield {"type": "content", "text": "EXPLICIT RESYNTH"}
            yield {"type": "finish", "finish_reason": "stop"}

        async def chat(self, **kwargs):
            provider_calls.append({"model": self.model, "has_tools": bool(kwargs.get("tools")),
                                   "nonstream": True})
            return {"content": "EXPLICIT RESYNTH", "finish_reason": "stop"}

    _wire(executor, monkeypatch, lambda mid: FakeProvider(mid),
          user_provider=FakeProvider("qwen3.7-max"))

    events = await _run(
        executor, "我胃还有点痛，怎么办？", user.id,
        extra_context=json.dumps({"model_id": "qwen3.7-max"}),
    )
    rendered = "".join(
        e["data"].get("content", "") for e in events if e.get("event") == "token"
    )
    done = events[-1]["data"]

    assert "FAST MEDICAL PROSE" not in rendered
    assert "must not reach user" not in rendered
    assert "EXPLICIT RESYNTH" in rendered
    # 重合成落在显式选定的 qwen3.7-max, 从未在 fast 上产出用户可见正文。
    resynth_calls = [c for c in provider_calls if c["model"] == "qwen3.7-max"]
    assert resynth_calls, provider_calls
    assert "fast_tool_round_direct_answer_resynthesized" in done["fallback_reasons"]
