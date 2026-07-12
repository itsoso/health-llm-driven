"""OpenAI 兼容 Provider - 支持 OpenAI、DeepSeek、vLLM 等 OpenAI API 兼容服务"""
import asyncio
import logging
from typing import AsyncIterator, Dict, Any, List, Optional, Union

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


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
        self._client = None  # 懒加载

    def _get_client(self):
        """懒加载 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url
            self._client = OpenAI(**client_kwargs)
            logger.info(
                f"[OpenAI Provider] 客户端初始化完成, "
                f"base_url={self.base_url or 'default'}, model={self.model}"
            )
        return self._client

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

        if stream:
            return self._stream_chat(messages, use_model, temperature, max_tokens, **kwargs)

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
        client = self._get_client()

        # OpenAI SDK 的 streaming 是同步迭代器，需要在线程中运行。
        # include_usage:让最后一个 chunk 带回 usage 真值(不兼容的代理→重试一次不带)。
        auto_usage = "stream_options" not in kwargs
        try:
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **_merge_include_usage(kwargs),
            )
        except Exception as e:  # noqa: BLE001
            # 只在 stream_options 是我们自动加的情况下退回重试(不带它=与历史请求
            # 完全一致);错误文案不可靠(各代理不一),不做文案匹配。
            if not auto_usage:
                raise
            logger.info("[OpenAI Provider] 带 stream_options 创建失败,退回无 usage 流式: %s", e)
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                **kwargs,
            )

        # response 是一个同步迭代器 (Stream)，包装为异步
        for chunk in response:
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
        use_model = model or self.model
        # return_metadata 是 chat() 的参数,流式不接受,丢弃避免传给 OpenAI SDK
        kwargs.pop("return_metadata", None)
        # thinking_budget / enable_thinking → extra_body(仅调用方门控过的 qwen 模型会带)
        kwargs = _apply_thinking_controls(kwargs)
        client = self._get_client()

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
            response = await asyncio.to_thread(
                client.chat.completions.create, **create_kwargs
            )
        except Exception as e:  # noqa: BLE001
            # 同 _stream_chat:只在 stream_options 为自动附加时退回(与历史请求一致)。
            if not auto_usage:
                raise
            logger.info("[OpenAI Provider] 带 stream_options 创建失败,退回无 usage 流式: %s", e)
            create_kwargs.pop("stream_options", None)
            response = await asyncio.to_thread(
                client.chat.completions.create, **create_kwargs
            )

        # tool_calls 分片按 index 累积: 同一个 tool_call 的 id / name / arguments
        # 会跨多个 chunk 到达,arguments 是字符串拼接。
        tool_acc: Dict[int, Dict[str, Any]] = {}
        finish_reason: Optional[str] = None

        for chunk in response:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                _report_usage_from_response(usage)
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason

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
