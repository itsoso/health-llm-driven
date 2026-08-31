"""Build the additive observability `meta` envelope for /agent/send.

Background: the non-streaming /agent/send口子历史上只回 reply/conversation_id/
message_id/mode/elapsed_ms,把 AgentExecutor 已经算好的 model/rounds/perf 和
usage_tracker 采集的 token/cost 全丢了。评测 runner 因此记 model=None、cost 全空,
"成本只有商用十分之一"的论证拿不到每回合真实成本账。

本模块把两个现成来源拼成一个 **纯附加** 的 `meta`:
  1) `done_data` —— AgentExecutor `done` 事件已带 model / llm_rounds / tools_used /
     perf{total_ms, llm_ttft_ms}。
  2) `summarize_usage_capture()` 的返回 —— 需调用方在 `begin_usage_capture()` 上下文内
     跑完 executor 才有值(token / cost_usd / models / providers)。拿不到 → usage/cost 一律
     None(诚实:拿不到成本给 null,绝不填 0 误导)。

设计铁律:
- 纯附加。现有响应字段零变化,老客户端不读 `meta` 不炸。
- fail-loud on programmer error, fail-soft on missing data:字段缺失给 None,不假造。
- 不引入新依赖,不碰 agent_executor。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def _first_non_empty(*values: Any) -> Optional[str]:
    for v in values:
        s = str(v).strip() if v is not None else ""
        if s:
            return s
    return None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):  # bool 是 int 子类,显式排除
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _build_usage(usage_summary: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """把 usage_tracker 的 summarize_usage_capture() 结果压成客户端友好的 usage 块。

    没有采集到任何 LLM 调用(summary=None / 空)→ 返回 None(诚实:无数据即 null)。
    """
    if not isinstance(usage_summary, dict) or not usage_summary:
        return None
    prompt = _int_or_none(usage_summary.get("prompt_tokens"))
    completion = _int_or_none(usage_summary.get("completion_tokens"))
    total = _int_or_none(usage_summary.get("total_tokens"))
    calls = _int_or_none(usage_summary.get("calls"))
    # 一次 LLM 调用都没有 → 无 usage 可言。
    if not calls and prompt is None and completion is None:
        return None
    return {
        "input_tokens": prompt,
        "output_tokens": completion,
        "total_tokens": total,
        "calls": calls,
        "models": list(usage_summary.get("models") or []) if isinstance(usage_summary.get("models"), list) else [],
        "providers": list(usage_summary.get("providers") or []) if isinstance(usage_summary.get("providers"), list) else [],
        "items": list(usage_summary.get("items") or []) if isinstance(usage_summary.get("items"), list) else [],
    }


def _build_cost(usage_summary: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """从 usage summary 抽成本块。

    诚实规则:只有拿到 **真实定价**(cost_usd > 0,或来源明确非 unpriced)才给数字。
    - summary 缺失 / 无调用 → None。
    - 成本为 0 且来源里全是 unpriced(定价表里查不到该模型)→ None,绝不用 0 误导
      成本论证(0 会被读成"免费")。
    - 本地 provider(ollama)真·免费 → cost_source=local_provider,给 0.0(如实)。
    返回 {value_usd, currency, estimated, sources} 或 None。
    """
    if not isinstance(usage_summary, dict) or not usage_summary:
        return None
    cost_usd = usage_summary.get("cost_usd")
    tokenplan_cny = usage_summary.get("tokenplan_cost_cny")
    if not isinstance(cost_usd, (int, float)) and not isinstance(tokenplan_cny, (int, float)):
        return None
    sources = usage_summary.get("cost_sources")
    sources = [str(s) for s in sources] if isinstance(sources, list) else []
    tokenplan_source = str(usage_summary.get("tokenplan_cost_source") or "").strip().lower()
    tokenplan_priced = (
        isinstance(tokenplan_cny, (int, float))
        and float(tokenplan_cny) > 0
        and tokenplan_source
        and not tokenplan_source.startswith("unpriced")
    )
    if sources and all(source.strip().lower().startswith("unpriced") for source in sources):
        tokenplan_priced = False
    # 无正成本 + 无本地免费来源 = 定价缺失,诚实报 null。
    priced = (
        (isinstance(cost_usd, (int, float)) and float(cost_usd) > 0)
        or tokenplan_priced
        or any(s == "local_provider" for s in sources)
    )
    if not priced:
        return None
    return {
        "value_usd": round(float(cost_usd or 0.0), 8),
        "currency": "USD",
        "estimated": bool(usage_summary.get("cost_estimated", True)),
        "sources": sources,
        "payg_value_cny": round(float(
            usage_summary.get("tokenplan_payg_value_cny")
            or usage_summary.get("cost_cny")
            or 0.0
        ), 6),
        "tokenplan_value_cny": usage_summary.get("tokenplan_cost_cny"),
        "tokenplan_cost_cny": usage_summary.get("tokenplan_cost_cny"),
        "tokenplan_capacity_cost_cny": usage_summary.get("tokenplan_cost_cny"),
        "tokenplan_credits_estimate": usage_summary.get("tokenplan_credits_estimate"),
        "tokenplan_estimated": usage_summary.get("tokenplan_cost_estimated"),
        "tokenplan_source": usage_summary.get("tokenplan_cost_source"),
        "tokenplan_monthly_fee_cny": usage_summary.get("tokenplan_monthly_fee_cny"),
        "tokenplan_monthly_credits": usage_summary.get("tokenplan_monthly_credits"),
    }


def build_send_meta(
    done_data: Optional[Dict[str, Any]],
    usage_summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """组装 /agent/send 的 additive `meta`。

    Args:
        done_data: AgentExecutor `done` 事件的 data(model/llm_rounds/tools_used/perf 等)。
        usage_summary: `summarize_usage_capture()` 的返回(在 usage capture 上下文内取)。

    Returns:
        `meta` dict。缺失字段一律 None(诚实,不假造)。永不抛。
    """
    done = done_data if isinstance(done_data, dict) else {}
    perf = done.get("perf") if isinstance(done.get("perf"), dict) else {}

    # model:优先 done 里的 answer_model / model,其次 usage summary 里首个模型名。
    summary_models = usage_summary.get("models") if isinstance(usage_summary, dict) else None
    summary_model = summary_models[0] if isinstance(summary_models, list) and summary_models else None
    model = _first_non_empty(
        done.get("answer_model"),
        done.get("model"),
        done.get("selected_model"),
        summary_model,
    )

    # rounds:done 的 llm_rounds(工具循环轮数);多模型路径无此字段 → None。
    rounds = _int_or_none(done.get("llm_rounds"))

    # latency:优先从 run_stream 入口起算的新口径；旧回合回退原字段。
    total_ms = _int_or_none(perf.get("end_to_end_total_ms"))
    if total_ms is None:
        total_ms = _int_or_none(perf.get("total_ms"))
    if total_ms is None:
        total_ms = _int_or_none(done.get("elapsed_ms"))
    end_to_end_ttft_ms = _int_or_none(perf.get("end_to_end_ttft_ms"))
    latency = {
        "total_ms": total_ms,
        "ttft_ms": (
            end_to_end_ttft_ms
            if end_to_end_ttft_ms is not None
            else _int_or_none(perf.get("llm_ttft_ms"))
        ),
    }

    tools_used = done.get("tools_used")
    tools_used = list(tools_used) if isinstance(tools_used, list) else None

    return {
        "model": model,
        "rounds": rounds,
        "usage": _build_usage(usage_summary),
        "cost_estimate": _build_cost(usage_summary),
        "latency": latency,
        "tools_used": tools_used,
    }
