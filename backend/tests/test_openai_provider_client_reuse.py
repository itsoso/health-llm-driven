# -*- coding: utf-8 -*-
"""底层 client 连接复用 (Phase-2 rank4: 消灭 per-round TLS 握手税)。

锁死:
  1. 同 (base_url, api_key) 的两个 provider 实例 → 复用同一个底层 OpenAI 客户端
     (= 同一个 httpx 连接池, 握手只付一次);
  2. 不同 api_key / 不同 base_url → 各自独立客户端 (绝不串号);
  3. `model` 不进 memo key: 同 (base_url, api_key) 不同 model 仍共享连接
     (= "用户切换模型立即生效" 契约 —— 路由在请求参数不在连接层);
  4. reset_client_cache() 清池后重新构造。
"""
from unittest.mock import MagicMock, patch

from app.services.llm.providers.openai_provider import (
    OpenAIProvider,
    reset_client_cache,
)


def _patched_openai():
    """patch openai.OpenAI, 每次构造返回一个**新** MagicMock, 便于按 identity 区分。"""
    return patch("openai.OpenAI", side_effect=lambda **kw: MagicMock(name="openai_client"))


def test_same_base_and_key_share_underlying_client():
    reset_client_cache()
    with _patched_openai() as mock_cls:
        p1 = OpenAIProvider(api_key="k1", base_url="https://x/v1", model="qwen3.6-flash")
        p2 = OpenAIProvider(api_key="k1", base_url="https://x/v1", model="qwen3.7-max")
        c1 = p1._get_client()
        c2 = p2._get_client()
    assert c1 is c2, "同 (base_url, api_key) 必须复用同一底层客户端"
    # 只构造一次 → 只付一次握手。
    assert mock_cls.call_count == 1


def test_different_api_key_gets_different_client():
    reset_client_cache()
    with _patched_openai():
        c1 = OpenAIProvider(api_key="k1", base_url="https://x/v1")._get_client()
        c2 = OpenAIProvider(api_key="k2", base_url="https://x/v1")._get_client()
    assert c1 is not c2, "不同 api_key 绝不共享连接 (防串号)"


def test_different_base_url_gets_different_client():
    reset_client_cache()
    with _patched_openai():
        c1 = OpenAIProvider(api_key="k1", base_url="https://a/v1")._get_client()
        c2 = OpenAIProvider(api_key="k1", base_url="https://b/v1")._get_client()
    assert c1 is not c2, "不同 base_url 各自独立客户端"


def test_model_switch_reuses_connection_but_routes_by_request_param():
    """同 key 不同 model 共享连接 = 用户切模型立即生效 (model 是请求参数不是连接键)。"""
    reset_client_cache()
    with _patched_openai() as mock_cls:
        p_flash = OpenAIProvider(api_key="k1", base_url="https://x/v1", model="qwen3.6-flash")
        p_max = OpenAIProvider(api_key="k1", base_url="https://x/v1", model="qwen3.7-max")
        assert p_flash._get_client() is p_max._get_client()
        assert mock_cls.call_count == 1
    # 路由差异体现在 provider.model (每次请求带), 连接层无差异。
    assert p_flash.model == "qwen3.6-flash"
    assert p_max.model == "qwen3.7-max"


def test_reset_client_cache_forces_reconstruction():
    reset_client_cache()
    with _patched_openai() as mock_cls:
        OpenAIProvider(api_key="k1", base_url="https://x/v1")._get_client()
        assert mock_cls.call_count == 1
        reset_client_cache()
        OpenAIProvider(api_key="k1", base_url="https://x/v1")._get_client()
        assert mock_cls.call_count == 2
