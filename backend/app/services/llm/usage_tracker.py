"""
LLM 用量/成本追踪.

设计:
- 用 tiktoken 估算 prompt + completion token 数 (provider 不返回 usage 时的回退)
- 价格表硬编码常用模型 ($/M tokens)
- 写入 llm_usage_logs (旁路, fail-soft, 出错只 log 不抛)
- 通过 wrap_provider() 把任意 LLMProvider.chat 包一层, 调用方零改动
"""
from __future__ import annotations

import logging
import time
import json
import re
from dataclasses import dataclass
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional, Tuple

from app.services.llm.tokenplan_cost import estimate_tokenplan_cost

logger = logging.getLogger(__name__)

# 默认估算表: $/1M tokens (input, output). 真实账单以 provider / TokenPlan 后台为准。
# 可用 LLM_MODEL_PRICING_JSON 覆盖,避免价格漂移时必须发版。
_MODEL_PRICING: Dict[str, Tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "qwen3.7-plus": (0.40, 1.20),
    "qwen3.7-max": (1.20, 3.60),
    "qwen3.6-plus": (0.40, 1.20),
    "qwen3.6-flash": (0.05, 0.20),
    "qwen-vl-max": (1.50, 4.50),
    "deepseek-v4-pro": (0.75, 2.40),
    "deepseek-v4-flash": (0.10, 0.30),
    "deepseek-v3.2": (0.30, 0.90),
    "kimi-k2.7-code": (0.80, 2.40),
    "kimi-k2.6": (0.50, 1.50),
    "kimi-k2.5": (0.50, 1.50),
    "glm-5.2": (0.30, 0.90),
    "glm-5.1": (0.25, 0.75),
    "glm-5": (0.20, 0.60),
    "minimax-m2.5": (0.80, 2.40),
    "commercial/gpt-5.5": (10.00, 30.00),
    "llama3": (0.0, 0.0),  # 本地 ollama 不计费
}
_PROVIDER_DEFAULT_PRICING: Dict[str, Tuple[float, float]] = {
    "tokenplan": (0.50, 1.50),
    "openai": (0.50, 1.50),
    "openai-proxy": (0.50, 1.50),
    "langbridge-proxy": (2.00, 6.00),
}
_LOCAL_PROVIDERS = {"ollama", "local"}


@dataclass(frozen=True)
class UsageCostEstimate:
    cost_usd: float
    cost_cny: float
    input_usd_per_million: float
    output_usd_per_million: float
    estimated: bool
    source: str
    pricing_unit: str = "USD_PER_1M_TOKENS"

# 调用方上下文 — orchestrator / specialist / endpoint 可以通过 set_caller() 标注自己
_caller_ctx: ContextVar[Optional[str]] = ContextVar("llm_caller", default=None)
_user_id_ctx: ContextVar[Optional[int]] = ContextVar("llm_user_id", default=None)
_run_id_ctx: ContextVar[Optional[str]] = ContextVar("llm_run_id", default=None)
_recovery_depth_ctx: ContextVar[int] = ContextVar("llm_recovery_depth", default=0)
_usage_capture_ctx: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "llm_usage_capture",
    default=None,
)
_MAX_CAPTURE_ITEMS = 20


class LLMBudgetExceeded(RuntimeError):
    """Raised before a paid LLM call would exceed the configured month quota."""

    error_code = "llm_budget_exceeded"


