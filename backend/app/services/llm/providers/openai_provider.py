"""OpenAI 兼容 Provider - 支持 OpenAI、DeepSeek、vLLM 等 OpenAI API 兼容服务"""
import asyncio
import logging
from typing import AsyncIterator, Dict, Any, List, Optional, Union

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


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
        message = response.choices[0].message
        if message.tool_calls:
            return {
                "content": message.content,
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
        content = message.content or ""
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

        # OpenAI SDK 的 streaming 是同步迭代器，需要在线程中运行
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
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

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
