"""P4 /agent/send 可观测性 meta 测试。

覆盖:
- build_send_meta 纯函数:model/rounds/latency/tools_used 映射 + usage 结构 +
  成本诚实 null(拿不到成本给 None,不填 0)。
- /agent/send 端点:响应含 meta.model(有模型时非 None)、usage 结构、latency 结构;
  老字段零变化。
"""
from __future__ import annotations

import json as jsonlib
import pytest

pytestmark = pytest.mark.usefixtures("consenting_agent_user")

from app.services.agent_send_meta import build_send_meta


# ---------------------------------------------------------------------------
# build_send_meta 纯函数
# ---------------------------------------------------------------------------

def _done_data() -> dict:
    return {
        "conversation_id": 1,
        "message_id": 2,
        "elapsed_ms": 4200,
        "llm_ms": 3900,
        "llm_rounds": 2,
        "model": "qwen3.7-plus",
        "answer_model": "qwen3.7-plus",
        "selected_model": "qwen3.7-plus",
        "tools_used": ["health_query"],
        "perf": {"total_ms": 4200, "llm_ttft_ms": 800},
    }


def _usage_summary(cost_usd: float = 0.00123, source: str = "builtin:qwen3.7-plus") -> dict:
    return {
        "calls": 2,
        "prompt_tokens": 1500,
        "completion_tokens": 600,
        "total_tokens": 2100,
        "cost_usd": cost_usd,
        "cost_cny": cost_usd * 7.2,
        "cost_estimated": True,
        "cost_sources": [source],
        "models": ["qwen3.7-plus"],
        "providers": ["tokenplan"],
        "tokenplan_credits_estimate": 3.18,
        "tokenplan_cost_cny": 0.0222,
        "tokenplan_payg_value_cny": 0.03024,
        "tokenplan_cost_estimated": True,
        "tokenplan_cost_source": "public_cny_rate:qwen3.7-plus",
        "tokenplan_monthly_fee_cny": 698.0,
        "tokenplan_monthly_credits": 100_000,
    }


def test_build_meta_maps_model_rounds_latency_tools():
    meta = build_send_meta(_done_data(), _usage_summary())
    assert meta["model"] == "qwen3.7-plus"
    assert meta["rounds"] == 2
    assert meta["latency"] == {"total_ms": 4200, "ttft_ms": 800}
    assert meta["tools_used"] == ["health_query"]


def test_build_meta_prefers_end_to_end_latency_when_available():
    done = _done_data()
    done["perf"].update({
        "end_to_end_total_ms": 5100,
        "end_to_end_ttft_ms": 1700,
    })

    meta = build_send_meta(done, _usage_summary())

    assert meta["latency"] == {"total_ms": 5100, "ttft_ms": 1700}


def test_build_meta_usage_structure_from_summary():
    meta = build_send_meta(_done_data(), _usage_summary())
    usage = meta["usage"]
    assert usage is not None
    assert usage["input_tokens"] == 1500
    assert usage["output_tokens"] == 600
    assert usage["total_tokens"] == 2100
    assert usage["calls"] == 2


def test_build_meta_cost_present_when_priced():
    meta = build_send_meta(_done_data(), _usage_summary(cost_usd=0.0042))
    cost = meta["cost_estimate"]
    assert cost is not None
    assert cost["value_usd"] == 0.0042
    assert cost["currency"] == "USD"
    assert cost["estimated"] is True
    assert cost["payg_value_cny"] == 0.03024
    assert cost["tokenplan_value_cny"] == 0.0222
    assert cost["tokenplan_cost_cny"] == 0.0222
    assert cost["tokenplan_capacity_cost_cny"] == 0.0222
    assert cost["tokenplan_credits_estimate"] == 3.18
    assert cost["tokenplan_monthly_fee_cny"] == 698.0
    assert cost["tokenplan_monthly_credits"] == 100_000


def test_build_meta_cost_is_null_not_zero_when_unpriced():
    """诚实铁律:定价缺失(cost=0 + unpriced 来源)→ cost_estimate=None,绝不填 0。"""
    meta = build_send_meta(_done_data(), _usage_summary(cost_usd=0.0, source="unpriced"))
    assert meta["cost_estimate"] is None
    # 但 usage(token 计数)仍在 —— 拿到了 token,只是没定价。
    assert meta["usage"] is not None
    assert meta["usage"]["input_tokens"] == 1500


def test_build_meta_no_usage_summary_yields_null_usage_and_cost():
    """一次 LLM 调用都没采集到 → usage/cost 全 None(不假造),但 done 里的 model/perf 仍出。"""
    meta = build_send_meta(_done_data(), None)
    assert meta["usage"] is None
    assert meta["cost_estimate"] is None
    assert meta["model"] == "qwen3.7-plus"  # done_data 仍提供 model
    assert meta["latency"]["total_ms"] == 4200


def test_build_meta_local_provider_reports_zero_cost_honestly():
    """本地 ollama 真·免费:cost_source=local_provider → 如实给 0.0(非误导)。"""
    summary = _usage_summary(cost_usd=0.0, source="local_provider")
    meta = build_send_meta(_done_data(), summary)
    assert meta["cost_estimate"] is not None
    assert meta["cost_estimate"]["value_usd"] == 0.0


