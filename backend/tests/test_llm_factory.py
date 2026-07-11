"""
LLM Factory 单元测试。

验证：
- 默认 provider 是 tokenplan
- OpenClaw provider 已移除，显式请求抛 ValueError
- 未知 provider 类型抛 ValueError
- provider 单例缓存行为
"""

import pytest
from unittest.mock import patch

from app.services.llm.factory import create_llm_provider, get_llm_provider, reset_llm_provider


class TestDefaultProvider:
    def test_default_is_tokenplan(self):
        """默认 provider 应该是 tokenplan。"""
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "tokenplan"
            mock_settings.tokenplan_api_key = "test-key"
            mock_settings.tokenplan_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            mock_settings.tokenplan_model = "qwen3.7-plus"

            provider = create_llm_provider()
            assert provider.provider_name == "tokenplan"


class TestRemovedProvider:
    def test_openclaw_request_raises(self):
        """OpenClaw 已移除，显式请求应失败而不是静默代理。"""
        with pytest.raises(ValueError, match="未知的 LLM provider"):
            create_llm_provider("openclaw")


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


class TestExtractionProvider:
    """Batch-1 token-perf: 抽取档 provider 助手 —— 命中时用降档模型, 失败 fail-soft 回退。"""

    def test_returns_flash_provider_when_available(self):
        from app.services.llm.factory import create_provider_for_extraction

        flash = object()
        with patch("app.services.llm.factory.create_provider_for_model_id",
                   return_value=flash) as cp, \
             patch("app.services.llm.factory.get_llm_provider") as gp:
            got = create_provider_for_extraction("deepseek-v4-flash")
        assert got is flash
        cp.assert_called_once_with("deepseek-v4-flash")
        gp.assert_not_called()  # 命中降档模型时绝不碰默认强模型

    def test_failsoft_falls_back_on_unregistered_model(self):
        """降档模型未注册 / env 缺失 → 回退 get_llm_provider(), 绝不抛。"""
        from app.services.llm.factory import create_provider_for_extraction

        sentinel = object()
        with patch("app.services.llm.factory.create_provider_for_model_id",
                   side_effect=ValueError("未注册的 model_id: nope")), \
             patch("app.services.llm.factory.get_llm_provider",
                   return_value=sentinel) as gp:
            got = create_provider_for_extraction("nope")
        assert got is sentinel
        gp.assert_called_once()
