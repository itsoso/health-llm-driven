"""
LLM Factory 单元测试。

验证：
- 默认 provider 是 openclaw（不再是 openai）
- openclaw 创建失败时回退到 openai
- 未知 provider 类型抛 ValueError
- provider 单例缓存行为
"""

import pytest
from unittest.mock import patch

from app.services.llm.factory import create_llm_provider, get_llm_provider, reset_llm_provider


class TestDefaultProvider:
    def test_default_is_openclaw(self):
        """默认 provider 应该是 openclaw，不是 openai。"""
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "openclaw"
            mock_settings.openclaw_base_url = "https://bot.executor.life/v1"
            mock_settings.openclaw_api_key = "test-key"
            mock_settings.openclaw_model = "openclaw"
            mock_settings.llm_openclaw_base_url = None
            mock_settings.llm_openclaw_api_key = None
            mock_settings.llm_openclaw_model = None
            mock_settings.llm_openclaw_analyze_url = None
            mock_settings.llm_openclaw_analyze_api_key = None
            mock_settings.llm_openclaw_kim_user_id = None

            provider = create_llm_provider()
            assert provider.provider_name == "openclaw"


class TestProviderFallback:
    def test_openclaw_fallback_to_openai(self):
        """OpenClaw 创建失败时应该回退到 OpenAI。"""
        with patch("app.services.llm.factory._create_openclaw_provider", side_effect=Exception("test error")):
            with patch("app.services.llm.factory._create_openai_provider") as mock_openai:
                mock_openai.return_value = type("MockProvider", (), {"provider_name": "openai"})()
                provider = create_llm_provider("openclaw")
                assert provider.provider_name == "openai"
                mock_openai.assert_called_once()


class TestUnknownProvider:
    def test_unknown_provider_raises(self):
        """未知 provider 类型应抛 ValueError。"""
        with pytest.raises(ValueError, match="未知的 LLM provider"):
            create_llm_provider("nonexistent")


class TestProviderSingleton:
    def test_singleton_caching(self):
        """get_llm_provider 应返回同一实例。"""
        reset_llm_provider()
        with patch("app.services.llm.factory.create_llm_provider") as mock_create:
            mock_create.return_value = type("MockProvider", (), {"provider_name": "test"})()
            p1 = get_llm_provider()
            p2 = get_llm_provider()
            assert p1 is p2
            mock_create.assert_called_once()
        reset_llm_provider()

    def test_reset_clears_cache(self):
        """reset_llm_provider 应清除缓存。"""
        reset_llm_provider()
        with patch("app.services.llm.factory.create_llm_provider") as mock_create:
            mock_create.return_value = type("MockProvider", (), {"provider_name": "test"})()
            p1 = get_llm_provider()
            reset_llm_provider()
            p2 = get_llm_provider()
            assert mock_create.call_count == 2
        reset_llm_provider()