def _enforce_monthly_token_quota(
    *,
    provider: str,
    model: Optional[str],
    messages: List[Dict[str, Any]],
    max_tokens: int,
) -> None:
    """Fail closed when an explicit production TokenPlan quota is exhausted.

    ``0`` means the operator has not configured a quota and is intentionally
    handled by release readiness rather than silently treated as unlimited.
    The guard is a preflight estimate, so it protects against ordinary runaway
    calls; production budget dashboards still remain the billing source of truth.
    """
    try:
        from app.config import settings

        if str(provider or "").strip().lower() != "tokenplan":
            return
        quota = int(getattr(settings, "tokenplan_monthly_token_quota", 0) or 0)
        if quota <= 0:
            return

        from datetime import datetime, timezone
        from sqlalchemy import func
        from app.database import SessionLocal
        from app.models.llm_usage import LlmUsageLog

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with SessionLocal() as db:
            used = int(
                db.query(func.coalesce(func.sum(LlmUsageLog.total_tokens), 0))
                .filter(
                    LlmUsageLog.provider == "tokenplan",
                    LlmUsageLog.created_at >= month_start,
                )
                .scalar()
                or 0
            )

        estimated_request = _estimate_tokens(_messages_to_text(messages), model or "gpt-4o-mini")
        estimated_request += max(0, int(max_tokens or 0))
        if used + estimated_request > quota:
            logger.error(
                "[LLM Budget] monthly token quota exceeded provider=tokenplan used=%s "
                "estimate=%s quota=%s",
                used,
                estimated_request,
                quota,
            )
            raise LLMBudgetExceeded("monthly token quota exceeded")
    except LLMBudgetExceeded:
        raise
    except Exception as exc:
        from app.config import settings

        if (settings.app_env or "").strip().lower() == "production":
            logger.error("[LLM Budget] quota guard unavailable; blocking production call: %s", exc)
            raise LLMBudgetExceeded("llm budget guard unavailable") from exc
        logger.warning("[LLM Budget] quota guard unavailable in non-production: %s", exc)


def set_caller(caller: str, user_id: Optional[int] = None) -> None:
    """在调用 LLM 前调用, 标注本次调用归属哪个业务."""
    _caller_ctx.set(caller)
    if user_id is not None:
        _user_id_ctx.set(user_id)


def set_run_id(run_id: Optional[str]) -> Token[Optional[str]]:
    """Bind all LLM calls in the current request to a trace/run id."""
    return _run_id_ctx.set(run_id)


def clear_run_id(token: Token[Optional[str]]) -> None:
    _run_id_ctx.reset(token)


def begin_usage_capture() -> Token[Optional[List[Dict[str, Any]]]]:
    """Start per-request LLM usage capture for surfacing a brief client profile."""
    return _usage_capture_ctx.set([])


def end_usage_capture(token: Token[Optional[List[Dict[str, Any]]]]) -> None:
    """End per-request capture and restore the previous context."""
    _usage_capture_ctx.reset(token)


def _capture_usage_entry(entry: Dict[str, Any]) -> None:
    bucket = _usage_capture_ctx.get()
    if bucket is None:
        return
    bucket.append(dict(entry))


# ── provider 真值 usage 通道(2026-07-08 token 优化 #1)──────────────────
# 历史:record_usage 永远用 tiktoken/len 估算,provider 返回的 usage 被丢弃 →
# 缓存命中率与真实 token 全盲,一切缓存优化都无法验收。
# 通道:provider 在拿到 API usage 后调 report_api_usage()(同一 asyncio task 的
# ContextVar);record_usage 消费即用真值(token_source='api'),没有才退估算。
_api_usage_ctx: ContextVar[Optional[Dict[str, Any]]] = ContextVar("llm_api_usage", default=None)


def report_api_usage(
    prompt_tokens: Optional[int],
    completion_tokens: Optional[int],
    cached_tokens: Optional[int] = None,
) -> None:
    """Provider 拿到 API 返回的 usage 后上报(fail-soft,绝不抛)。"""
    try:
        if prompt_tokens is None and completion_tokens is None:
            return
        _api_usage_ctx.set({
            "prompt_tokens": int(prompt_tokens or 0),
            "completion_tokens": int(completion_tokens or 0),
            "cached_tokens": int(cached_tokens) if cached_tokens is not None else None,
        })
    except Exception:  # noqa: BLE001 — 观测层绝不断业务
        pass


def _consume_api_usage() -> Optional[Dict[str, Any]]:
    """读取并清空本 task 的 API usage(一次调用一次消费,防串到下一次)。"""
    usage = _api_usage_ctx.get()
    if usage is not None:
        _api_usage_ctx.set(None)
    return usage


