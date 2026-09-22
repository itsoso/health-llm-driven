"""Unified multi-model analysis client."""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def is_completed_analysis(result: Any) -> bool:
    """Only a completed, nonempty text result may be published as analysis."""
    return (isinstance(result, dict) and result.get("status") == "completed"
            and isinstance(result.get("aggregation"), str)
            and bool(result["aggregation"].strip()))


class MultiModelAnalyzeClient:
    """Delegate multi-model analysis to the configured first-party LLM provider."""

    async def analyze(self, prompt: str, *, user_id: int) -> Dict[str, Any]:
        """Submit an analysis prompt and return the provider aggregation."""
        try:
            from app.services.llm import get_llm_provider
            from app.services.llm.usage_tracker import background_ai_scope

            with background_ai_scope("multi_model_analyze", user_id=user_id):
                provider = get_llm_provider()
                result = await provider.multi_model_analyze(prompt)
            if is_completed_analysis(result):
                return result
            logger.warning("[multi-model] analysis did not produce a completed text result")
        except Exception as e:
            logger.error("[multi-model] analysis failed error_type=%s", type(e).__name__)
        return {
            "status": "error",
            "model_results": [],
            "aggregation": "分析暂未完成，请稍后重试。",
        }