def test_build_meta_multi_model_path_has_no_rounds():
    """多模型 done 无 llm_rounds → rounds=None,model 仍从 answer_model 取。"""
    done = {
        "conversation_id": 9,
        "message_id": 10,
        "elapsed_ms": 8000,
        "model": "商用三强",
        "answer_model": "商用三强",
        "mode": "multi_model",
    }
    meta = build_send_meta(done, None)
    assert meta["rounds"] is None
    assert meta["model"] == "商用三强"
    # perf 缺失 → total_ms 回退顶层 elapsed_ms,ttft None。
    assert meta["latency"] == {"total_ms": 8000, "ttft_ms": None}


def test_build_meta_never_raises_on_garbage():
    # fail-soft:non-dict 输入不炸。
    assert isinstance(build_send_meta(None, None), dict)
    assert isinstance(build_send_meta("nope", "nope"), dict)


# ---------------------------------------------------------------------------
# /agent/send 端点集成
# ---------------------------------------------------------------------------

def test_agent_send_response_carries_meta_with_model_and_usage(
    client, auth_user_and_headers, monkeypatch
):
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "答案"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": 55,
                "message_id": 66,
                "elapsed_ms": 3100,
                "llm_rounds": 1,
                "model": "qwen3.7-plus",
                "answer_model": "qwen3.7-plus",
                "tools_used": ["health_query"],
                "perf": {"total_ms": 3100, "llm_ttft_ms": 500},
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )
    # 在端点的 usage capture 上下文里回一个真实 usage summary(模拟 LLM 计费采集)。
    monkeypatch.setattr(
        "app.services.llm.usage_tracker.summarize_usage_capture",
        lambda: {
            "calls": 1,
            "prompt_tokens": 900,
            "completion_tokens": 300,
            "total_tokens": 1200,
            "cost_usd": 0.00054,
            "cost_estimated": True,
            "cost_sources": ["builtin:qwen3.7-plus"],
            "models": ["qwen3.7-plus"],
            "providers": ["tokenplan"],
        },
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "带 meta 的回合"},
    )

    assert res.status_code == 200
    body = res.json()
    # 老字段零变化。
    assert body["reply"] == "答案"
    assert body["conversation_id"] == 55
    assert body["message_id"] == 66
    assert body["mode"] == "agent"
    assert body["elapsed_ms"] == 3100
    # meta.model 有模型时非 None。
    meta = body["meta"]
    assert meta["model"] == "qwen3.7-plus"
    assert meta["rounds"] == 1
    assert meta["tools_used"] == ["health_query"]
    # usage 结构。
    assert meta["usage"]["input_tokens"] == 900
    assert meta["usage"]["output_tokens"] == 300
    # cost 结构(拿到定价 → 非 None)。
    assert meta["cost_estimate"]["value_usd"] == 0.00054
    # latency 结构。
    assert meta["latency"]["total_ms"] == 3100
    assert meta["latency"]["ttft_ms"] == 500


def test_agent_send_meta_cost_null_when_no_usage_captured(
    client, auth_user_and_headers, monkeypatch
):
    """没采集到 usage → meta.cost_estimate=None(诚实),但老字段与 meta.model 照常。"""
    _, headers = auth_user_and_headers

    async def fake_run_stream(self, **kwargs):
        yield {"event": "token", "data": {"content": "无成本回合"}}
        yield {
            "event": "done",
            "data": {
                "conversation_id": 1,
                "message_id": 2,
                "elapsed_ms": 120,
                "llm_rounds": 0,
                "model": "qwen3.6-flash",
                "answer_model": "qwen3.6-flash",
                "perf": {"total_ms": 120, "llm_ttft_ms": None},
            },
        }

    monkeypatch.setattr(
        "app.services.agent_executor.AgentExecutor.run_stream", fake_run_stream
    )
    monkeypatch.setattr(
        "app.services.llm.usage_tracker.summarize_usage_capture",
        lambda: None,
    )

    res = client.post(
        "/api/v1/agent/send",
        headers=headers,
        json={"message": "无 usage 采集"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["reply"] == "无成本回合"
    meta = body["meta"]
    assert meta["cost_estimate"] is None  # 诚实 null,不是 0
    assert meta["usage"] is None
    assert meta["model"] == "qwen3.6-flash"  # done 提供 model


def test_run_xiaoba_reads_model_and_cost_from_meta():
    """评测对接:run_xiaoba 从新 meta 读到 model / cost(此前 model=None、cost=None)。"""
    from evals.comparative.battery import Question
    from evals.comparative.run_xiaoba import _run_one

    def poster(message, conversation_id):
        return {
            "reply": f"回答:{message}",
            "conversation_id": 42,
            "mode": "agent",
            "elapsed_ms": 2000,
            "meta": {
                "model": "qwen3.7-plus",
                "rounds": 1,
                "usage": {"input_tokens": 800, "output_tokens": 200, "total_tokens": 1000, "calls": 1},
                "cost_estimate": {"value_usd": 0.0006, "currency": "USD", "estimated": True, "sources": []},
                "latency": {"total_ms": 2000, "ttft_ms": 400},
                "tools_used": ["health_query"],
            },
        }

    q = Question(
        id="q_meta",
        family="fact",
        prompt="镁有什么作用",
        requires_personal_data=False,
        scoring_notes="事实题,校验 meta 透出",
    )
    t = _run_one(q, poster)
    assert t.meta["model"] == "qwen3.7-plus"  # 不再是 None
    assert t.cost == 0.0006  # 从 meta.cost_estimate.value_usd 累加
    assert t.turns[0]["meta"]["usage"]["input_tokens"] == 800
    assert t.turns[0]["meta"]["cost_usd"] == 0.0006
