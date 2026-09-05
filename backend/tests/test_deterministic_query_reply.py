"""端到端: 确定性查询直出 (Phase-2 rank2) 通过 /api/v1/agent/stream。

flag ON + 覆盖维度的只读查询回合 → 从真实 tool result 渲染确定性读数并**跳过合成轮**。
窄范围多指标请求还会确定性构造批查询, 省掉工具决策轮 (0 次 LLM)。flag OFF / 安全
告警后缀 / 未覆盖维度 → fail-open 回落正常模型路径。
"""
import json

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm import model_registry as reg


_FAST_ID = "deepseek-v4-flash"

_WATER_RESULT = json.dumps({
    "record_date": "2026-07-12",
    "total_amount": 1200,
    "target_amount": 2000,
    "progress_percentage": 60.0,
    "records_count": 2,
    "records": [{"amount": 600}, {"amount": 600}],
}, ensure_ascii=False)

_SYNTH_ANSWER = "综合来看,你今天的饮水量还可以,继续保持。"


def _stub_registry_fast(monkeypatch, fast_id=_FAST_ID):
    monkeypatch.setattr(reg, "pick_fast_tool_model_id", lambda **_k: fast_id)


async def _run(executor, message, user_id):
    return [
        event
        async for event in executor.run_stream(
            user_id=user_id,
            message=message,
            user_auth_token="test-token",
        )
    ]


class _ToolThenAnswerProvider:
    """Round 1: health_query tool_call; round 2+: 纯文本合成答案。

    stream_calls 累积每次 chat_stream 调用 = LLM 轮数 (确定性短路后不该有第二次)。
    """

    def __init__(self, model_id, tool_args, stream_calls, tool_name="health_query"):
        self.model = model_id
        self._tool_args = tool_args
        self._stream_calls = stream_calls
        self._tool_name = tool_name

    async def chat_stream(self, **kwargs):
        self._stream_calls.append(kwargs.get("tools"))
        if not any(
            message.get("role") == "tool"
            for message in kwargs.get("messages", [])
        ):
            yield {
                "type": "tool_calls",
                "tool_calls": [{
                    "id": "call_q1",
                    "type": "function",
                    "function": {
                        "name": self._tool_name,
                        "arguments": json.dumps(self._tool_args, ensure_ascii=False),
                    },
                }],
            }
            yield {"type": "finish", "finish_reason": "tool_calls"}
        else:
            yield {"type": "content", "text": _SYNTH_ANSWER}
            yield {"type": "finish", "finish_reason": "stop"}

    async def chat(self, **kwargs):  # noqa: ARG002 — 兜底非流式
        return {"content": _SYNTH_ANSWER, "finish_reason": "stop"}


def _wire(executor, monkeypatch, provider_factory):
    monkeypatch.setattr("app.services.agent_executor.settings.llm_provider", "tokenplan")
    monkeypatch.setattr("app.services.agent_executor.settings.agent_base_url", None)
    monkeypatch.setattr("app.services.agent_executor.settings.agent_api_key", None)
    monkeypatch.setattr(
        "app.services.agent_executor.get_health_tools",
        lambda subset=None: [
            {
                "type": "function",
                "function": {"name": "health_query", "description": "x",
                             "parameters": {"type": "object", "properties": {}}},
            },
            {
                "type": "function",
                "function": {"name": "health_query_batch", "description": "x",
                             "parameters": {"type": "object", "properties": {}}},
            },
        ],
    )
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_model_id",
        provider_factory,
    )
    # Every provider path used by this integration test must stay local.  The
    # second (synthesis) round resolves the user's default provider rather than
    # the fast tool provider, so only stubbing the model-id factory would make
    # this test depend on a configured TokenPlan key.
    monkeypatch.setattr(
        "app.services.llm.factory.create_provider_for_user",
        lambda *_args, **_kwargs: provider_factory("test-default"),
    )
    monkeypatch.setattr(executor, "_build_system_prompt", lambda *a, **k: "SYS")


def _tokens(events) -> str:
    return "".join(
        e["data"].get("content", "")
        for e in events
        if e.get("event") == "token"
    )


def _set_flag(monkeypatch, value):
    monkeypatch.setattr("app.services.agent_executor.settings.deterministic_query_reply", value)


def _make_executor(
    db,
    monkeypatch,
    tool_args=None,
    tool_result=_WATER_RESULT,
    tool_name="health_query",
):
    """Wire an executor whose health_query returns a canned result. Returns (executor, state)."""
    executor = AgentExecutor(db)
    state = {"stream_calls": [], "executed": []}

    def factory(model_id):
        return _ToolThenAnswerProvider(
            model_id,
            tool_args or {"dimension": "water"},
            state["stream_calls"],
            tool_name=tool_name,
        )

    async def fake_execute_tool(tool_name, args, token):  # noqa: ARG001
        state["executed"].append((tool_name, args))
        return tool_result

    _stub_registry_fast(monkeypatch)
    _wire(executor, monkeypatch, factory)
    monkeypatch.setattr(executor, "_execute_tool", fake_execute_tool)
    return executor, state


