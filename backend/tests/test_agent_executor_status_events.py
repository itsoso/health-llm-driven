"""Thinking-process status SSE events + fast-route answer max_tokens cap.

Two additive latency/UX features on the 小巴 hot path (AgentExecutor.run_stream):

1. Real thinking-process status events (思考过程可视化). The mac client used to guess
   "正在思考…" by elapsed time; the backend now emits REAL stage events with the exact
   contract:
       {"event": "status", "data": {"stage": <str>, "detail": <str|None>, "round": <int|None>}}
   Emitted at: vision pre-pass, top of each tool-loop round (thinking/synthesis), and
   right before each serial tool executes (tool, with a short Chinese label).

2. Fast-route answer max_tokens cap. Fast-routed simple record/query turns cap answer
   generation at FAST_ROUTE_ANSWER_MAX_TOKENS (2000); everything else keeps
   ANSWER_MAX_TOKENS (8000). The tail decode of a simple answer is part of the latency.
"""
import pytest

from app.services.agent_executor import (
    ANSWER_MAX_TOKENS,
    FAST_ROUTE_ANSWER_MAX_TOKENS,
    AgentExecutor,
    _tool_status_label,
)
from app.services.llm import model_registry as reg


# ──── tool → status label map ────

@pytest.mark.parametrize("name,label", [
    ("health_query", "查询健康数据"),
    ("health_record", "写入记录"),
    ("health_manage", "管理记录"),
    ("health_analysis", "深度分析"),
    ("knowledge_search", "检索知识库"),
    ("realtime_search", "联网搜索"),
])
def test_tool_status_label_maps_known_tools(name, label):
    assert _tool_status_label(name) == label


def test_tool_status_label_unknown_falls_back_to_raw_name():
    assert _tool_status_label("some_new_tool") == "some_new_tool"
    assert _tool_status_label(None) == "工具"


# ──── shared wiring ────

def _statuses(events):
    """Extract (stage, detail, round) tuples from status events, in emit order."""
    out = []
    for e in events:
        if e.get("event") == "status":
            d = e["data"]
            out.append((d["stage"], d.get("detail"), d.get("round")))
    return out


async def _run(executor, message, images=None, extra_context=None, user_id=1):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
            images=images,
            extra_context=extra_context,
        )
    ]


def _wire_min(executor, monkeypatch):
    """Minimal wiring so run_stream reaches the round loop without real LLM/provider."""
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr("app.services.agent_executor.get_health_tools", lambda: [{
        "type": "function",
        "function": {"name": "health_query", "description": "x",
                     "parameters": {"type": "object", "properties": {}}},
    }])
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


# ──── status events: order on a mocked tool turn ────

@pytest.mark.asyncio
async def test_status_events_order_vision_thinking_tool_synthesis(
    db, auth_user_and_headers, monkeypatch
):
    """A photo turn that calls a tool then synthesizes emits, in order:
    vision → thinking(r1) → tool(r1) → synthesis(r2)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    # Force the vision pre-pass path (independent vision, not raw-image direct send).
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda uid: False)

    async def _no_import(*a, **k):
        return None

    async def _vision(*a, **k):
        return "图里是一份早餐"

    monkeypatch.setattr(executor, "_try_import_medical_report_images", _no_import)
    monkeypatch.setattr(executor, "_analyze_image_with_vision", _vision)

    # Round 1 → one tool call; round 2 → final answer (no tools).
    calls = {"round": 0}

    async def fake_stream(messages, round_tools):
        calls["round"] += 1
        if calls["round"] == 1:
            yield {"type": "tool_calls", "tool_calls": [{
                "id": "c1",
                "function": {"name": "health_query", "arguments": "{}"},
            }]}
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": "查到了。"}
            yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    async def fake_exec(name, args, token):
        return "今天步数 8000"

    monkeypatch.setattr(executor, "_execute_tool", fake_exec)
    # After a tool ran, force the deterministic synthesis (no-tools) answer round so the
    # round-2 status is 'synthesis' rather than 'thinking'.
    orig = executor._should_synthesize_with_requested_model_after_tools
    monkeypatch.setattr(
        executor,
        "_should_synthesize_with_requested_model_after_tools",
        lambda n: n > 0 or orig(n),
    )

    events = await _run(
        executor,
        "看看我今天的步数",
        images=[{"base64": "AA==", "mime_type": "image/png"}],
        user_id=user.id,
    )
    stages = _statuses(events)

    # exact ordered contract
    assert stages == [
        ("vision", None, None),
        ("thinking", None, 1),
        ("tool", "查询健康数据", 1),
        ("synthesis", None, 2),
    ]


@pytest.mark.asyncio
async def test_status_no_vision_when_raw_images_sent_direct(
    db, auth_user_and_headers, monkeypatch
):
    """Raw images go straight to a multimodal model → NO separate vision pre-pass →
    no 'vision' status event."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    monkeypatch.setattr(executor, "_should_send_raw_images_to_primary_model", lambda uid: True)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "好的"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(
        executor,
        "看看这张图",
        images=[{"base64": "AA==", "mime_type": "image/png"}],
        user_id=user.id,
    )
    stages = _statuses(events)
    assert ("vision", None, None) not in stages
    # a plain no-tool answer turn still emits a thinking status for round 1
    assert ("thinking", None, 1) in stages


