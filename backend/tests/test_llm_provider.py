"""LLM Provider 适配层测试"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.llm.base import LLMProvider
from app.services.llm.factory import create_llm_provider, get_llm_provider, reset_llm_provider
from app.services.llm.providers.openai_provider import OpenAIProvider
from app.services.llm.providers.ollama_provider import OllamaProvider
from app.services.llm.providers.openclaw_provider import OpenClawProvider


class _MockSettings:
    """
    用于工厂测试的 mock settings 对象。

    对于不在构造时设置的属性，getattr 抛出 AttributeError，
    让 factory.py 中的 getattr(settings, "llm_xxx", default) 正确回退到 default。
    """

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)

    def __getattr__(self, name):
        raise AttributeError(f"_MockSettings has no attribute {name!r}")


def _mock_httpx_client(post_response=None, get_response=None):
    """
    创建一个可用于 `async with httpx.AsyncClient(...) as client:` 的 mock。

    返回 (mock_cls, mock_client_instance)，其中:
    - mock_cls 用于 patch httpx.AsyncClient
    - mock_client_instance 是实际的 mock 客户端，可以断言 post/get 调用
    """
    mock_client = AsyncMock()
    if post_response is not None:
        mock_client.post = AsyncMock(return_value=post_response)
    if get_response is not None:
        mock_client.get = AsyncMock(return_value=get_response)

    # 创建异步上下文管理器
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_client)
    ctx.__aexit__ = AsyncMock(return_value=False)

    mock_cls = MagicMock(return_value=ctx)
    return mock_cls, mock_client


# ============================================================
# TestLLMProviderBase - 抽象基类测试
# ============================================================

class TestLLMProviderBase:
    """测试 LLMProvider 抽象基类"""

    def test_cannot_instantiate_abstract_class(self):
        """不能直接实例化抽象基类"""
        with pytest.raises(TypeError):
            LLMProvider()

    def test_subclass_must_implement_chat(self):
        """子类必须实现 chat 方法"""

        class IncompleteProvider(LLMProvider):
            provider_name = "incomplete"

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_subclass_must_implement_chat_with_vision(self):
        """子类必须实现 chat_with_vision 方法"""

        class PartialProvider(LLMProvider):
            provider_name = "partial"

            async def chat(self, messages, **kwargs):
                return "ok"

        with pytest.raises(TypeError):
            PartialProvider()

    def test_valid_subclass_can_instantiate(self):
        """正确实现所有抽象方法的子类可以实例化"""

        class ValidProvider(LLMProvider):
            provider_name = "valid"

            async def chat(self, messages, **kwargs):
                return "ok"

            async def chat_with_vision(self, messages, image_url, **kwargs):
                return "ok"

        p = ValidProvider()
        assert p.provider_name == "valid"
        assert p.supports_multi_model is False

    @pytest.mark.asyncio
    async def test_multi_model_analyze_default_fallback(self):
        """multi_model_analyze 默认回退到单模型 chat"""

        class SimpleProvider(LLMProvider):
            provider_name = "simple"

            async def chat(self, messages, **kwargs):
                return "分析结果"

            async def chat_with_vision(self, messages, image_url, **kwargs):
                return "ok"

        p = SimpleProvider()
        result = await p.multi_model_analyze("分析我的数据")
        assert result["status"] == "completed"
        assert result["aggregation"] == "分析结果"
        assert len(result["model_results"]) == 1

    @pytest.mark.asyncio
    async def test_multi_model_analyze_error_handling(self):
        """multi_model_analyze 异常时返回 error 状态"""

        class ErrorProvider(LLMProvider):
            provider_name = "error"

            async def chat(self, messages, **kwargs):
                raise Exception("模型不可用")

            async def chat_with_vision(self, messages, image_url, **kwargs):
                return "ok"

        p = ErrorProvider()
        result = await p.multi_model_analyze("测试")
        assert result["status"] == "error"
        assert "模型不可用" in result["aggregation"]

    def test_repr(self):
        """__repr__ 输出"""

        class TestProvider(LLMProvider):
            provider_name = "test"

            async def chat(self, messages, **kwargs):
                return "ok"

            async def chat_with_vision(self, messages, image_url, **kwargs):
                return "ok"

        p = TestProvider()
        assert "TestProvider" in repr(p)
        assert "test" in repr(p)


# ============================================================
# TestLLMProviderFactory - 工厂测试
# ============================================================

class TestLLMProviderFactory:
    """测试 LLM Provider 工厂"""

    def setup_method(self):
        reset_llm_provider()

    def teardown_method(self):
        reset_llm_provider()

    def test_create_openai_provider(self):
        """创建 OpenAI provider"""
        mock_s = _MockSettings(
            openai_api_key="sk-test",
            openai_base_url=None,
            openai_model="gpt-4o-mini",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.provider_name == "openai"
        assert provider.api_key == "sk-test"

    def test_create_ollama_provider(self):
        """创建 Ollama provider"""
        mock_s = _MockSettings()
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("ollama")
        assert isinstance(provider, OllamaProvider)
        assert provider.provider_name == "ollama"

    def test_create_openclaw_provider(self):
        """创建 OpenClaw provider"""
        mock_s = _MockSettings(
            openclaw_base_url="https://bot.test.com/v1",
            openclaw_api_key="oc-test",
            openclaw_model="openclaw:main",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("openclaw")
        assert isinstance(provider, OpenClawProvider)
        assert provider.provider_name == "openclaw"
        assert provider.api_key == "oc-test"

    def test_create_unknown_provider_raises(self):
        """未知 provider 类型抛出 ValueError"""
        with pytest.raises(ValueError, match="未知的 LLM provider 类型"):
            create_llm_provider("unknown_provider")

    def test_default_provider_from_settings(self):
        """默认从 settings.llm_provider 读取"""
        mock_s = _MockSettings(
            llm_provider="ollama",
            llm_ollama_base_url="http://localhost:11434",
            llm_ollama_model="llama3",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider()
        assert isinstance(provider, OllamaProvider)

    def test_fallback_to_legacy_openai_config(self):
        """新配置不存在时回退到遗留 OpenAI 配置"""
        mock_s = _MockSettings(
            openai_api_key="sk-legacy",
            openai_base_url="https://proxy.example.com/v1",
            openai_model="gpt-4",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("openai")
        assert isinstance(provider, OpenAIProvider)
        assert provider.api_key == "sk-legacy"
        assert provider.base_url == "https://proxy.example.com/v1"
        assert provider.model == "gpt-4"

    def test_fallback_to_legacy_openclaw_config(self):
        """新配置不存在时回退到遗留 OpenClaw 配置"""
        mock_s = _MockSettings(
            openclaw_base_url="https://bot.executor.life/v1",
            openclaw_api_key="oc-legacy",
            openclaw_model="openclaw:main",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("openclaw")
        assert isinstance(provider, OpenClawProvider)
        assert provider.api_key == "oc-legacy"

    def test_get_llm_provider_singleton(self):
        """get_llm_provider 返回单例"""
        mock_s = _MockSettings(
            openai_api_key="sk-test",
            openai_base_url=None,
            openai_model="gpt-4o-mini",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            p1 = get_llm_provider()
            p2 = get_llm_provider()
        assert p1 is p2

    def test_reset_clears_singleton(self):
        """reset_llm_provider 清除单例"""
        mock_s = _MockSettings(
            openai_api_key="sk-test",
            openai_base_url=None,
            openai_model="gpt-4o-mini",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            p1 = get_llm_provider()
            reset_llm_provider()
            p2 = get_llm_provider()
        assert p1 is not p2

    def test_case_insensitive_provider_type(self):
        """provider 类型不区分大小写"""
        mock_s = _MockSettings(
            openai_api_key="sk-test",
            openai_base_url=None,
            openai_model="gpt-4o-mini",
        )
        with patch("app.services.llm.factory.settings", mock_s):
            provider = create_llm_provider("OpenAI")
            assert isinstance(provider, OpenAIProvider)

            provider = create_llm_provider("OLLAMA")
            assert isinstance(provider, OllamaProvider)


# ============================================================
# TestOpenAIProvider - OpenAI Provider 测试
# ============================================================

class TestOpenAIProvider:
    """测试 OpenAI Provider"""

    def test_init(self):
        """初始化参数"""
        p = OpenAIProvider(
            api_key="sk-test",
            base_url="https://proxy.example.com/v1",
            model="gpt-4",
        )
        assert p.api_key == "sk-test"
        assert p.base_url == "https://proxy.example.com/v1"
        assert p.model == "gpt-4"
        assert p.provider_name == "openai"
        assert p._client is None

    def test_default_model(self):
        """默认模型"""
        p = OpenAIProvider(api_key="sk-test")
        assert p.model == "gpt-4o-mini"

    def test_lazy_client_init(self):
        """懒加载 OpenAI 客户端"""
        p = OpenAIProvider(api_key="sk-test", base_url="https://proxy.com/v1")
        assert p._client is None

        mock_instance = MagicMock()
        with patch("openai.OpenAI", return_value=mock_instance) as mock_cls:
            client = p._get_client()
            mock_cls.assert_called_once_with(
                api_key="sk-test", base_url="https://proxy.com/v1"
            )
            assert p._client is client
            assert client is mock_instance

            # 再次调用不会重新创建
            p._get_client()
            assert mock_cls.call_count == 1

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self):
        """非流式 chat 调用"""
        p = OpenAIProvider(api_key="sk-test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "你好！"
        mock_response.choices[0].message.tool_calls = None
        p._client = MagicMock()

        with patch(
            "app.services.llm.providers.openai_provider.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_to_thread:
            result = await p.chat(
                messages=[{"role": "user", "content": "你好"}],
                stream=False,
            )

        assert result == "你好！"
        mock_to_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_vision(self):
        """vision 调用"""
        p = OpenAIProvider(api_key="sk-test")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "这是一张猫的图片"
        p._client = MagicMock()

        with patch(
            "app.services.llm.providers.openai_provider.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_to_thread:
            result = await p.chat_with_vision(
                messages=[
                    {"role": "system", "content": "你是图片分析助手"},
                    {"role": "user", "content": "描述这张图片"},
                ],
                image_url="data:image/jpeg;base64,/9j/test",
            )

        assert result == "这是一张猫的图片"
        mock_to_thread.assert_called_once()
        # 验证传入的 messages 包含 vision 格式
        call_kwargs = mock_to_thread.call_args.kwargs
        sent_messages = call_kwargs.get("messages")
        assert sent_messages is not None
        last_user = [m for m in sent_messages if m["role"] == "user"][-1]
        assert isinstance(last_user["content"], list)
        assert any(part.get("type") == "image_url" for part in last_user["content"])

    def test_build_vision_messages(self):
        """构建 vision 消息格式"""
        messages = [
            {"role": "system", "content": "你是助手"},
            {"role": "user", "content": "看看这个"},
        ]
        result = OpenAIProvider._build_vision_messages(
            messages, "data:image/png;base64,abc123"
        )
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert isinstance(result[1]["content"], list)
        assert result[1]["content"][0]["type"] == "text"
        assert result[1]["content"][1]["type"] == "image_url"
        assert "abc123" in result[1]["content"][1]["image_url"]["url"]

    def test_build_vision_messages_preserves_non_user(self):
        """vision 消息构建保持非 user 消息不变"""
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "第一个问题"},
            {"role": "assistant", "content": "第一个回答"},
            {"role": "user", "content": "看图"},
        ]
        result = OpenAIProvider._build_vision_messages(messages, "https://img.com/pic.jpg")
        assert isinstance(result[1]["content"], str)
        assert isinstance(result[3]["content"], list)


# ============================================================
# TestOllamaProvider - Ollama Provider 测试
# ============================================================

class TestOllamaProvider:
    """测试 Ollama Provider"""

    def test_init(self):
        """初始化参数"""
        p = OllamaProvider(base_url="http://localhost:11434", model="llama3")
        assert p.base_url == "http://localhost:11434"
        assert p.model == "llama3"
        assert p.provider_name == "ollama"

    def test_trailing_slash_stripped(self):
        """base_url 尾部斜杠被去除"""
        p = OllamaProvider(base_url="http://localhost:11434/")
        assert p.base_url == "http://localhost:11434"

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self):
        """非流式 chat 调用 Ollama"""
        p = OllamaProvider(base_url="http://test:11434", model="llama3")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "你好世界"},
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(post_response=mock_response)

        with patch(
            "app.services.llm.providers.ollama_provider.httpx.AsyncClient", mock_cls
        ):
            result = await p.chat(
                messages=[{"role": "user", "content": "你好"}],
                stream=False,
            )

        assert result == "你好世界"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/api/chat" in call_args[0][0]
        payload = call_args[1]["json"]
        assert payload["model"] == "llama3"
        assert payload["stream"] is False

    @pytest.mark.asyncio
    async def test_chat_with_vision(self):
        """vision 调用 Ollama"""
        p = OllamaProvider(base_url="http://test:11434", model="llava")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "这是一只猫"},
            "done": True,
        }
        mock_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(post_response=mock_response)

        with patch(
            "app.services.llm.providers.ollama_provider.httpx.AsyncClient", mock_cls
        ):
            result = await p.chat_with_vision(
                messages=[{"role": "user", "content": "描述图片"}],
                image_url="data:image/jpeg;base64,/9j/test",
            )

        assert result == "这是一只猫"
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"]
        user_msgs = [m for m in payload["messages"] if m["role"] == "user"]
        assert "images" in user_msgs[-1]

    def test_build_vision_messages(self):
        """构建 Ollama 视觉消息格式"""
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "描述图片"},
        ]
        result = OllamaProvider._build_vision_messages(
            messages, "data:image/jpeg;base64,abc123"
        )
        assert len(result) == 2
        assert "images" in result[1]
        assert result[1]["images"] == ["abc123"]
        assert result[0] == {"role": "system", "content": "系统提示"}

    def test_build_vision_messages_raw_base64(self):
        """非 data URI 格式直接作为 image_data"""
        messages = [{"role": "user", "content": "看图"}]
        result = OllamaProvider._build_vision_messages(messages, "raw_base64_data")
        assert result[0]["images"] == ["raw_base64_data"]


# ============================================================
# TestOpenClawProvider - OpenClaw Provider 测试
# ============================================================

class TestOpenClawProvider:
    """测试 OpenClaw Provider"""

    def test_init(self):
        """初始化参数"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            api_key="oc-test",
            model="openclaw:main",
        )
        assert p.base_url == "https://bot.test.com/v1"
        assert p.api_key == "oc-test"
        assert p.model == "openclaw:main"
        assert p.provider_name == "openclaw"

    def test_trailing_slash_stripped(self):
        """base_url 尾部斜杠被去除"""
        p = OpenClawProvider(base_url="https://bot.test.com/v1/")
        assert p.base_url == "https://bot.test.com/v1"

    def test_supports_multi_model_false_without_analyze_url(self):
        """未配置 analyze_url 时不支持多模型"""
        p = OpenClawProvider(base_url="https://bot.test.com/v1")
        assert p.supports_multi_model is False

    def test_supports_multi_model_true_with_analyze_url(self):
        """配置 analyze_url 后支持多模型"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            analyze_url="https://base.executor.life/api/openclaw/analyze",
        )
        assert p.supports_multi_model is True

    def test_get_headers_with_api_key(self):
        """带 API key 的请求头"""
        p = OpenClawProvider(api_key="oc-test")
        headers = p._get_headers()
        assert headers["Authorization"] == "Bearer oc-test"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_without_api_key(self):
        """无 API key 的请求头"""
        p = OpenClawProvider(api_key=None)
        headers = p._get_headers()
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self):
        """非流式 chat 调用 OpenClaw"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            api_key="oc-test",
            model="openclaw:main",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "你好！我是健康助手"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(post_response=mock_response)

        with patch(
            "app.services.llm.providers.openclaw_provider.httpx.AsyncClient", mock_cls
        ):
            result = await p.chat(
                messages=[{"role": "user", "content": "你好"}],
                stream=False,
            )

        assert result == "你好！我是健康助手"
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert "/chat/completions" in call_args[0][0]
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer oc-test"

    @pytest.mark.asyncio
    async def test_multi_model_without_analyze_url(self):
        """未配置 analyze_url 时回退到单模型"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            api_key="oc-test",
        )
        assert p.supports_multi_model is False

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "单模型结果"}}]
        }
        mock_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(post_response=mock_response)

        with patch(
            "app.services.llm.providers.openclaw_provider.httpx.AsyncClient", mock_cls
        ):
            result = await p.multi_model_analyze("分析数据")

        assert result["status"] == "completed"
        assert result["aggregation"] == "单模型结果"

    @pytest.mark.asyncio
    async def test_multi_model_submit_and_poll(self):
        """多模型分析: submit + poll 流程"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            api_key="oc-test",
            analyze_url="https://base.executor.life/api/openclaw/analyze",
            analyze_api_key="oc-analyze-key",
            kim_user_id="test_user",
        )
        assert p.supports_multi_model is True

        submit_response = MagicMock()
        submit_response.json.return_value = {"ok": True, "batch_id": "batch-123"}
        submit_response.raise_for_status = MagicMock()

        poll_response = MagicMock()
        poll_response.json.return_value = {
            "status": "completed",
            "model_results": [{"model": "gpt4", "content": "结果1"}],
            "aggregation": "综合分析结果",
        }
        poll_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(
            post_response=submit_response,
            get_response=poll_response,
        )

        with patch(
            "app.services.llm.providers.openclaw_provider.httpx.AsyncClient", mock_cls
        ), patch(
            "app.services.llm.providers.openclaw_provider.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            result = await p.multi_model_analyze("分析我的运动数据")

        assert result["status"] == "completed"
        assert result["aggregation"] == "综合分析结果"
        assert len(result["model_results"]) == 1

    @pytest.mark.asyncio
    async def test_multi_model_submit_failure(self):
        """多模型分析: submit 失败"""
        p = OpenClawProvider(
            base_url="https://bot.test.com/v1",
            analyze_url="https://base.executor.life/api/openclaw/analyze",
            analyze_api_key="oc-key",
            kim_user_id="user",
        )

        submit_response = MagicMock()
        submit_response.json.return_value = {"ok": False, "error": "服务繁忙"}
        submit_response.raise_for_status = MagicMock()

        mock_cls, mock_client = _mock_httpx_client(post_response=submit_response)

        with patch(
            "app.services.llm.providers.openclaw_provider.httpx.AsyncClient", mock_cls
        ):
            result = await p.multi_model_analyze("测试")

        assert result["status"] == "error"
        assert "提交分析失败" in result["aggregation"]

    def test_build_vision_messages(self):
        """构建 OpenClaw vision 消息格式"""
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "分析这张图"},
        ]
        result = OpenClawProvider._build_vision_messages(
            messages, "data:image/jpeg;base64,abc"
        )
        assert len(result) == 2
        assert isinstance(result[1]["content"], list)
        assert result[1]["content"][0]["type"] == "text"
        assert result[1]["content"][1]["type"] == "image_url"