def summarize_usage_capture() -> Optional[Dict[str, Any]]:
    """Return a privacy-safe summary of the current request's LLM calls."""
    items = _usage_capture_ctx.get()
    if not items:
        return None

    captured = [dict(item) for item in items]
    prompt_tokens = sum(int(item.get("prompt_tokens") or 0) for item in captured)
    completion_tokens = sum(int(item.get("completion_tokens") or 0) for item in captured)
    total_tokens = sum(int(item.get("total_tokens") or 0) for item in captured)
    cost_usd = sum(float(item.get("cost_usd") or 0.0) for item in captured)
    cost_cny = sum(float(item.get("cost_cny") or 0.0) for item in captured)
    tokenplan_items = [
        item for item in captured
        if isinstance(item.get("tokenplan_cost_cny"), (int, float))
    ]
    tokenplan_credits = sum(float(item.get("tokenplan_credits_estimate") or 0.0) for item in tokenplan_items)
    tokenplan_cost_cny = sum(float(item.get("tokenplan_cost_cny") or 0.0) for item in tokenplan_items)
    tokenplan_payg_value_cny = sum(
        float(item.get("tokenplan_payg_value_cny") or 0.0) for item in tokenplan_items
    )
    tokenplan_sources = sorted({
        str(item.get("tokenplan_cost_source") or "").strip()
        for item in tokenplan_items
        if str(item.get("tokenplan_cost_source") or "").strip()
    })
    latency_values = [
        int(item["latency_ms"])
        for item in captured
        if isinstance(item.get("latency_ms"), int)
    ]

    models: List[str] = []
    providers: List[str] = []
    for item in captured:
        model = str(item.get("model") or "").strip()
        provider = str(item.get("provider") or "").strip()
        if model and model not in models:
            models.append(model)
        if provider and provider not in providers:
            providers.append(provider)

    return {
        "run_id": _run_id_ctx.get(),
        "calls": len(captured),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 8),
        "cost_cny": round(cost_cny, 6),
        "cost_estimated": any(bool(item.get("cost_estimated")) for item in captured),
        "cost_sources": sorted({
            str(item.get("cost_source") or "").strip()
            for item in captured
            if str(item.get("cost_source") or "").strip()
        }),
        "tokenplan_credits_estimate": round(tokenplan_credits, 6) if tokenplan_items else None,
        "tokenplan_cost_cny": round(tokenplan_cost_cny, 6) if tokenplan_items else None,
        "tokenplan_payg_value_cny": round(tokenplan_payg_value_cny, 6) if tokenplan_items else None,
        "tokenplan_cost_estimated": any(
            bool(item.get("tokenplan_cost_estimated", True)) for item in tokenplan_items
        ) if tokenplan_items else None,
        "tokenplan_cost_source": tokenplan_sources[0] if len(tokenplan_sources) == 1 else (
            "mixed" if tokenplan_sources else None
        ),
        "tokenplan_cost_sources": tokenplan_sources,
        "tokenplan_monthly_fee_cny": tokenplan_items[0].get("tokenplan_monthly_fee_cny") if tokenplan_items else None,
        "tokenplan_monthly_credits": tokenplan_items[0].get("tokenplan_monthly_credits") if tokenplan_items else None,
        "latency_ms": sum(latency_values) if latency_values else None,
        "failed_calls": sum(1 for item in captured if not item.get("success", True)),
        "models": models,
        "providers": providers,
        "items": captured[-_MAX_CAPTURE_ITEMS:],
    }


def sum_captured_cached_tokens() -> Optional[int]:
    """当前 capture 桶内所有调用的 cached_tokens 之和(无桶 → None)。

    仅统计 provider 真值上报的 cached_tokens(token_source='api';估算调用为 None,记 0)。
    供 rank11 shadow worker 观测分段调用的显式缓存命中(begin_usage_capture 起一个隔离桶,
    分段 gather 子任务按引用共享该 list 就地 append,gather 后本函数汇总)。纯读,绝不抛。"""
    items = _usage_capture_ctx.get()
    if items is None:
        return None
    return sum(int(item.get("cached_tokens") or 0) for item in items)


def _estimate_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """tiktoken 估算 token 数, 失败回退到 len(text) / 4."""
    if not text:
        return 0
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except KeyError:
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _messages_to_text(messages: List[Dict[str, Any]]) -> str:
    """把 messages 拼成估算 token 用的纯文本."""
    parts = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            # vision messages: [{type: text, text: ...}, {type: image_url, ...}]
            for c in content:
                if isinstance(c, dict) and c.get("type") == "text":
                    parts.append(c.get("text", ""))
        elif content is not None:
            parts.append(json.dumps(content, ensure_ascii=False))
    return "\n".join(parts)