@pytest.mark.asyncio
async def test_flag_on_water_query_is_deterministic_single_round(db, auth_user_and_headers, monkeypatch):
    """flag ON + 水查询 → 确定性读数, 恰好 1 次 LLM 调用 (无合成轮)。"""
    user, _ = auth_user_and_headers
    executor, state = _make_executor(db, monkeypatch)
    _set_flag(monkeypatch, True)

    events = await _run(executor, "今天喝了多少水", user.id)

    # 恰好 1 次 LLM 调用 = 工具决策轮; 合成轮被 break 跳过。
    assert len(state["stream_calls"]) == 1
    # health_query 执行了一次。
    assert state["executed"] == [("health_query", '{"dimension": "water"}')]
    # 面向用户 tokens = 确定性读数, 且不含合成答案。
    tokens = _tokens(events)
    assert tokens == "今日饮水 1200ml,目标 2000ml(完成 60%)。"
    assert _SYNTH_ANSWER not in tokens
    # done 事件正常, completion_status complete。
    done = events[-1]["data"]
    assert done["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_flag_on_batch_query_is_deterministic_single_round(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    batch_args = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ],
    }
    batch_result = json.dumps({
        "queries": [
            {
                "dimension": "hrv",
                "days": 7,
                "agg": "avg",
                "value": 58,
                "unit": "ms",
                "n": 7,
            },
            {
                "dimension": "sleep",
                "days": 7,
                "agg": "avg",
                "value": 76,
                "n": 7,
            },
        ],
        "meta": {"executed": 2, "failed": 0},
    }, ensure_ascii=False)
    executor, state = _make_executor(
        db,
        monkeypatch,
        tool_args=batch_args,
        tool_result=batch_result,
        tool_name="health_query_batch",
    )
    _set_flag(monkeypatch, True)

    events = await _run(executor, "查一下最近7天的HRV和睡眠平均值", user.id)

    assert len(state["stream_calls"]) == 0
    assert state["executed"] == [
        ("health_query_batch", json.dumps(batch_args, ensure_ascii=False)),
    ]
    assert _tokens(events) == (
        "近7天 HRV 平均值 58 ms。\n\n"
        "近7天 睡眠评分 平均值 76 分。"
    )
    done = events[-1]["data"]
    assert done["completion_status"] == "complete"
    assert done["llm_rounds"] == 0
    assert done["perf"]["end_to_end_ttft_ms"] is not None
    assert done["perf"]["first_useful_ms"] is not None


@pytest.mark.asyncio
async def test_implicit_batch_aggregation_skips_decision_model_but_uses_synthesis(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    batch_args = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": None},
            {"dimension": "sleep", "days": 7, "agg": None},
        ],
    }
    batch_result = json.dumps({
        "queries": [
            {
                "dimension": "hrv",
                "days": 7,
                "agg": None,
                "value": None,
                "data": "hrv 最近 7 天: 2026-08-25: 58ms",
            },
            {
                "dimension": "sleep",
                "days": 7,
                "agg": None,
                "value": None,
                "data": "sleep 最近 7 天: 2026-08-25: 76",
            },
        ],
        "meta": {"executed": 2, "failed": 0},
    }, ensure_ascii=False)
    executor, state = _make_executor(
        db,
        monkeypatch,
        tool_args=batch_args,
        tool_result=batch_result,
        tool_name="health_query_batch",
    )
    _set_flag(monkeypatch, True)

    events = await _run(executor, "查一下最近7天的HRV和睡眠数据", user.id)

    assert len(state["stream_calls"]) == 1
    assert state["executed"] == [
        ("health_query_batch", json.dumps(batch_args, ensure_ascii=False)),
    ]
    assert _tokens(events) == _SYNTH_ANSWER
    assert events[-1]["data"]["perf"]["decision_route"] == (
        "deterministic_batch_query_fallback_llm"
    )