# ---- Function Calling / Tools Tests ----

class TestOpenAIProviderTools:
    """OpenAI Provider tools 参数测试"""

    @pytest.fixture
    def provider(self):
        return OpenAIProvider(api_key="test-key", model="gpt-4o-mini")

    @pytest.fixture
    def sample_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_water",
                    "description": "记录饮水量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount_ml": {"type": "integer", "description": "饮水量(毫升)"}
                        },
                        "required": ["amount_ml"],
                    },
                },
            }
        ]

    @patch("app.services.llm.providers.openai_provider.asyncio.to_thread")
    @pytest.mark.asyncio
    async def test_chat_with_tools_passes_to_sdk(self, mock_to_thread, provider, sample_tools):
        """tools 参数应透传给 OpenAI SDK"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "已记录"
        mock_response.choices[0].message.tool_calls = None
        mock_to_thread.return_value = mock_response

        with patch.object(provider, "_get_client") as mock_client:
            mock_client.return_value = MagicMock()
            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=sample_tools,
            )
            # tools 应通过 **kwargs 透传
            call_kwargs = mock_to_thread.call_args
            assert "tools" in str(call_kwargs)


class TestOpenClawProviderTools:
    """OpenClaw Provider tools 参数测试"""

    @pytest.fixture
    def provider(self):
        return OpenClawProvider(
            base_url="https://test.com/v1",
            api_key="test-key",
        )

    @pytest.fixture
    def sample_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "record_water",
                    "description": "记录饮水量",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "amount_ml": {"type": "integer"}
                        },
                        "required": ["amount_ml"],
                    },
                },
            }
        ]

    @pytest.mark.asyncio
    async def test_chat_with_tools_includes_in_payload(self, provider, sample_tools):
        """tools 参数应包含在 HTTP payload 中"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "已记录", "tool_calls": None}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=sample_tools,
            )
            # 验证 POST payload 包含 tools
            post_call = mock_instance.post.call_args
            payload = post_call.kwargs.get("json", {})
            assert "tools" in payload
            assert payload["tools"] == sample_tools

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls_returns_dict(self, provider):
        """当 LLM 返回 tool_calls 时，chat 应返回包含 tool_calls 的结构"""
        tool_calls_data = [
            {
                "id": "call_123",
                "type": "function",
                "function": {"name": "record_water", "arguments": '{"amount_ml": 250}'},
            }
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": tool_calls_data,
                    }
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            MockClient.return_value = mock_instance

            result = await provider.chat(
                messages=[{"role": "user", "content": "喝水250"}],
                tools=[{"type": "function", "function": {"name": "record_water"}}],
            )
            # tool_calls 时返回 dict 而非 str
            assert isinstance(result, dict)
            assert "tool_calls" in result
            assert result["tool_calls"][0]["function"]["name"] == "record_water"
