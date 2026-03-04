"""LLM Provider 抽象基类 - 定义统一的 LLM 调用接口"""
import logging
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """
    LLM Provider 抽象基类

    所有 LLM 后端（OpenAI、Ollama、OpenClaw 等）都需要实现此接口。
    支持普通对话、流式对话、视觉分析和多模型分析。
    """

    # 子类必须覆盖此属性
    provider_name: str = "base"

    @abstractmethod
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
        发送聊天请求

        Args:
            messages: 消息列表，格式 [{"role": "system"|"user"|"assistant", "content": "..."}]
            model: 模型名称，None 则使用 provider 默认模型
            temperature: 温度参数 (0.0-2.0)
            max_tokens: 最大生成 token 数
            stream: 是否流式返回
            **kwargs: 额外参数（如 tools 用于 function calling）

        Returns:
            stream=False: 返回完整的响应字符串，或当 LLM 返回 tool_calls 时返回 dict
            stream=True: 返回 AsyncIterator[str]，逐 token yield
        """
        ...

    @abstractmethod
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
        带图片的聊天请求（视觉分析）

        Args:
            messages: 消息列表（最后一条 user 消息将附加图片）
            image_url: 图片 URL 或 base64 data URI（如 "data:image/jpeg;base64,..."）
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            **kwargs: 额外参数

        Returns:
            LLM 的文本响应
        """
        ...

    async def multi_model_analyze(
        self,
        prompt: str,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        多模型分析（可选实现）

        默认回退到单模型 chat 调用。仅 OpenClaw 等支持多模型聚合的 provider
        需要覆盖此方法。

        Args:
            prompt: 分析提示词
            **kwargs: 额外参数

        Returns:
            {
                "status": "completed" | "partial" | "timeout" | "error",
                "model_results": [...],
                "aggregation": "聚合结果文本"
            }
        """
        # 默认实现：回退到单模型 chat
        try:
            result = await self.chat(
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            return {
                "status": "completed",
                "model_results": [{"model": self.provider_name, "content": result}],
                "aggregation": result,
            }
        except Exception as e:
            logger.error(f"[{self.provider_name}] multi_model_analyze 回退失败: {e}")
            return {
                "status": "error",
                "model_results": [],
                "aggregation": f"分析失败: {e}",
            }

    @property
    def supports_multi_model(self) -> bool:
        """是否支持真正的多模型分析（默认 False）"""
        return False

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} provider_name={self.provider_name!r}>"