def _normalize_price_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _parse_pricing_pair(value: Any) -> Optional[Tuple[float, float]]:
    try:
        if isinstance(value, (list, tuple)) and len(value) >= 2:
            return float(value[0]), float(value[1])
        if isinstance(value, dict):
            input_price = (
                value.get("input")
                if "input" in value
                else value.get("input_usd_per_million", value.get("prompt"))
            )
            output_price = (
                value.get("output")
                if "output" in value
                else value.get("output_usd_per_million", value.get("completion"))
            )
            if input_price is not None and output_price is not None:
                return float(input_price), float(output_price)
    except (TypeError, ValueError):
        return None
    return None


def _pricing_overrides() -> Dict[str, Tuple[float, float]]:
    try:
        from app.config import settings

        raw = getattr(settings, "llm_model_pricing_json", None)
    except Exception:
        raw = None
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        logger.warning("[LLM Usage] LLM_MODEL_PRICING_JSON 解析失败,使用内置估算表: %s", exc)
        return {}
    if not isinstance(parsed, dict):
        return {}

    overrides: Dict[str, Tuple[float, float]] = {}
    for key, value in parsed.items():
        pair = _parse_pricing_pair(value)
        if pair:
            overrides[_normalize_price_key(key)] = pair
        elif isinstance(value, dict):
            default_pair = _parse_pricing_pair(value.get("default"))
            if default_pair:
                overrides[f"{_normalize_price_key(key)}:*"] = default_pair
            for nested_key, nested_value in value.items():
                if nested_key == "default":
                    continue
                nested_pair = _parse_pricing_pair(nested_value)
                if nested_pair:
                    overrides[_normalize_price_key(nested_key)] = nested_pair
    return overrides


def _builtin_pricing_for(provider: str, model: str) -> Tuple[Tuple[float, float], str]:
    provider_key = _normalize_price_key(provider)
    model_key = _normalize_price_key(model)
    if provider_key in _LOCAL_PROVIDERS:
        return (0.0, 0.0), "local_provider"

    candidates = [
        model_key,
        model_key.split(":", 1)[0],
        model_key.split("/", 1)[0],
    ]
    for key in candidates:
        if key in _MODEL_PRICING:
            return _MODEL_PRICING[key], f"builtin:{key}"

    if model_key.startswith("qwen") and "flash" in model_key:
        return (0.05, 0.20), "builtin_family:qwen_flash"
    if model_key.startswith("qwen") and any(word in model_key for word in ("max", "pro")):
        return (1.20, 3.60), "builtin_family:qwen_reasoning"
    if model_key.startswith("qwen"):
        return (0.40, 1.20), "builtin_family:qwen_balanced"
    if model_key.startswith("deepseek") and any(word in model_key for word in ("pro", "reason")):
        return (0.75, 2.40), "builtin_family:deepseek_reasoning"
    if model_key.startswith("deepseek") and "flash" in model_key:
        return (0.10, 0.30), "builtin_family:deepseek_flash"
    if model_key.startswith("deepseek"):
        return (0.30, 0.90), "builtin_family:deepseek_balanced"
    if model_key.startswith("kimi"):
        return (0.50, 1.50), "builtin_family:kimi"
    if model_key.startswith("glm"):
        return (0.30, 0.90), "builtin_family:glm"
    if model_key.startswith("minimax"):
        return (0.80, 2.40), "builtin_family:minimax"
    if model_key.startswith("gpt-"):
        return (0.50, 1.50), "builtin_family:gpt_unknown"
    if provider_key in _PROVIDER_DEFAULT_PRICING:
        return _PROVIDER_DEFAULT_PRICING[provider_key], f"provider_default:{provider_key}"
    return (0.0, 0.0), "unpriced"


