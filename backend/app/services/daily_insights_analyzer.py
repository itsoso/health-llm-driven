"""The daily-insights surface has a fixed, fail-closed Token Plan route."""
import logging

from app.config import settings
from app.services.llm.factory import create_tokenplan_provider
from app.services.llm.model_registry import get_model
from app.services.llm_health_analyzer import LLMHealthAnalyzer

logger = logging.getLogger(__name__)


def analysis_route(use_llm=True):
    entry = get_model(settings.tokenplan_model)
    model = entry.model if entry and entry.provider == 'tokenplan' else settings.tokenplan_model
    return {'version': 1, 'provider': 'tokenplan' if use_llm else 'rules',
            'model': model if use_llm else None}


def recommendations_cache_matches(result, use_llm=True):
    """Reject legacy/model-mismatched and failed AI results at both cache layers."""
    if not isinstance(result, dict):
        return False
    for name in ('one_day', 'seven_day'):
        period = result.get(name)
        if not isinstance(period, dict) or period.get('_analysis_route') != analysis_route(use_llm):
            return False
        if use_llm and period.get('status') != 'no_data':
            analysis = period.get('llm_analysis') or {}
            if analysis.get('available') is not True or analysis.get('error') or analysis.get('provider') != 'tokenplan':
                return False
    return True


class TokenPlanHealthAnalyzer(LLMHealthAnalyzer):
    def __init__(self):
        self._provider = None
        self.model = analysis_route()['model']
        try:
            self._provider = create_tokenplan_provider()
            self.model = self._provider.model
        except Exception as exc:
            logger.warning('Daily insights Token Plan unavailable error_type=%s', type(exc).__name__)

    async def analyze_daily_health(self, *args, **kwargs):
        result = await super().analyze_daily_health(*args, **kwargs)
        if not result.get('available') or result.get('error'):
            return {'available': False, 'provider': 'tokenplan', 'model': self.model,
                    'error': '阿里云 Token Plan 分析暂不可用，请稍后重试或检查服务配置'}
        return {**result, 'provider': 'tokenplan', 'model': self.model}
