"""OpenClaw 多模型分析客户端（向后兼容包装器）

NOTE: 新代码应使用 app.services.llm.get_llm_provider().multi_model_analyze()
此模块保留用于向后兼容。
"""
import logging
from typing import Dict, Any

from app.config import settings

logger = logging.getLogger(__name__)


class OpenClawAnalyzeClient:
    """OpenClaw 多模型分析客户端 - 委托给 LLM Provider"""

    async def analyze(self, prompt: str) -> Dict[str, Any]:
        """提交分析并等待结果。委托给统一的 LLM Provider。"""
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller
            set_caller("openclaw_analyze.multi_model")
            provider = get_llm_provider()
            return await provider.multi_model_analyze(prompt)
        except Exception as e:
            logger.error(f"[OpenClaw分析] 分析失败: {e}")
            return {
                "status": "error",
                "model_results": [],
                "aggregation": f"分析失败: {str(e)}",
            }
