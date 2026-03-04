"""验证 LLM 服务重构后仍正常工作"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestLLMHealthAnalyzerRefactored:
    """验证 LLMHealthAnalyzer 使用 LLM Provider"""

    @pytest.mark.asyncio
    async def test_analyze_with_prompt_uses_provider(self):
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="分析结果：一切正常")
        mock_provider.model = "gpt-4o-mini"

        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            result = await analyzer.analyze_with_prompt(
                system_prompt="你是健康分析师",
                user_prompt="分析我的数据",
            )
            assert result == "分析结果：一切正常"
            mock_provider.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_analyze_with_prompt_strips_markdown_json(self):
        """analyze_with_prompt 能正确去除 markdown 代码块"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value='```json\n{"key": "value"}\n```')
        mock_provider.model = "gpt-4o-mini"

        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            result = await analyzer.analyze_with_prompt(
                system_prompt="系统提示",
                user_prompt="用户提示",
            )
            assert result == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_analyze_with_prompt_raises_when_unavailable(self):
        """LLM 不可用时 analyze_with_prompt 抛出异常"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        with patch("app.services.llm_health_analyzer.get_llm_provider", side_effect=Exception("No config")):
            analyzer = LLMHealthAnalyzer()
            with pytest.raises(Exception, match="LLM 服务不可用"):
                await analyzer.analyze_with_prompt(
                    system_prompt="系统提示",
                    user_prompt="用户提示",
                )

    def test_is_available_with_provider(self):
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        mock_provider.model = "gpt-4o-mini"
        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.is_available() is True

    def test_is_available_without_provider(self):
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        with patch("app.services.llm_health_analyzer.get_llm_provider", side_effect=Exception("No config")):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.is_available() is False

    def test_model_attribute_from_provider(self):
        """model 属性应从 provider 获取"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        mock_provider.model = "gpt-4"
        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.model == "gpt-4"

    def test_model_fallback_when_provider_fails(self):
        """provider 初始化失败时 model 回退到默认值"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        with patch("app.services.llm_health_analyzer.get_llm_provider", side_effect=Exception("fail")):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.model == "gpt-4o-mini"
            assert analyzer._provider is None
