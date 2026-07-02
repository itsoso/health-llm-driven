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
from contextvars import ContextVar, Token
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 价格表: $/1M tokens (input, output). 找不到的模型回退到 0.0 (只算 token 不算钱).
# 来源: openai pricing 2026-04, qwen/openclaw 内部估算.
_MODEL_PRICING: Dict[str, tuple] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4-turbo": (10.00, 30.00),
    "qwen-vl-max": (1.50, 4.50),
    "openclaw:main": (0.20, 0.80),  # 估算
    "openclaw/main": (0.20, 0.80),
    "llama3": (0.0, 0.0),  # 本地 ollama 不计费
}

# 调用方上下文 — orchestrator / specialist / endpoint 可以通过 set_caller() 标注自己
_caller_ctx: ContextVar[Optional[str]] = ContextVar("llm_caller", default=None)
_user_id_ctx: ContextVar[Optional[int]] = ContextVar("llm_user_id", default=None)
_usage_capture_ctx: ContextVar[Optional[List[Dict[str, Any]]]] = ContextVar(
    "llm_usage_capture",
    default=None,
)
_MAX_CAPTURE_ITEMS = 20


def set_caller(caller: str, user_id: Optional[int] = None) -> None:
    """在调用 LLM 前调用, 标注本次调用归属哪个业务."""
    _caller_ctx.set(caller)
    if user_id is not None:
        _user_id_ctx.set(user_id)


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
        "calls": len(captured),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 8),
        "latency_ms": sum(latency_values) if latency_values else None,
        "failed_calls": sum(1 for item in captured if not item.get("success", True)),
        "models": models,
        "providers": providers,
        "items": captured[-_MAX_CAPTURE_ITEMS:],
    }


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


def _price_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pricing = _MODEL_PRICING.get(model) or _MODEL_PRICING.get(model.split(":")[0]) or (0.0, 0.0)
    in_price, out_price = pricing
    return (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000


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
) -> None:
    """写一条 LlmUsageLog (旁路, 失败只 log)."""
    prompt_tokens = _estimate_tokens(prompt_text, model)
    completion_tokens = _estimate_tokens(completion_text, model)
    cost = _price_usd(model, prompt_tokens, completion_tokens)
    resolved_caller = caller or _caller_ctx.get() or "unknown"
    resolved_user_id = user_id if user_id is not None else _user_id_ctx.get()
    entry = {
        "provider": provider,
        "model": model,
        "caller": resolved_caller,
        "user_id": resolved_user_id,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "cost_usd": round(cost, 8),
        "latency_ms": latency_ms,
        "success": bool(success),
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
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                success=1 if success else 0,
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
        if stream:
            # 流式不追踪 (会破坏 AsyncIterator 语义); 流式调用本身少
            return await original_chat(messages, model=model, temperature=temperature,
                                       max_tokens=max_tokens, stream=True, **kwargs)
        start = time.monotonic()
        success = True
        result = ""
        try:
            result = await original_chat(messages, model=model, temperature=temperature,
                                         max_tokens=max_tokens, stream=False, **kwargs)
            return result
        except Exception:
            success = False
            raise
        finally:
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
            record_usage(
                provider=provider.provider_name,
                model=actual_model,
                prompt_text=prompt_text,
                completion_text=completion_text,
                latency_ms=latency_ms,
                success=success,
            )

    provider.chat = chat_with_tracking

    original_chat_stream = getattr(provider, "chat_stream", None)
    if original_chat_stream is not None:
        async def chat_stream_with_tracking(messages, model=None, temperature=0.3,
                                            max_tokens=2000, tools=None, **kwargs):
            start = time.monotonic()
            success = True
            collected: List[str] = []
            try:
                async for evt in original_chat_stream(
                    messages, model=model, temperature=temperature,
                    max_tokens=max_tokens, tools=tools, **kwargs
                ):
                    if isinstance(evt, dict) and evt.get("type") == "content":
                        collected.append(evt.get("text") or "")
                    yield evt
            except Exception:
                success = False
                raise
            finally:
                latency_ms = int((time.monotonic() - start) * 1000)
                actual_model = (
                    model
                    or getattr(provider, "model", None)
                    or getattr(provider, "default_model", None)
                    or "unknown"
                )
                record_usage(
                    provider=provider.provider_name,
                    model=actual_model,
                    prompt_text=_messages_to_text(messages),
                    completion_text="".join(collected),
                    latency_ms=latency_ms,
                    success=success,
                )
        provider.chat_stream = chat_stream_with_tracking

    provider._usage_wrapped = True
    return provider