@pytest.mark.asyncio
async def test_status_thinking_only_for_plain_text_turn(
    db, auth_user_and_headers, monkeypatch
):
    """No images, no tools → just a single 'thinking' status (no vision/tool/synthesis)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)

    async def fake_stream(messages, round_tools):
        yield {"type": "content", "text": "你好呀"}
        yield {"type": "finish", "finish_reason": "stop"}

    monkeypatch.setattr(executor, "_call_llm_stream", fake_stream)

    events = await _run(executor, "你好呀", user_id=user.id)
    stages = _statuses(events)
    assert stages == [("thinking", None, 1)]


# ──── fast-route answer max_tokens cap ────

def _capture_stream_max_tokens(executor, monkeypatch):
    """Patch the provider resolution so _call_llm_stream records the max_tokens it passes."""
    captured = {}

    class _Prov:
        model = "cap-test"

        async def chat_stream(self, **kwargs):
            captured["max_tokens"] = kwargs.get("max_tokens")
            yield {"type": "content", "text": "OK"}
            yield {"type": "finish", "finish_reason": "stop"}

    # _call_llm_stream calls self._resolve_chat_provider(tools) → (provider, pass_tools)
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda tools: (_Prov(), None))
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    return captured


@pytest.mark.asyncio
async def test_fast_routed_turn_caps_answer_max_tokens(
    db, auth_user_and_headers, monkeypatch
):
    """Fast-routed simple turn → answer max_tokens capped to FAST_ROUTE_ANSWER_MAX_TOKENS."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    captured = _capture_stream_max_tokens(executor, monkeypatch)
    # ensure the fast route actually fires (env-agnostic)
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    await _run(executor, "查一下我今天喝了多少水", user_id=user.id)

    assert executor._fast_route_simple_turn is True
    assert captured["max_tokens"] == FAST_ROUTE_ANSWER_MAX_TOKENS
    assert FAST_ROUTE_ANSWER_MAX_TOKENS == 2000


@pytest.mark.asyncio
async def test_non_fast_turn_keeps_full_answer_max_tokens(
    db, auth_user_and_headers, monkeypatch
):
    """Analysis/复盘 turn (not fast-routed) → keeps full ANSWER_MAX_TOKENS (8000)."""
    user, _ = auth_user_and_headers
    executor = AgentExecutor(db)
    _wire_min(executor, monkeypatch)
    captured = _capture_stream_max_tokens(executor, monkeypatch)
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: "deepseek-v4-flash")

    await _run(executor, "综合分析我的健康趋势", user_id=user.id)

    assert executor._fast_route_simple_turn is False
    assert captured["max_tokens"] == ANSWER_MAX_TOKENS
    assert ANSWER_MAX_TOKENS == 8000


@pytest.mark.asyncio
async def test_answer_max_tokens_helper_switches_on_flag(db):
    """Unit: _answer_max_tokens returns capped only when the fast-route flag is set."""
    executor = AgentExecutor(db)
    executor._fast_route_simple_turn = False
    assert executor._answer_max_tokens() == ANSWER_MAX_TOKENS
    executor._fast_route_simple_turn = True
    assert executor._answer_max_tokens() == FAST_ROUTE_ANSWER_MAX_TOKENS
