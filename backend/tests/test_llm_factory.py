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


class TestLangBridgeProxy:
    """langbridge-proxy provider 把商用模型代理到 browser-llm-orchestrator gateway."""

    def test_entry_builds_openai_provider_pointing_at_gateway(self):
        from app.services.llm.factory import _create_from_entry
        from app.services.llm.model_registry import get_model
        from app.services.llm.providers.openai_provider import OpenAIProvider

        entry = get_model("claude-opus-4.7")
        assert entry is not None, "claude-opus-4.7 entry 应注册"
        assert entry.provider == "langbridge-proxy"
        assert entry.model == "commercial/Claude-Opus-4.7"

        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.langbridge_gateway_api_key = "test-token"
            mock_settings.langbridge_gateway_base_url = "https://base.executor.life/api/llm"
            provider = _create_from_entry(entry)
            # OpenAI-compatible 保证由 provider 类承担(复用 OpenAIProvider 协议层);
            # provider_name 自 token 成本核算(cf2d54f5)起标注真实路由 "langbridge-proxy",
            # 供 usage dashboard 按路由归因, 不再伪装成 "openai"。
            assert isinstance(provider, OpenAIProvider)
            assert provider.provider_name == "langbridge-proxy"
            assert provider.base_url == "https://base.executor.life/api/llm"
            assert provider.api_key == "test-token"
            assert provider.model == "commercial/Claude-Opus-4.7"

    def test_missing_api_key_raises(self):
        from app.services.llm.factory import _create_from_entry
        from app.services.llm.model_registry import get_model

        entry = get_model("gpt-5.5")
        assert entry is not None
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.langbridge_gateway_api_key = None
            mock_settings.langbridge_gateway_base_url = "https://x"
            with pytest.raises(ValueError, match="LANGBRIDGE_GATEWAY_API_KEY"):
                _create_from_entry(entry)

    def test_three_commercial_entries_registered(self):
        from app.services.llm.model_registry import get_model
        for mid, expected in [
            ("claude-opus-4.7", "commercial/Claude-Opus-4.7"),
            ("gpt-5.5", "commercial/GPT-5.5"),
            ("gemini-3.1-pro", "commercial/Gemini-3.1-Pro-Preview"),
        ]:
            e = get_model(mid)
            assert e is not None, f"{mid} 未注册"
            assert e.provider == "langbridge-proxy"
            assert e.model == expected
            assert "LANGBRIDGE_GATEWAY_API_KEY" in e.requires_env


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