def estimate_usage_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> UsageCostEstimate:
    provider_key = _normalize_price_key(provider)
    model_key = _normalize_price_key(model)
    overrides = _pricing_overrides()
    override_keys = [f"{provider_key}:{model_key}", model_key, f"{provider_key}:*"]
    pricing: Optional[Tuple[float, float]] = None
    source = ""
    for key in override_keys:
        if key in overrides:
            pricing = overrides[key]
            source = f"env:{key}"
            break
    if pricing is None:
        pricing, source = _builtin_pricing_for(provider, model)

    input_price, output_price = pricing
    cost_usd = (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000
    try:
        from app.config import settings

        usd_to_cny = float(getattr(settings, "llm_cost_usd_to_cny", 7.2) or 0.0)
    except Exception:
        usd_to_cny = 7.2
    return UsageCostEstimate(
        cost_usd=cost_usd,
        cost_cny=cost_usd * usd_to_cny,
        input_usd_per_million=input_price,
        output_usd_per_million=output_price,
        estimated=source != "local_provider",
        source=source,
    )


def _price_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    return estimate_usage_cost("", model, prompt_tokens, completion_tokens).cost_usd


def _compact_error_message(error: BaseException | str | None, *, max_len: int = 500) -> Optional[str]:
    if error is None:
        return None
    text = str(error).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    return text[:max_len]


def _pick_error_field(error: BaseException | str | None, field: str) -> Optional[str]:
    if error is None:
        return None
    for attr in (field, f"error_{field}"):
        value = getattr(error, attr, None)
        if value:
            return str(value)[:64]
    text = str(error)
    # Handles both Python-dict-ish and JSON-ish upstream error payloads.
    patterns = [
        rf"['\"]{re.escape(field)}['\"]\s*:\s*['\"]([^'\"]+)['\"]",
        rf"\b{re.escape(field)}=([A-Za-z0-9_.:-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)[:64]
    return None


def record_usage(
    provider: str,
    model: str,
    prompt_text: str,
    completion_text: str,
    *,
    caller: Optional[str] = None,
    user_id: Optional[int] = None,
    latency_ms: Optional[int] = None,
    success: bool = True,
    error_type: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    error_class: Optional[str] = None,
    recovery_action: Optional[str] = None,
    recovery_model: Optional[str] = None,
    run_id: Optional[str] = None,
) -> None:
    """写一条 LlmUsageLog (旁路, 失败只 log). API 真值优先, tiktoken 估算兜底."""
    api_usage = _consume_api_usage()
    cached_tokens: Optional[int] = None
    if api_usage is not None:
        prompt_tokens = api_usage["prompt_tokens"]
        completion_tokens = api_usage["completion_tokens"]
        cached_tokens = api_usage.get("cached_tokens")
        token_source = "api"
    else:
        prompt_tokens = _estimate_tokens(prompt_text, model)
        completion_tokens = _estimate_tokens(completion_text, model)
        token_source = "estimate"
    cost = estimate_usage_cost(provider, model, prompt_tokens, completion_tokens)
    tokenplan_cost = estimate_tokenplan_cost(
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cached_tokens=cached_tokens,
    )
    resolved_caller = caller or _caller_ctx.get() or "unknown"
    resolved_user_id = user_id if user_id is not None else _user_id_ctx.get()
    resolved_run_id = run_id if run_id is not None else _run_id_ctx.get()
    entry = {
        "provider": provider,
        "model": model,
        "caller": resolved_caller,
        "user_id": resolved_user_id,
        "run_id": resolved_run_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cached_tokens": cached_tokens,
        "token_source": token_source,
        "cost_usd": round(cost.cost_usd, 8),
        "cost_cny": round(cost.cost_cny, 6),
        "cost_estimated": cost.estimated,
        "cost_source": cost.source,
        "pricing_unit": cost.pricing_unit,
        "input_usd_per_million": cost.input_usd_per_million,
        "output_usd_per_million": cost.output_usd_per_million,
        "tokenplan_credits_estimate": round(tokenplan_cost.credits, 6) if tokenplan_cost else None,
        "tokenplan_cost_cny": round(tokenplan_cost.cost_cny, 6) if tokenplan_cost else None,
        "tokenplan_payg_value_cny": round(tokenplan_cost.payg_value_cny, 6) if tokenplan_cost else None,
        "tokenplan_cost_estimated": tokenplan_cost.estimated if tokenplan_cost else None,
        "tokenplan_cost_source": tokenplan_cost.source if tokenplan_cost else None,
        "tokenplan_monthly_fee_cny": tokenplan_cost.monthly_fee_cny if tokenplan_cost else None,
        "tokenplan_monthly_credits": tokenplan_cost.monthly_credits if tokenplan_cost else None,
        "latency_ms": latency_ms,
        "success": bool(success),
        "error_class": error_class,
        "error_type": error_type,
        "error_code": error_code,
        "error_message": error_message,
        "recovery_action": recovery_action,
        "recovery_model": recovery_model,
    }
    _capture_usage_entry(entry)

    try:
        from app.database import SessionLocal
        from app.models.llm_usage import LlmUsageLog

        if resolved_caller == "unknown":
            import traceback
            stack = "".join(traceback.format_stack(limit=8))
            logger.warning(f"[LLM Usage] caller=unknown, model={model}, "
                           f"tokens={prompt_tokens}+{completion_tokens}\nstack:\n{stack}")

        with SessionLocal() as db:
            row = LlmUsageLog(
                provider=provider,
                model=model,
                caller=resolved_caller,
                user_id=resolved_user_id,
                run_id=resolved_run_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cached_tokens=cached_tokens,
                token_source=token_source,
                cost_usd=cost.cost_usd,
                tokenplan_credits_estimate=tokenplan_cost.credits if tokenplan_cost else None,
                tokenplan_cost_cny=tokenplan_cost.cost_cny if tokenplan_cost else None,
                tokenplan_payg_value_cny=tokenplan_cost.payg_value_cny if tokenplan_cost else None,
                tokenplan_cost_estimated=(1 if tokenplan_cost.estimated else 0) if tokenplan_cost else None,
                tokenplan_cost_source=tokenplan_cost.source if tokenplan_cost else None,
                tokenplan_monthly_fee_cny=tokenplan_cost.monthly_fee_cny if tokenplan_cost else None,
                tokenplan_monthly_credits=tokenplan_cost.monthly_credits if tokenplan_cost else None,
                latency_ms=latency_ms,
                success=1 if success else 0,
                error_class=error_class,
                error_type=error_type,
                error_code=error_code,
                error_message=error_message,
                recovery_action=recovery_action,
                recovery_model=recovery_model,
            )
            db.add(row)
            db.commit()
    except Exception as e:
        logger.warning(f"[LLM Usage] 写日志失败 (旁路, 不影响业务): {e}")


def wrap_provider(provider):
    """
    把 LLMProvider 实例的 chat() 包一层 usage 追踪.
    返回原 provider (就地修改 chat 方法).
    """
    if getattr(provider, "_usage_wrapped", False):
        return provider

    original_chat = getattr(provider, "chat", None)
    if original_chat is None:
        # Mock / 测试 provider 没实现 chat — 直接跳过
        return provider

    async def chat_with_tracking(messages, model=None, temperature=0.7, max_tokens=2000, stream=False, **kwargs):
        _enforce_monthly_token_quota(
            provider=getattr(provider, "provider_name", ""),
            model=model or getattr(provider, "model", None),
            messages=messages,
            max_tokens=max_tokens,
        )
        if stream:
            # 流式不追踪 (会破坏 AsyncIterator 语义); 流式调用本身少
            return await original_chat(messages, model=model, temperature=temperature,
                                       max_tokens=max_tokens, stream=True, **kwargs)
        start = time.monotonic()
        success = True
        result = ""
        caught_error: BaseException | None = None
        primary_recorded = False
        try:
            result = await original_chat(messages, model=model, temperature=temperature,
                                         max_tokens=max_tokens, stream=False, **kwargs)
            return result
        except Exception as exc:
            success = False
            caught_error = exc
            actual_model = (
                model
                or getattr(provider, "model", None)
                or getattr(provider, "default_model", None)
                or "unknown"
            )
            if _recovery_depth_ctx.get() <= 0:
                from app.config import settings
                from app.services.llm.recovery import (
                    diagnose_llm_error,
                    pick_recovery_model_id,
                    try_recover_chat,
                )

                diagnosis = diagnose_llm_error(exc)
                recovery_model = None
                if getattr(settings, "llm_auto_recovery_enabled", False) and diagnosis.recoverable:
                    recovery_model = pick_recovery_model_id(
                        diagnosis,
                        primary_provider=getattr(provider, "provider_name", None),
                        primary_model=actual_model,
                    )
                if recovery_model:
                    latency_ms = int((time.monotonic() - start) * 1000)
                    record_usage(
                        provider=provider.provider_name,
                        model=actual_model,
                        prompt_text=_messages_to_text(messages),
                        completion_text="",
                        latency_ms=latency_ms,
                        success=False,
                        error_class=diagnosis.error_class,
                        error_type=_pick_error_field(exc, "type"),
                        error_code=_pick_error_field(exc, "code"),
                        error_message=_compact_error_message(exc),
                        recovery_action="fallback_attempted",
                        recovery_model=recovery_model,
                    )
                    primary_recorded = True

                recovery_depth_token = _recovery_depth_ctx.set(_recovery_depth_ctx.get() + 1)
                try:
                    ok, recovered, _recovery_model, _diagnosis = await try_recover_chat(
                        exc,
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        primary_provider=getattr(provider, "provider_name", None),
                        primary_model=actual_model,
                        kwargs=dict(kwargs),
                        recovery_model_id=recovery_model,
                    )
                finally:
                    _recovery_depth_ctx.reset(recovery_depth_token)
                if ok:
                    return recovered
            raise
        finally:
            if not primary_recorded:
                latency_ms = int((time.monotonic() - start) * 1000)
                actual_model = (
                    model
                    or getattr(provider, "model", None)
                    or getattr(provider, "default_model", None)
                    or "unknown"
                )
                prompt_text = _messages_to_text(messages)
                # result 可能是 str 或 dict (tool_calls), 后者只记 0 completion tokens
                completion_text = result if isinstance(result, str) else ""
                error_class = None
                if caught_error is not None:
                    from app.services.llm.recovery import diagnose_llm_error

                    error_class = diagnose_llm_error(caught_error).error_class
                record_usage(
                    provider=provider.provider_name,
                    model=actual_model,
                    prompt_text=prompt_text,
                    completion_text=completion_text,
                    latency_ms=latency_ms,
                    success=success,
                    error_class=error_class,
                    error_type=_pick_error_field(caught_error, "type") if caught_error else None,
                    error_code=_pick_error_field(caught_error, "code") if caught_error else None,
                    error_message=_compact_error_message(caught_error) if caught_error else None,
                )

    provider.chat = chat_with_tracking

    original_chat_stream = getattr(provider, "chat_stream", None)
    if original_chat_stream is not None:
        async def chat_stream_with_tracking(messages, model=None, temperature=0.3,
                                            max_tokens=2000, tools=None, **kwargs):
            start = time.monotonic()
            success = True
            collected: List[str] = []
            caught_error: BaseException | None = None
            try:
                async for evt in original_chat_stream(
                    messages, model=model, temperature=temperature,
                    max_tokens=max_tokens, tools=tools, **kwargs
                ):
                    if isinstance(evt, dict) and evt.get("type") == "content":
                        collected.append(evt.get("text") or "")
                    yield evt
            except Exception as exc:
                success = False
                caught_error = exc
                raise
            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                actual_model = (
                    model
                    or getattr(provider, "model", None)
                    or getattr(provider, "default_model", None)
                    or "unknown"
                )
                error_class = None
                if caught_error is not None:
                    from app.services.llm.recovery import diagnose_llm_error

                    error_class = diagnose_llm_error(caught_error).error_class
                record_usage(
                    provider=provider.provider_name,
                    model=actual_model,
                    prompt_text=_messages_to_text(messages),
                    completion_text="".join(collected),
                    latency_ms=latency_ms,
                    success=success,
                    error_class=error_class,
                    error_type=_pick_error_field(caught_error, "type") if caught_error else None,
                    error_code=_pick_error_field(caught_error, "code") if caught_error else None,
                    error_message=_compact_error_message(caught_error) if caught_error else None,
                )
        provider.chat_stream = chat_stream_with_tracking

    provider._usage_wrapped = True
    return provider
