"""Ollama Provider - 通过 REST API 调用本地 Ollama 服务"""
import json
import logging
from typing import AsyncIterator, Dict, Any, List, Optional, Union

import httpx

from app.services.llm.base import LLMProvider
from app.services.ai_consent import require_local_or_consented_ai

logger = logging.getLogger(__name__)

# Ollama 默认超时配置
DEFAULT_TIMEOUT = 120.0  # Ollama 本地推理可能较慢


class OllamaProvider(LLMProvider):
    """
    Ollama Provider

    通过 httpx 调用 Ollama 的 REST API (http://localhost:11434)。
    支持文本对话和视觉模型（如 llava）。

    API 文档: https://github.com/ollama/ollama/blob/main/docs/api.md
    """

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

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
        调用 Ollama /api/chat 接口

        stream=False: 返回完整文本
        stream=True: 返回 AsyncIterator 逐 token yield (NDJSON)
        """
        use_model = model or self.model

        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if stream:
            return self._stream_chat(payload)

        require_local_or_consented_ai(self.base_url)
        url = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Ollama 非流式响应格式: {"message": {"role": "assistant", "content": "..."}, ...}
        content = data.get("message", {}).get("content", "")
        return content.strip()

    async def _stream_chat(self, payload: Dict[str, Any]) -> AsyncIterator[str]:
        """流式调用 Ollama，解析 NDJSON 逐行返回"""
        require_local_or_consented_ai(self.base_url)
        url = f"{self.base_url}/api/chat"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content
                        # Ollama 用 "done": true 标记结束
                        if chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"[Ollama] 无法解析 NDJSON 行: {line[:100]}")
                        continue

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
        带图片的对话（Ollama 视觉模型如 llava）

        Ollama 使用 messages[].images 字段传递 base64 图片数据。
        """
        use_model = model or self.model
        vision_messages = self._build_vision_messages(messages, image_url)
        require_local_or_consented_ai(self.base_url)

        payload = {
            "model": use_model,
            "messages": vision_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        url = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data.get("message", {}).get("content", "")
        return content.strip()

    @staticmethod
    def _build_vision_messages(
        messages: List[Dict[str, Any]], image_url: str
    ) -> List[Dict[str, Any]]:
        """
        构建 Ollama 视觉消息格式

        Ollama 的视觉模型使用 messages[].images 字段，值为 base64 字符串列表。
        格式: {"role": "user", "content": "描述这张图片", "images": ["<base64>"]}
        """
        import base64

        # 提取 base64 数据
        image_data = image_url
        if image_url.startswith("data:"):
            # data:image/jpeg;base64,/9j/4AAQ... -> 提取 base64 部分
            parts = image_url.split(",", 1)
            if len(parts) == 2:
                image_data = parts[1]

        vision_messages = []
        last_user_idx = -1

        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user_idx = i

        for i, msg in enumerate(messages):
            if i == last_user_idx:
                vision_messages.append({
                    "role": "user",
                    "content": msg.get("content", ""),
                    "images": [image_data],
                })
            else:
                vision_messages.append(msg.copy())

        return vision_messages
