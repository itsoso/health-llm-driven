"""OpenClaw Provider - 调用 OpenClaw AI 对话服务 + 多模型分析"""
import asyncio
import json
import logging
from typing import AsyncIterator, Dict, Any, List, Optional, Union

import httpx

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# 默认超时和轮询配置
DEFAULT_CHAT_TIMEOUT = 240.0
DEFAULT_POLL_INTERVAL = 10  # 秒
DEFAULT_MAX_POLL_ATTEMPTS = 18  # 最多 180 秒


class OpenClawProvider(LLMProvider):
    """
    OpenClaw Provider

    通过 OpenAI 兼容格式的 HTTP API 进行对话，
    并支持独有的多模型分析（submit + poll 模式）。
    """

    provider_name = "openclaw"

    def __init__(
        self,
        base_url: str = "https://bot.executor.life/v1",
        api_key: Optional[str] = None,
        model: str = "openclaw:main",
        analyze_url: Optional[str] = None,
        analyze_api_key: Optional[str] = None,
        kim_user_id: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        # 多模型分析配置（可选）
        self.analyze_url = analyze_url
        self.analyze_api_key = analyze_api_key
        self.kim_user_id = kim_user_id

    def _get_headers(self) -> Dict[str, str]:
        """构建请求头"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

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
        调用 OpenClaw Chat API（OpenAI 兼容格式）

        stream=False: 返回完整文本
        stream=True: 返回 AsyncIterator，解析 SSE 逐 token yield
        """
        use_model = model or self.model

        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(payload)

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=DEFAULT_CHAT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip()

    async def _stream_chat(self, payload: Dict[str, Any]) -> AsyncIterator[str]:
        """SSE 流式调用 OpenClaw"""
        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=DEFAULT_CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST", url, json=payload, headers=self._get_headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
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
        带图片的对话

        OpenClaw 兼容 OpenAI 的 vision 消息格式。
        """
        vision_messages = self._build_vision_messages(messages, image_url)
        use_model = model or self.model

        payload = {
            "model": use_model,
            "messages": vision_messages,
        }

        url = f"{self.base_url}/chat/completions"
        async with httpx.AsyncClient(timeout=DEFAULT_CHAT_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            resp.raise_for_status()
            data = resp.json()

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip()

    @staticmethod
    def _build_vision_messages(
        messages: List[Dict[str, Any]], image_url: str
    ) -> List[Dict[str, Any]]:
        """构建 OpenAI 格式的 vision 消息"""
        vision_messages = []
        last_user_idx = -1

        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                last_user_idx = i

        for i, msg in enumerate(messages):
            if i == last_user_idx:
                text_content = msg.get("content", "")
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

    @property
    def supports_multi_model(self) -> bool:
        """是否支持多模型分析（需要 analyze_url 已配置）"""
        return bool(self.analyze_url)

    async def multi_model_analyze(
        self,
        prompt: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        OpenClaw 多模型分析：提交任务 → 轮询结果

        如果 analyze_url 未配置，回退到基类的单模型实现。
        """
        if not self.analyze_url:
            logger.info("[OpenClaw] analyze_url 未配置，回退到单模型分析")
            return await super().multi_model_analyze(prompt, **kwargs)

        # 提交分析任务
        batch_id = await self._submit_analyze(prompt)
        if not batch_id:
            return {
                "status": "error",
                "model_results": [],
                "aggregation": "提交分析失败",
            }

        # 轮询结果
        return await self._poll_analyze(batch_id)

    async def _submit_analyze(self, prompt: str) -> Optional[str]:
        """提交多模型分析请求，返回 batch_id"""
        payload = {
            "prompt": prompt,
            "kim_user_id": self.kim_user_id or "default",
            "api_key": self.analyze_api_key or "",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.analyze_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    batch_id = data.get("batch_id")
                    logger.info(f"[OpenClaw 多模型分析] 提交成功: batch_id={batch_id}")
                    return batch_id
                else:
                    logger.error(f"[OpenClaw 多模型分析] 提交失败: {data}")
                    return None
        except Exception as e:
            logger.error(f"[OpenClaw 多模型分析] 提交异常: {e}")
            return None

    async def _poll_analyze(self, batch_id: str) -> Dict[str, Any]:
        """轮询多模型分析结果"""
        # 从 analyze_url 推导 status_url
        # 例: https://base.executor.life/api/openclaw/analyze
        #  -> https://base.executor.life/api/openclaw/status
        status_base = self.analyze_url.replace("/analyze", "/status")
        url = f"{status_base}/{batch_id}"

        for attempt in range(1, DEFAULT_MAX_POLL_ATTEMPTS + 1):
            await asyncio.sleep(DEFAULT_POLL_INTERVAL)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()

                status = data.get("status", "")
                logger.info(
                    f"[OpenClaw 多模型分析] 轮询 {attempt}/{DEFAULT_MAX_POLL_ATTEMPTS}: "
                    f"status={status}"
                )

                if status in ("completed", "partial"):
                    return {
                        "status": status,
                        "model_results": data.get("model_results", []),
                        "aggregation": data.get("aggregation", ""),
                    }
            except Exception as e:
                logger.warning(
                    f"[OpenClaw 多模型分析] 轮询异常 ({attempt}): {e}"
                )

        return {
            "status": "timeout",
            "model_results": [],
            "aggregation": "分析超时，请稍后查看结果。",
        }
