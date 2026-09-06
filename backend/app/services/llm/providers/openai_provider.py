"""OpenAI 兼容 Provider - 支持 OpenAI、DeepSeek、vLLM 等 OpenAI API 兼容服务"""
import asyncio
import inspect
import logging
import threading
from typing import AsyncIterator, Dict, Any, List, Optional, Union

from app.services.llm.base import LLMProvider
from app.services.ai_consent import require_ai_consent

logger = logging.getLogger(__name__)


# ── 底层 client 连接复用池 (Phase-2 rank4: 消灭 per-round TLS 握手税) ──────────────
# create_provider_for_user 每回合新建 provider → 过去每回合也新建一个 OpenAI 客户端 →
# 新 httpx 连接池 → 每轮付一次 TCP+TLS 握手 (~50-300ms × 2-3 轮/回合)。这里把**原始
# 客户端 / 连接池**按 client 级 kwarg (base_url + api_key + 未来任何差异项) 做 module
# 级 memoize:同 (base_url, api_key) 的 provider 复用同一个底层客户端和连接池,握手只付
# 一次。provider WRAPPER (usage_tracker/pii_scrub/per-user 参数) 仍 per-call 创建,
# 路由在**请求参数** (model=) 不在连接层 —— "用户切换立即生效" 契约不动。
# OpenAI / AsyncOpenAI 客户端跨协程/线程共享是安全的 (官方保证)。
_SYNC_CLIENT_CACHE: Dict[tuple, Any] = {}
# 流式路径 (Phase-2 rank6) 用 AsyncOpenAI + `async for`,不再同步迭代阻塞 event loop;
# 异步客户端同样按 (base_url, api_key) memoize (与同步池共用同一把锁)。
_ASYNC_CLIENT_CACHE: Dict[tuple, Any] = {}
_CLIENT_CACHE_LOCK = threading.Lock()


# ── 每调用硬超时 (2026-07-15: 治无界 LLM 轮冻结) ─────────────────────────────────
# openai SDK 默认 timeout=600s + max_retries=2 → 单个卡住的请求最坏 600s×3 才放弃,
# 生产实测出现过 362s 整回合冻结 (弱模型/代理挂住)。这里给共享客户端设显式硬边界:
# read 帽按当日真实 llm_ms 分布定 —— 合法单轮 p95≈56s、最慢合法 88s,120s 留 ~36% 余量
# **不误杀正常慢合成**;而卡住的请求在 read 帽处被斩,连既有 provider failover 重路由。
# max_retries=1:留一次瞬时网络抖动重试,但不再 ×3 放大冻结。connect 帽 10s 快速判死端点。
# 仅当 caller 未显式传 timeout/max_retries 时套用 (per-call 覆盖优先)。
_DEFAULT_HTTP_TIMEOUT: Any = None  # 惰性构造 (import httpx 放函数内, 避免顶层依赖顺序问题)
_DEFAULT_MAX_RETRIES = 1


