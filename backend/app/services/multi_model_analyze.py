"""Unified multi-model analysis client."""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class MultiModelAnalyzeClient:
    """Delegate multi-model analysis to the configured first-party LLM provider."""

    async def analyze(self, prompt: str) -> Dict[str, Any]:
        """Submit an analysis prompt and return the provider aggregation."""
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import set_caller

            set_caller("multi_model_analyze")
            provider = get_llm_provider()
            return await provider.multi_model_analyze(prompt)
        except Exception as e:
            logger.error("[multi-model] analysis failed: %s", e)
            return {
                "status": "error",
                "model_results": [],
                "aggregation": f"分析失败: {str(e)}",
            }