@pytest.mark.asyncio
async def test_preplanned_batch_failure_falls_open_to_one_synthesis_round(
    db, auth_user_and_headers, monkeypatch
):
    user, _ = auth_user_and_headers
    batch_args = {
        "queries": [
            {"dimension": "hrv", "days": 7, "agg": "avg"},
            {"dimension": "sleep", "days": 7, "agg": "avg"},
        ],
    }
    batch_result = json.dumps({
        "queries": [
            {
                "dimension": "hrv",
                "days": 7,
                "agg": "avg",
                "value": None,
                "error": "数据查询失败",
            },
            {
                "dimension": "sleep",
                "days": 7,
                "agg": "avg",
                "value": 76,
                "n": 7,
            },
        ],
        "meta": {"executed": 2, "failed": 1},
    }, ensure_ascii=False)
    executor, state = _make_executor(
        db,
        monkeypatch,
        tool_args=batch_args,
        tool_result=batch_result,
        tool_name="health_query_batch",
    )
    _set_flag(monkeypatch, True)

    events = await _run(executor, "查一下最近7天的HRV和睡眠平均值", user.id)

    assert len(state["stream_calls"]) == 1
    assert state["executed"] == [
        ("health_query_batch", json.dumps(batch_args, ensure_ascii=False)),
    ]
    assert _tokens(events) == _SYNTH_ANSWER
    assert events[-1]["data"]["perf"]["decision_route"] == (
        "deterministic_batch_query_fallback_llm"
    )


@pytest.mark.asyncio
async def test_flag_off_falls_through_to_synthesis(db, auth_user_and_headers, monkeypatch):
    """flag OFF → 现状: 工具轮 + 合成轮 (2 次 LLM 调用), 答案来自合成, 无确定性读数。"""
    user, _ = auth_user_and_headers
    executor, state = _make_executor(db, monkeypatch)
    _set_flag(monkeypatch, False)

    events = await _run(executor, "今天喝了多少水", user.id)

    assert len(state["stream_calls"]) == 2  # 工具轮 + 合成轮
    tokens = _tokens(events)
    assert tokens == _SYNTH_ANSWER
    assert "今日饮水" not in tokens  # 确定性读数从未产生
    done = events[-1]["data"]
    assert done["completion_status"] == "complete"


@pytest.mark.asyncio
async def test_shadow_keeps_synthesis_and_reports_content_free_eligibility(
    db, auth_user_and_headers, monkeypatch,
):
    user, _ = auth_user_and_headers
    executor, state = _make_executor(db, monkeypatch)
    _set_flag(monkeypatch, "shadow")

    events = await _run(executor, "今天喝了多少水", user.id)

    assert len(state["stream_calls"]) == 2
    assert _tokens(events) == _SYNTH_ANSWER
    assert events[-1]["data"]["perf"]["deterministic_query"] == {
        "mode": "shadow",
        "eligible": True,
        "candidate_chars": len("今日饮水 1200ml,目标 2000ml(完成 60%)。"),
    }


@pytest.mark.asyncio
async def test_unknown_mode_fails_closed_to_normal_synthesis(
    db, auth_user_and_headers, monkeypatch,
):
    user, _ = auth_user_and_headers
    executor, state = _make_executor(db, monkeypatch)
    _set_flag(monkeypatch, "surprise")

    events = await _run(executor, "今天喝了多少水", user.id)

    assert len(state["stream_calls"]) == 2
    assert _tokens(events) == _SYNTH_ANSWER
    assert "deterministic_query" not in events[-1]["data"]["perf"]


@pytest.mark.asyncio
async def test_flag_on_safety_suffix_falls_through_to_synthesis(db, auth_user_and_headers, monkeypatch):
    """flag ON 但 tool result 带安全告警后缀 → 绝不确定性短路, 回落合成 (安全文本须进强模型答案)。"""
    user, _ = auth_user_and_headers
    from app.services.agent_executor import SAFETY_WARNING_MARKER

    warned_result = _WATER_RESULT + SAFETY_WARNING_MARKER + " 夜间血氧偏低"
    executor, state = _make_executor(db, monkeypatch, tool_result=warned_result)
    _set_flag(monkeypatch, True)

    events = await _run(executor, "今天喝了多少水", user.id)

    assert len(state["stream_calls"]) == 2  # 回落合成轮
    tokens = _tokens(events)
    assert tokens == _SYNTH_ANSWER
    assert "今日饮水" not in tokens


@pytest.mark.asyncio
async def test_flag_on_uncovered_dimension_falls_through(db, auth_user_and_headers, monkeypatch):
    """flag ON 但维度未覆盖 (genetic) → fail-open 回落合成轮。"""
    user, _ = auth_user_and_headers
    executor, state = _make_executor(
        db, monkeypatch,
        tool_args={"dimension": "genetic"},
        tool_result=json.dumps([{"gene_name": "MTHFR", "genotype": "CT"}], ensure_ascii=False),
    )
    _set_flag(monkeypatch, True)

    events = await _run(executor, "查一下我的基因 MTHFR", user.id)

    assert len(state["stream_calls"]) == 2  # 回落合成轮
    tokens = _tokens(events)
    assert tokens == _SYNTH_ANSWER