def _apply_client_defaults(client_kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """返回补齐硬超时/重试上限默认值的新 dict (不改 caller 原 dict)。"""
    global _DEFAULT_HTTP_TIMEOUT
    kw = dict(client_kwargs)
    if "timeout" not in kw:
        if _DEFAULT_HTTP_TIMEOUT is None:
            import httpx

            _DEFAULT_HTTP_TIMEOUT = httpx.Timeout(
                connect=10.0, read=120.0, write=30.0, pool=10.0
            )
        kw["timeout"] = _DEFAULT_HTTP_TIMEOUT
    kw.setdefault("max_retries", _DEFAULT_MAX_RETRIES)
    return kw


def _client_cache_key(client_kwargs: Dict[str, Any]) -> tuple:
    """稳定 memo key:client 级 kwarg 全参与 (排序去顺序敏感)。

    只有构造底层客户端的参数进 key (api_key / base_url / 任何未来 client 级 kwarg)。
    `model` 不是 client 级参数 (它随每次请求传),故同 key 的不同模型共享连接。
    """
    return tuple(sorted((str(k), str(v)) for k, v in client_kwargs.items()))


def _get_shared_sync_client(client_kwargs: Dict[str, Any]):
    """按 client_kwargs memoize 一个共享的同步 OpenAI 客户端 (含 httpx 连接池)。"""
    key = _client_cache_key(client_kwargs)
    client = _SYNC_CLIENT_CACHE.get(key)
    if client is not None:
        return client
    with _CLIENT_CACHE_LOCK:
        client = _SYNC_CLIENT_CACHE.get(key)
        if client is None:
            from openai import OpenAI

            client = OpenAI(**_apply_client_defaults(client_kwargs))
            _SYNC_CLIENT_CACHE[key] = client
            logger.info(
                "[OpenAI Provider] 新建共享同步客户端 base_url=%s (连接池复用)",
                client_kwargs.get("base_url", "default"),
            )
    return client


def _get_shared_async_client(client_kwargs: Dict[str, Any]):
    """按 client_kwargs memoize 一个共享的异步 AsyncOpenAI 客户端 (含 httpx 连接池)。

    流式合成/工具轮走异步客户端 + `async for`,让 inter-chunk 网络等待 (~80ms @
    12-13 tok/s) 不再霸占 event loop —— 一条在飞流不再拖住其它回合的 SSE flush。
    """
    key = _client_cache_key(client_kwargs)
    client = _ASYNC_CLIENT_CACHE.get(key)
    if client is not None:
        return client
    with _CLIENT_CACHE_LOCK:
        client = _ASYNC_CLIENT_CACHE.get(key)
        if client is None:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(**_apply_client_defaults(client_kwargs))
            _ASYNC_CLIENT_CACHE[key] = client
            logger.info(
                "[OpenAI Provider] 新建共享异步客户端 base_url=%s (连接池复用)",
                client_kwargs.get("base_url", "default"),
            )
    return client


async def _create_stream(create, create_kwargs: Dict[str, Any]):
    """调 chat.completions.create(stream=True) 并统一 await:

    - AsyncOpenAI: create(...) 返回 coroutine → await 得 AsyncStream;
    - 测试 fake / 老式同步 client: create(...) 直接返回同步迭代器 → 原样返回。
    """
    result = create(**create_kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


async def _aiter_stream(response) -> AsyncIterator[Any]:
    """把底层 stream 统一成 async 迭代。

    生产恒 AsyncStream (走 __aiter__ = 非阻塞异步迭代);同步迭代器 (测试 fake) 走
    普通 for —— 测试里 chunk 已全部物化,无网络等待,不会阻塞。
    """
    if hasattr(response, "__aiter__"):
        async for chunk in response:
            yield chunk
    else:
        for chunk in response:
            yield chunk


def reset_client_cache() -> None:
    """清空 module 级 client 复用池 (同步 + 异步;测试隔离用,生产无需调用)。"""
    with _CLIENT_CACHE_LOCK:
        _SYNC_CLIENT_CACHE.clear()
        _ASYNC_CLIENT_CACHE.clear()


def _report_usage_from_response(usage: Any) -> None:
    """把 OpenAI 兼容返回体的 usage 真值上报给 usage_tracker(fail-soft)。

    cached tokens 兼容 OpenAI/DeepSeek/DashScope(百炼)的
    usage.prompt_tokens_details.cached_tokens 字段。
    """
    try:
        if usage is None:
            return
        from app.services.llm.usage_tracker import report_api_usage

        details = getattr(usage, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", None) if details is not None else None
        report_api_usage(
            prompt_tokens=getattr(usage, "prompt_tokens", None),
            completion_tokens=getattr(usage, "completion_tokens", None),
            cached_tokens=cached,
        )
    except Exception:  # noqa: BLE001 — 观测层绝不断业务
        pass


def _merge_include_usage(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """流式请求带上 stream_options.include_usage(调用方已显式传则不覆盖)。"""
    merged = dict(kwargs)
    if "stream_options" not in merged:
        merged["stream_options"] = {"include_usage": True}
    return merged


def _apply_thinking_controls(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """把 thinking_budget / enable_thinking(DashScope/qwen 思考控制)折进 extra_body。

    OpenAI SDK 不认识这两个字段,当顶层 kwarg 传会 TypeError;必须走 extra_body
    (compatible-mode 顶层放置,探针实证生效——见 scripts/probe_qwen_thinking_budget.py)。
    kwargs 里没这两个键则原样返回(零影响)。原地 pop 掉这两个键,避免它们继续以
    未知 kwarg 流进 client.chat.completions.create() 触发 TypeError。

    调用方(agent_executor)已按 ModelEntry.supports_thinking_budget 门控,只对**探针
    验证过**的 qwen 系 tokenplan 模型传入;非 qwen 模型永不带这两个 kwarg → extra_body
    不受影响。thinking_budget 需要思考开着才谈得上封顶,故默认补 enable_thinking=True。
    """
    thinking_budget = kwargs.pop("thinking_budget", None)
    enable_thinking = kwargs.pop("enable_thinking", None)
    if thinking_budget is None and enable_thinking is None:
        return kwargs
    extra_body = dict(kwargs.get("extra_body") or {})
    if enable_thinking is not None:
        extra_body["enable_thinking"] = bool(enable_thinking)
    if thinking_budget is not None:
        extra_body.setdefault("enable_thinking", True)
        extra_body["thinking_budget"] = int(thinking_budget)
    kwargs["extra_body"] = extra_body
    return kwargs


def _model_supports_explicit_cache(model_name: Optional[str]) -> bool:
    """按 model 字符串反查注册表是否支持显式缓存。fail-closed → False (未知/查不到即不贴)。

    镜像 agent_executor._provider_is_non_streaming 的反查模式:直接遍历 MODELS, 匹配
    entry.model 或 entry.id。绝不抛 (观测/门控层不断主链路)。"""
    if not model_name:
        return False
    try:
        from app.services.llm.model_registry import MODELS

        for entry in MODELS:
            if entry.model == model_name or entry.id == model_name:
                return bool(getattr(entry, "supports_explicit_cache", False))
        return False
    except Exception:  # noqa: BLE001 — 查不到注册表宁可不贴 (纯降级, 无功能影响)
        return False


def _maybe_mark_prompt_cache(
    messages: List[Dict[str, Any]], kwargs: Dict[str, Any], model: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """DashScope 显式上下文缓存 (Phase-2 rank3): 按 role/position 在 append-only 边界注入
    cache_control ephemeral 断点。

    调用方 (agent_executor._maybe_apply_prompt_cache_markers) 已 flag + ModelEntry
    .supports_explicit_cache 门控, 只对**探针验证过**的 DashScope 模型置 `prompt_cache_markers`;
    OpenAI SDK 不认识该 kwarg, 当顶层传会 TypeError, 所以这里**必须 pop 掉**。没这个键
    (= flag 关 / 模型未验证) 时原样返回 messages → payload 逐字节不变。

    **最后一英里 fail-closed (failover 残留洞根治):** executor 按**主选 effective model**
    置 markers 信号, 但该 kwargs 可能被原样带给 failover 到的 **fallback provider (不同
    model)**。这里按**本次实际调用的 model** (= chat/chat_stream 的 `use_model = model or
    self.model`, 对主选 provider 和任何 fallback provider 都成立) 再查一次注册表 —— 不支持
    显式缓存的模型 (含未知/查不到) 绝不贴 cache_control (贴到不支持的端点可能被拒, 恰好打断
    兜底链)。这是覆盖 primary + 所有 fallback 路径的单一 chokepoint。

    layout 值可为 True (默认布局: system + history_prefix) 或 dict (显式 layout knobs, 供
    探针实验静态前缀 / tail 断点)。变换是纯函数 (prompt_cache.apply_cache_markers), 返回
    **新** list, 绝不改调用方的 messages。"""
    layout = kwargs.pop("prompt_cache_markers", None)
    if not layout:
        return messages
    if not _model_supports_explicit_cache(model):
        return messages
    from app.services.llm.prompt_cache import apply_cache_markers

    if isinstance(layout, dict):
        return apply_cache_markers(messages, **layout)
    return apply_cache_markers(messages)


def _extract_reasoning_delta(delta: Any) -> Optional[str]:
    """从流式 delta 取 reasoning_content(DashScope/qwen 思考流增量)。

    OpenAI SDK 的 ChoiceDelta 不认识这个字段,会落到直接属性或 model_extra 上
    (探针 scripts/probe_qwen_thinking_budget.py 实证两种形态都出现过)。非 qwen /
    思考关时永远为 None → 调用方零行为变更。仅返回增量文本,绝不并入答案 content。
    """
    r = getattr(delta, "reasoning_content", None)
    if r:
        return r
    extra = getattr(delta, "model_extra", None)
    if isinstance(extra, dict):
        r = extra.get("reasoning_content")
        if r:
            return r
    return None


class OpenAIProvider(LLMProvider):
    """
    OpenAI 兼容 Provider

    通过 openai SDK 调用，支持自定义 base_url 以兼容：
    - OpenAI 官方 API
    - DeepSeek API
    - vLLM / LiteLLM 本地部署
    - 任何 OpenAI API 兼容的服务
    """

    provider_name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client = None  # 懒加载 (同步 — 非流式 chat/vision)
        self._async_client = None  # 懒加载 (异步 — 流式 chat_stream/_stream_chat)

    def _client_kwargs(self) -> Dict[str, Any]:
        """构造底层客户端的 kwarg (进 memo key 的全部 client 级参数)。"""
        client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        return client_kwargs

    def _get_client(self):
        """懒加载同步 OpenAI 客户端 (module 级按 base_url+api_key 复用底层连接池)。"""
        if self._client is None:
            self._client = _get_shared_sync_client(self._client_kwargs())
        return self._client

    def _get_async_client(self):
        """懒加载异步 AsyncOpenAI 客户端 (流式路径专用, 同样按 base_url+api_key 复用)。"""
        if self._async_client is None:
            self._async_client = _get_shared_async_client(self._client_kwargs())
        return self._async_client

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        **kwargs,
    ) -> Union[str, AsyncIterator[str]]:
        """
        调用 OpenAI Chat Completions API

        stream=False: 同步调用包装为异步，返回完整文本
        stream=True: 返回 AsyncIterator 逐 token yield
        """
        use_model = model or self.model
        return_metadata = bool(kwargs.pop("return_metadata", False))
        # thinking_budget / enable_thinking → extra_body(仅调用方门控过的 qwen 模型会带)
        kwargs = _apply_thinking_controls(kwargs)
        # 显式上下文缓存 (rank3): 门控过时在 append-only 边界打 cache_control 断点。
        # 必须在 stream 分支前做 —— pop 掉 prompt_cache_markers, 并让 stream=True 下发已
        # 标记的 messages 给 _stream_chat (它不再重复标: kwarg 已被 pop)。flag 关时透传。
        messages = _maybe_mark_prompt_cache(messages, kwargs, use_model)

        if stream:
            return self._stream_chat(messages, use_model, temperature, max_tokens, **kwargs)

        require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
        client = self._get_client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=use_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            **kwargs,
        )
        _report_usage_from_response(getattr(response, "usage", None))
        choice = response.choices[0]
        finish_reason = choice.finish_reason
        message = choice.message
        if message.tool_calls:
            result = {
                "content": message.content,
                "finish_reason": finish_reason,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
            return result
        content = message.content or ""
        if return_metadata:
            return {
                "content": content.strip(),
                "finish_reason": finish_reason,
            }
        return content.strip()

    async def _stream_chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式调用，逐 token yield"""
        require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
        # AsyncOpenAI + `async for`:inter-chunk 网络等待不再霸占 event loop(旧代码
        # 用 asyncio.to_thread 创建后 `for chunk in response` 同步迭代,每个 ~80ms 等待
        # 阻塞整个 loop)。include_usage:让最后一个 chunk 带回 usage 真值(不兼容代理→
        # 重试一次不带)。
        client = self._get_async_client()
        base_kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        auto_usage = "stream_options" not in kwargs
        try:
            response = await _create_stream(
                client.chat.completions.create,
                {**base_kwargs, **_merge_include_usage(kwargs)},
            )
        except Exception as e:  # noqa: BLE001
            # 只在 stream_options 是我们自动加的情况下退回重试(不带它=与历史请求
            # 完全一致);错误文案不可靠(各代理不一),不做文案匹配。
            if not auto_usage:
                raise
            logger.info("[OpenAI Provider] 带 stream_options 创建失败,退回无 usage 流式: %s", e)
            require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
            response = await _create_stream(
                client.chat.completions.create,
                {**base_kwargs, **kwargs},
            )

        async for chunk in _aiter_stream(response):
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                _report_usage_from_response(usage)
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """结构化流式调用 — 实时 yield content delta，同时正确累积 tool_calls。

        与 chat(stream=True) 不同:后者只 yield 纯文本 delta、丢失 tool_calls,
        无法支撑 agent 的 function-calling 循环。本方法 yield 结构化事件:

        - {"type": "content", "text": <delta>}   每个内容增量 (实时)
        - {"type": "tool_calls", "tool_calls": [...openai-format...]}  流结束时若有
        - {"type": "finish", "finish_reason": <reason>}  最后

        OpenAI SDK 的 streaming 是同步迭代器,在线程里跑 (同 _stream_chat)。
        """
        require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
        use_model = model or self.model
        # return_metadata 是 chat() 的参数,流式不接受,丢弃避免传给 OpenAI SDK
        kwargs.pop("return_metadata", None)
        # thinking_budget / enable_thinking → extra_body(仅调用方门控过的 qwen 模型会带)
        kwargs = _apply_thinking_controls(kwargs)
        # 显式上下文缓存 (rank3): 门控过时在 append-only 边界打 cache_control 断点; pop 掉
        # prompt_cache_markers 避免作为未知顶层 kwarg 流进 create()。flag 关时透传 (逐字节不变)。
        messages = _maybe_mark_prompt_cache(messages, kwargs, use_model)
        # AsyncOpenAI + `async for`:合成/工具决策轮的 inter-chunk 网络等待不再阻塞
        # 整个 event loop(旧代码 to_thread 创建后同步 `for chunk in response`)。
        client = self._get_async_client()

        create_kwargs: Dict[str, Any] = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            create_kwargs["tools"] = tools
        auto_usage = "stream_options" not in kwargs
        create_kwargs.update(_merge_include_usage(kwargs))

        try:
            response = await _create_stream(client.chat.completions.create, create_kwargs)
        except Exception as e:  # noqa: BLE001
            # 同 _stream_chat:只在 stream_options 为自动附加时退回(与历史请求一致)。
            if not auto_usage:
                raise
            logger.info("[OpenAI Provider] 带 stream_options 创建失败,退回无 usage 流式: %s", e)
            create_kwargs.pop("stream_options", None)
            require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
            response = await _create_stream(client.chat.completions.create, create_kwargs)

        # tool_calls 分片按 index 累积: 同一个 tool_call 的 id / name / arguments
        # 会跨多个 chunk 到达,arguments 是字符串拼接。
        tool_acc: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None

        async for chunk in _aiter_stream(response):
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                _report_usage_from_response(usage)
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            # 思考流(reasoning_content): qwen3.7-max 首个可见 token 前先吐 reasoning
            # 增量(实证首个 reasoning delta @ ~1.7s vs 首个 content @ ~35.8s)。作为
            # **独立**事件产出,供 executor 把死气变成活的思考进度。绝不并入答案 content。
            reasoning = _extract_reasoning_delta(delta)
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}

            content = getattr(delta, "content", None)
            if content:
                yield {"type": "content", "text": content}

            delta_tool_calls = getattr(delta, "tool_calls", None)
            if delta_tool_calls:
                for tc in delta_tool_calls:
                    idx = tc.index if tc.index is not None else 0
                    slot = tool_acc.setdefault(
                        idx,
                        {"id": None, "type": "function",
                         "function": {"name": None, "arguments": ""}},
                    )
                    if tc.id:
                        slot["id"] = tc.id
                    if getattr(tc, "type", None):
                        slot["type"] = tc.type
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            slot["function"]["name"] = fn.name
                        if getattr(fn, "arguments", None):
                            slot["function"]["arguments"] += fn.arguments

        if tool_acc:
            ordered = [tool_acc[i] for i in sorted(tool_acc.keys())]
            yield {"type": "tool_calls", "tool_calls": ordered}

        yield {"type": "finish", "finish_reason": finish_reason}

    async def chat_with_vision(
        self,
        messages: List[Dict[str, Any]],
        image_url: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs,
    ) -> str:
        """
        带图片的对话（Vision API）

        将最后一条 user 消息的 content 改为包含文本和图片的列表格式。
        """
        # 构建 vision 消息
        require_ai_consent(destination=self.base_url or "https://api.openai.com/v1")
        vision_messages = self._build_vision_messages(messages, image_url)

        use_model = model or self.model
        client = self._get_client()

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=use_model,
            messages=vision_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        content = response.choices[0].message.content or ""
        return content.strip()

    @staticmethod
    def _build_vision_messages(
        messages: List[Dict[str, Any]], image_url: str
    ) -> List[Dict[str, Any]]:
        """
        构建视觉消息格式

        找到最后一条 user 消息，将其 content 改为包含 text + image_url 的列表
        """
        vision_messages = []
        last_user_idx = -1

        # 找到最后一条 user 消息的索引
        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user_idx = i

        for i, msg in enumerate(messages):
            if i == last_user_idx:
                # 将 user 消息转为 vision 格式
                text_content = msg.get("content", "")
                if isinstance(text_content, list):
                    # 已经是多部分格式，追加图片
                    parts = list(text_content)
                    parts.append({
                        "type": "image_url",
                        "image_url": {"url": image_url, "detail": "high"},
                    })
                    vision_messages.append({"role": "user", "content": parts})
                else:
                    vision_messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": str(text_content)},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url, "detail": "high"},
                            },
                        ],
                    })
            else:
                vision_messages.append(msg.copy())

        return vision_messages
