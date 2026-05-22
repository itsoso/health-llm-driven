# 健康管理系统开源 Phase 1 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将健康管理系统重构为可开源部署的版本（Phase 1: LLM 适配层 + Docker Compose + 敏感信息清理）

**Architecture:** 创建统一的 LLM Provider 抽象层替换现有散落的 OpenAI/OpenClaw 直接调用，添加 Docker Compose 支持一键部署，清理所有硬编码敏感信息。

**Tech Stack:** Python/FastAPI, SQLAlchemy, Pydantic v2, Docker/Docker Compose, PostgreSQL, Redis, Celery

---

## Task 1: LLM Provider 基础接口与工厂

**Files:**
- Create: `backend/app/services/llm/__init__.py`
- Create: `backend/app/services/llm/base.py`
- Create: `backend/app/services/llm/factory.py`
- Test: `backend/tests/test_llm_provider.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_llm_provider.py
"""LLM Provider 基础接口和工厂测试"""
import pytest
from unittest.mock import patch, MagicMock


class TestLLMProviderBase:
    """测试 LLMProvider 抽象基类"""

    def test_cannot_instantiate_abstract_class(self):
        from app.services.llm.base import LLMProvider
        with pytest.raises(TypeError):
            LLMProvider()

    def test_subclass_must_implement_chat(self):
        from app.services.llm.base import LLMProvider

        class IncompleteProvider(LLMProvider):
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()


class TestLLMProviderFactory:
    """测试 Provider 工厂"""

    def test_factory_returns_openai_provider(self):
        from app.services.llm.factory import create_llm_provider
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.llm_api_key = "sk-test"
            mock_settings.llm_base_url = None
            mock_settings.llm_model = "gpt-4o-mini"
            mock_settings.llm_vision_model = "gpt-4o"
            provider = create_llm_provider()
            assert provider is not None
            assert provider.provider_name == "openai"

    def test_factory_returns_ollama_provider(self):
        from app.services.llm.factory import create_llm_provider
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_base_url = "http://localhost:11434"
            mock_settings.ollama_model = "llama3"
            mock_settings.llm_vision_model = "llava"
            provider = create_llm_provider()
            assert provider is not None
            assert provider.provider_name == "ollama"

    def test_factory_unknown_provider_raises(self):
        from app.services.llm.factory import create_llm_provider
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "unknown_provider"
            with pytest.raises(ValueError, match="Unknown LLM provider"):
                create_llm_provider()

    def test_factory_fallback_to_legacy_openai_config(self):
        """当新配置不存在时，回退到旧的 openai_api_key 配置"""
        from app.services.llm.factory import create_llm_provider
        with patch("app.services.llm.factory.settings") as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.llm_api_key = None  # 新配置没设置
            mock_settings.openai_api_key = "sk-legacy"  # 旧配置存在
            mock_settings.llm_base_url = None
            mock_settings.openai_base_url = "https://proxy.example.com/v1"
            mock_settings.llm_model = "gpt-4o-mini"
            mock_settings.openai_model = "gpt-4o-mini"
            mock_settings.llm_vision_model = "gpt-4o"
            provider = create_llm_provider()
            assert provider is not None
            assert provider.api_key == "sk-legacy"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_provider.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.llm'"

**Step 3: Write minimal implementation**

```python
# backend/app/services/llm/__init__.py
"""LLM Provider 适配层 - 统一多种 LLM 后端的调用接口"""
from app.services.llm.base import LLMProvider
from app.services.llm.factory import create_llm_provider, get_llm_provider

__all__ = ["LLMProvider", "create_llm_provider", "get_llm_provider"]
```

```python
# backend/app/services/llm/base.py
"""LLM Provider 抽象基类"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional


class LLMProvider(ABC):
    """所有 LLM 提供商的基类。

    子类需实现 chat() 和 chat_with_vision()。
    multi_model_analyze() 默认回退为单模型调用。
    """

    provider_name: str = "base"

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        timeout: float = 60.0,
    ) -> str | AsyncIterator[str]:
        """发送对话请求。

        Args:
            messages: OpenAI 格式的消息列表 [{"role": "system", "content": "..."}]
            model: 覆盖默认模型名
            temperature: 采样温度
            max_tokens: 最大输出 token 数
            stream: 是否流式返回
            timeout: 请求超时（秒）

        Returns:
            stream=False 时返回 str，stream=True 时返回 AsyncIterator[str]
        """

    @abstractmethod
    async def chat_with_vision(
        self,
        messages: list[dict],
        images: list[str],
        model: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        """视觉理解（食物识别、图片分析等）。

        Args:
            messages: 消息列表
            images: base64 编码的图片列表
            model: 覆盖默认视觉模型名
            max_tokens: 最大输出 token 数
        """

    async def multi_model_analyze(
        self,
        prompt: str,
        models: Optional[list[str]] = None,
    ) -> dict:
        """多模型并行分析（可选）。

        默认实现：使用单模型调用回退。
        仅 OpenClaw Provider 支持真正的多模型分析。
        """
        result = await self.chat(
            messages=[{"role": "user", "content": prompt}],
            model=models[0] if models else None,
        )
        return {
            "status": "completed",
            "model_results": [{"model": "default", "content": result}],
            "aggregation": result,
        }
```

```python
# backend/app/services/llm/factory.py
"""LLM Provider 工厂 - 根据配置创建对应的 Provider 实例"""
import logging
from typing import Optional
from app.config import settings
from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

_provider_instance: Optional[LLMProvider] = None


def create_llm_provider() -> LLMProvider:
    """根据配置创建 LLM Provider 实例。

    配置优先级：
    - 新配置 (LLM_PROVIDER, LLM_API_KEY, ...) 优先
    - 旧配置 (OPENAI_API_KEY, OPENCLAW_BASE_URL, ...) 作为回退
    """
    provider_type = getattr(settings, "llm_provider", "openai")

    if provider_type == "openai":
        from app.services.llm.providers.openai_provider import OpenAILLMProvider

        api_key = getattr(settings, "llm_api_key", None) or getattr(settings, "openai_api_key", None)
        base_url = getattr(settings, "llm_base_url", None) or getattr(settings, "openai_base_url", None)
        model = getattr(settings, "llm_model", None) or getattr(settings, "openai_model", "gpt-4o-mini")
        vision_model = getattr(settings, "llm_vision_model", "gpt-4o")

        return OpenAILLMProvider(
            api_key=api_key,
            base_url=base_url,
            model=model,
            vision_model=vision_model,
        )

    elif provider_type == "ollama":
        from app.services.llm.providers.ollama_provider import OllamaLLMProvider

        base_url = getattr(settings, "ollama_base_url", "http://localhost:11434")
        model = getattr(settings, "ollama_model", "llama3")
        vision_model = getattr(settings, "llm_vision_model", "llava")

        return OllamaLLMProvider(
            base_url=base_url,
            model=model,
            vision_model=vision_model,
        )

    elif provider_type == "openclaw":
        from app.services.llm.providers.openclaw_provider import OpenClawLLMProvider

        base_url = getattr(settings, "llm_base_url", None) or getattr(settings, "openclaw_base_url", "https://bot.executor.life/v1")
        api_key = getattr(settings, "llm_api_key", None) or getattr(settings, "openclaw_api_key", None)
        model = getattr(settings, "llm_model", None) or getattr(settings, "openclaw_model", "openclaw:main")
        # OpenClaw 多模型分析配置
        analyze_url = getattr(settings, "openclaw_analyze_url", None)
        analyze_api_key = getattr(settings, "openclaw_analyze_api_key", None)
        analyze_user_id = getattr(settings, "openclaw_analyze_user_id", None)

        return OpenClawLLMProvider(
            base_url=base_url,
            api_key=api_key,
            model=model,
            analyze_url=analyze_url,
            analyze_api_key=analyze_api_key,
            analyze_user_id=analyze_user_id,
        )

    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}. Supported: openai, ollama, openclaw")


def get_llm_provider() -> LLMProvider:
    """获取全局 LLM Provider 单例（懒加载）"""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = create_llm_provider()
    return _provider_instance


def reset_llm_provider():
    """重置全局 Provider（用于测试或配置变更）"""
    global _provider_instance
    _provider_instance = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_provider.py -v`
Expected: PASS (4 tests)

Note: Step 4 will require Task 2 (OpenAI Provider) and Task 3 (Ollama Provider) to fully pass. The factory tests import those providers. You can temporarily stub them or implement Tasks 1-3 together.

**Step 5: Commit**

```bash
git add backend/app/services/llm/ backend/tests/test_llm_provider.py
git commit -m "feat: add LLM Provider base interface and factory"
```

---

## Task 2: OpenAI Provider 实现

**Files:**
- Create: `backend/app/services/llm/providers/__init__.py`
- Create: `backend/app/services/llm/providers/openai_provider.py`
- Test: `backend/tests/test_llm_provider.py` (追加)

**Step 1: Write the failing test**

追加到 `backend/tests/test_llm_provider.py`：

```python
class TestOpenAIProvider:
    """测试 OpenAI Provider"""

    def test_init_with_api_key(self):
        from app.services.llm.providers.openai_provider import OpenAILLMProvider
        provider = OpenAILLMProvider(api_key="sk-test", model="gpt-4o-mini")
        assert provider.provider_name == "openai"
        assert provider.api_key == "sk-test"
        assert provider.model == "gpt-4o-mini"

    def test_init_with_base_url(self):
        from app.services.llm.providers.openai_provider import OpenAILLMProvider
        provider = OpenAILLMProvider(
            api_key="sk-test",
            base_url="https://proxy.example.com/v1",
            model="gpt-4o-mini",
        )
        assert provider.base_url == "https://proxy.example.com/v1"

    @pytest.mark.asyncio
    async def test_chat_calls_openai(self):
        from app.services.llm.providers.openai_provider import OpenAILLMProvider
        provider = OpenAILLMProvider(api_key="sk-test", model="gpt-4o-mini")

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Hello!"))]

        with patch.object(provider, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result == "Hello!"

    @pytest.mark.asyncio
    async def test_chat_with_vision(self):
        from app.services.llm.providers.openai_provider import OpenAILLMProvider
        provider = OpenAILLMProvider(
            api_key="sk-test", model="gpt-4o-mini", vision_model="gpt-4o"
        )

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"food": "apple"}'))]

        with patch.object(provider, "_get_client") as mock_client:
            mock_client.return_value.chat.completions.create.return_value = mock_response
            result = await provider.chat_with_vision(
                messages=[{"role": "user", "content": "What food is this?"}],
                images=["base64data"],
            )
            assert "apple" in result
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOpenAIProvider -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/app/services/llm/providers/__init__.py
"""LLM Provider 实现"""
```

```python
# backend/app/services/llm/providers/openai_provider.py
"""OpenAI 兼容 LLM Provider - 支持 OpenAI / DeepSeek / vLLM / LM Studio 等"""
import asyncio
import logging
from typing import AsyncIterator, Optional

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenAILLMProvider(LLMProvider):
    """OpenAI 兼容的 LLM Provider。

    支持所有 OpenAI API 兼容的服务：
    - OpenAI (api.openai.com)
    - DeepSeek (api.deepseek.com)
    - vLLM / LM Studio (本地)
    - 各种代理服务
    """

    provider_name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "gpt-4o-mini",
        vision_model: str = "gpt-4o",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.vision_model = vision_model
        self._client = None

    def _get_client(self):
        """懒加载 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI
            kwargs = {"api_key": self.api_key}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            self._client = OpenAI(**kwargs)
        return self._client

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        timeout: float = 60.0,
    ) -> str | AsyncIterator[str]:
        use_model = model or self.model
        client = self._get_client()

        if stream:
            return self._stream_chat(client, messages, use_model, temperature, max_tokens, timeout)

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=use_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        return response.choices[0].message.content or ""

    async def _stream_chat(
        self, client, messages, model, temperature, max_tokens, timeout
    ) -> AsyncIterator[str]:
        """流式返回 token"""
        def _create_stream():
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                timeout=timeout,
            )

        stream = await asyncio.to_thread(_create_stream)
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def chat_with_vision(
        self,
        messages: list[dict],
        images: list[str],
        model: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        use_model = model or self.vision_model
        client = self._get_client()

        # 构建带图片的消息
        vision_messages = []
        for msg in messages:
            if msg["role"] == "user" and images:
                content = [{"type": "text", "text": msg["content"]}]
                for img in images:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                    })
                vision_messages.append({"role": msg["role"], "content": content})
            else:
                vision_messages.append(msg)

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=use_model,
            messages=vision_messages,
            max_tokens=max_tokens,
            timeout=60,
        )
        return response.choices[0].message.content or ""
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOpenAIProvider -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm/providers/
git commit -m "feat: add OpenAI-compatible LLM Provider"
```

---

## Task 3: Ollama Provider 实现

**Files:**
- Create: `backend/app/services/llm/providers/ollama_provider.py`
- Test: `backend/tests/test_llm_provider.py` (追加)

**Step 1: Write the failing test**

追加到 `backend/tests/test_llm_provider.py`：

```python
class TestOllamaProvider:
    """测试 Ollama Provider"""

    def test_init(self):
        from app.services.llm.providers.ollama_provider import OllamaLLMProvider
        provider = OllamaLLMProvider(
            base_url="http://localhost:11434",
            model="llama3",
        )
        assert provider.provider_name == "ollama"
        assert provider.model == "llama3"

    @pytest.mark.asyncio
    async def test_chat_calls_ollama_api(self):
        from app.services.llm.providers.ollama_provider import OllamaLLMProvider
        provider = OllamaLLMProvider(
            base_url="http://localhost:11434",
            model="llama3",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "Hello from Ollama!"}
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = MagicMock(return_value=False)
            mock_client.post = MagicMock(return_value=mock_resp)

            # Use a real async mock
            import asyncio
            mock_client.post = MagicMock()
            future = asyncio.Future()
            future.set_result(mock_resp)
            mock_client.post.return_value = future

            result = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result == "Hello from Ollama!"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOllamaProvider -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/app/services/llm/providers/ollama_provider.py
"""Ollama 本地 LLM Provider"""
import logging
from typing import AsyncIterator, Optional

import httpx

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class OllamaLLMProvider(LLMProvider):
    """Ollama 本地模型 Provider。

    通过 Ollama REST API 调用本地模型。
    需要先安装 Ollama 并拉取模型：ollama pull llama3
    """

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        vision_model: str = "llava",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.vision_model = vision_model

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        timeout: float = 120.0,
    ) -> str | AsyncIterator[str]:
        use_model = model or self.model
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": use_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if stream:
            return self._stream_chat(url, payload, timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")

    async def _stream_chat(self, url, payload, timeout) -> AsyncIterator[str]:
        """流式返回 token"""
        import json
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content

    async def chat_with_vision(
        self,
        messages: list[dict],
        images: list[str],
        model: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        use_model = model or self.vision_model
        url = f"{self.base_url}/api/chat"

        # Ollama 视觉模型使用 images 字段
        vision_messages = []
        for msg in messages:
            m = {"role": msg["role"], "content": msg["content"]}
            if msg["role"] == "user" and images:
                m["images"] = images  # Ollama 接受 base64 列表
            vision_messages.append(m)

        payload = {
            "model": use_model,
            "messages": vision_messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOllamaProvider -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm/providers/ollama_provider.py backend/tests/test_llm_provider.py
git commit -m "feat: add Ollama local LLM Provider"
```

---

## Task 4: OpenClaw Provider 实现

**Files:**
- Create: `backend/app/services/llm/providers/openclaw_provider.py`
- Test: `backend/tests/test_llm_provider.py` (追加)

**Step 1: Write the failing test**

追加到 `backend/tests/test_llm_provider.py`：

```python
class TestOpenClawProvider:
    """测试 OpenClaw Provider"""

    def test_init(self):
        from app.services.llm.providers.openclaw_provider import OpenClawLLMProvider
        provider = OpenClawLLMProvider(
            base_url="https://bot.example.com/v1",
            api_key="test-key",
            model="openclaw:main",
        )
        assert provider.provider_name == "openclaw"
        assert provider.model == "openclaw:main"

    @pytest.mark.asyncio
    async def test_chat_calls_openclaw_api(self):
        from app.services.llm.providers.openclaw_provider import OpenClawLLMProvider
        provider = OpenClawLLMProvider(
            base_url="https://bot.example.com/v1",
            api_key="test-key",
            model="openclaw:main",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Hello from OpenClaw!"}}]
        }
        mock_resp.raise_for_status = MagicMock()

        import asyncio
        with patch("httpx.AsyncClient") as MockClient:
            mock_client = MagicMock()
            MockClient.return_value.__aenter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = MagicMock(return_value=False)
            future = asyncio.Future()
            future.set_result(mock_resp)
            mock_client.post.return_value = future

            result = await provider.chat(
                messages=[{"role": "user", "content": "Hi"}]
            )
            assert result == "Hello from OpenClaw!"

    def test_multi_model_analyze_available(self):
        from app.services.llm.providers.openclaw_provider import OpenClawLLMProvider
        provider = OpenClawLLMProvider(
            base_url="https://bot.example.com/v1",
            api_key="test-key",
            model="openclaw:main",
            analyze_url="https://base.example.com/api/openclaw/analyze",
            analyze_api_key="oc-test-key",
            analyze_user_id="test-user",
        )
        assert provider.supports_multi_model is True

    def test_multi_model_analyze_not_available_without_config(self):
        from app.services.llm.providers.openclaw_provider import OpenClawLLMProvider
        provider = OpenClawLLMProvider(
            base_url="https://bot.example.com/v1",
            api_key="test-key",
            model="openclaw:main",
        )
        assert provider.supports_multi_model is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOpenClawProvider -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/app/services/llm/providers/openclaw_provider.py
"""OpenClaw LLM Provider - 支持对话 + 多模型分析"""
import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import httpx

from app.services.llm.base import LLMProvider

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 10
MAX_POLL_ATTEMPTS = 18


class OpenClawLLMProvider(LLMProvider):
    """OpenClaw LLM Provider。

    支持：
    - OpenAI 兼容的对话 API（/chat/completions）
    - 多模型并行分析（可选，需配置 analyze_url）
    - 流式输出（SSE）
    """

    provider_name = "openclaw"

    def __init__(
        self,
        base_url: str = "https://bot.executor.life/v1",
        api_key: Optional[str] = None,
        model: str = "openclaw:main",
        analyze_url: Optional[str] = None,
        analyze_api_key: Optional[str] = None,
        analyze_user_id: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.vision_model = model  # OpenClaw 使用同一模型
        # 多模型分析配置
        self.analyze_url = analyze_url
        self.analyze_api_key = analyze_api_key
        self.analyze_user_id = analyze_user_id

    @property
    def supports_multi_model(self) -> bool:
        return bool(self.analyze_url and self.analyze_api_key and self.analyze_user_id)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
        timeout: float = 240.0,
    ) -> str | AsyncIterator[str]:
        use_model = model or self.model
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": use_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if stream:
            return self._stream_chat(url, payload, timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def _stream_chat(self, url, payload, timeout) -> AsyncIterator[str]:
        """SSE 流式返回"""
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", url, json=payload, headers=self._headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    async def chat_with_vision(
        self,
        messages: list[dict],
        images: list[str],
        model: Optional[str] = None,
        max_tokens: int = 2000,
    ) -> str:
        """OpenClaw 使用 OpenAI 格式的 vision 消息"""
        vision_messages = []
        for msg in messages:
            if msg["role"] == "user" and images:
                content = [{"type": "text", "text": msg["content"]}]
                for img in images:
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{img}"},
                    })
                vision_messages.append({"role": msg["role"], "content": content})
            else:
                vision_messages.append(msg)

        result = await self.chat(
            messages=vision_messages, model=model, max_tokens=max_tokens
        )
        return result

    async def multi_model_analyze(
        self,
        prompt: str,
        models: Optional[list[str]] = None,
    ) -> dict:
        """提交多模型分析并轮询结果"""
        if not self.supports_multi_model:
            return await super().multi_model_analyze(prompt, models)

        batch_id = await self._submit_analyze(prompt)
        if not batch_id:
            return {"status": "error", "model_results": [], "aggregation": "提交分析失败"}

        return await self._poll_analyze(batch_id)

    async def _submit_analyze(self, prompt: str) -> Optional[str]:
        payload = {
            "prompt": prompt,
            "kim_user_id": self.analyze_user_id,
            "api_key": self.analyze_api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.analyze_url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                if data.get("ok"):
                    return data.get("batch_id")
                logger.error(f"[OpenClaw分析] 提交失败: {data}")
                return None
        except Exception as e:
            logger.error(f"[OpenClaw分析] 提交异常: {e}")
            return None

    async def _poll_analyze(self, batch_id: str) -> dict:
        status_url = self.analyze_url.replace("/analyze", "/status")
        url = f"{status_url}/{batch_id}"
        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                status = data.get("status", "")
                if status in ("completed", "partial"):
                    return {
                        "status": status,
                        "model_results": data.get("model_results", []),
                        "aggregation": data.get("aggregation", ""),
                    }
            except Exception as e:
                logger.warning(f"[OpenClaw分析] 轮询异常 ({attempt}): {e}")

        return {
            "status": "timeout",
            "model_results": [],
            "aggregation": "分析超时，请稍后查看结果。",
        }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_provider.py::TestOpenClawProvider -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm/providers/openclaw_provider.py backend/tests/test_llm_provider.py
git commit -m "feat: add OpenClaw LLM Provider with multi-model analysis"
```

---

## Task 5: Config 新增 LLM Provider 配置 + 敏感信息清理

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/openclaw_analyze.py`
- Modify: `backend/app/.env.example`

**Step 1: 修改 config.py 添加新的 LLM 配置字段**

在 `backend/app/config.py` 的 `Settings` 类中，在现有 OpenAI 配置之前添加：

```python
    # === LLM Provider 统一配置 ===
    llm_provider: str = "openai"  # openai | ollama | openclaw
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    llm_model: str = "gpt-4o-mini"
    llm_vision_model: str = "gpt-4o"

    # Ollama 本地模型配置
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"

    # OpenClaw 多模型分析配置（可选）
    openclaw_analyze_url: Optional[str] = None
    openclaw_analyze_api_key: Optional[str] = None
    openclaw_analyze_user_id: Optional[str] = None
```

保留现有的 `openai_api_key`、`openai_base_url`、`openai_model`、`openclaw_base_url`、`openclaw_api_key`、`openclaw_model` 作为向后兼容。

**Step 2: 修改 openclaw_analyze.py 移除硬编码**

将 `backend/app/services/openclaw_analyze.py` 中的硬编码常量改为从 config 读取：

```python
"""OpenClaw 多模型分析客户端（向后兼容包装器）"""
import logging
from typing import Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)


class OpenClawAnalyzeClient:
    """OpenClaw 多模型分析客户端 - 现在委托给 LLM Provider"""

    async def analyze(self, prompt: str) -> Dict[str, Any]:
        from app.services.llm import get_llm_provider
        provider = get_llm_provider()
        return await provider.multi_model_analyze(prompt)
```

**Step 3: 更新 .env.example**

在 `backend/.env.example` 中添加 LLM Provider 配置示例：

```env
# === LLM Provider Configuration ===
# Provider: openai | ollama | openclaw
LLM_PROVIDER=openai

# For OpenAI / DeepSeek / any OpenAI-compatible API:
LLM_API_KEY=sk-your-api-key
# LLM_BASE_URL=https://api.openai.com/v1  # Optional proxy
LLM_MODEL=gpt-4o-mini
LLM_VISION_MODEL=gpt-4o

# For Ollama (local models):
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3

# For OpenClaw multi-model analysis (optional):
# OPENCLAW_ANALYZE_URL=https://your-openclaw-server/api/openclaw/analyze
# OPENCLAW_ANALYZE_API_KEY=your-key
# OPENCLAW_ANALYZE_USER_ID=your-user-id
```

**Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/test_llm_provider.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/openclaw_analyze.py backend/.env.example
git commit -m "feat: add LLM Provider config, remove hardcoded API keys"
```

---

## Task 6: 重构 LLMHealthAnalyzer 使用 Provider

**Files:**
- Modify: `backend/app/services/llm_health_analyzer.py`
- Test: `backend/tests/test_llm_refactor.py`

这是重构的关键示范：展示如何将现有 OpenAI SDK 调用迁移到 LLM Provider。

**Step 1: Write the failing test**

```python
# backend/tests/test_llm_refactor.py
"""验证 LLM 服务重构后仍正常工作"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestLLMHealthAnalyzerRefactored:
    """验证 LLMHealthAnalyzer 使用 LLM Provider"""

    @pytest.mark.asyncio
    async def test_analyze_with_prompt_uses_provider(self):
        """确认 analyze_with_prompt 走 LLM Provider 而非直接 OpenAI"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(return_value="分析结果：一切正常")

        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            result = await analyzer.analyze_with_prompt(
                system_prompt="你是健康分析师",
                user_prompt="分析我的数据",
            )
            assert result == "分析结果：一切正常"
            mock_provider.chat.assert_called_once()

    def test_is_available_checks_provider(self):
        """确认 is_available 检查 Provider 而非 OpenAI client"""
        from app.services.llm_health_analyzer import LLMHealthAnalyzer

        mock_provider = MagicMock()
        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=mock_provider):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.is_available() is True

        with patch("app.services.llm_health_analyzer.get_llm_provider", return_value=None):
            analyzer = LLMHealthAnalyzer()
            assert analyzer.is_available() is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_llm_refactor.py -v`
Expected: FAIL

**Step 3: Modify LLMHealthAnalyzer**

修改 `backend/app/services/llm_health_analyzer.py` 的 `__init__` 和 `analyze_with_prompt` 方法：

将原有的 OpenAI 客户端初始化：
```python
# 旧代码（删除）
from openai import OpenAI
self.client = OpenAI(api_key=settings.openai_api_key)
```

替换为：
```python
# 新代码
from app.services.llm import get_llm_provider
self._provider = None
try:
    self._provider = get_llm_provider()
except Exception:
    logger.warning("LLM Provider 初始化失败，将使用纯规则分析")
```

修改 `is_available()`：
```python
def is_available(self) -> bool:
    return self._provider is not None
```

修改 `analyze_with_prompt()`：
```python
async def analyze_with_prompt(self, system_prompt, user_prompt, temperature=0.7, max_tokens=2000):
    if not self.is_available():
        raise Exception("LLM 服务不可用，请配置 LLM Provider")

    return await self._provider.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
```

同样修改 `analyze_daily_health()` 和 `generate_weekly_report()` 中的 `self.client.chat.completions.create()` 调用，改为 `await self._provider.chat(messages=[...])` 并解析返回的字符串。

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_llm_refactor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/app/services/llm_health_analyzer.py backend/tests/test_llm_refactor.py
git commit -m "refactor: migrate LLMHealthAnalyzer to LLM Provider"
```

---

## Task 7: 重构剩余 LLM 服务

**Files:**
- Modify: `backend/app/services/ai/food_recognition.py`
- Modify: `backend/app/services/health_analysis.py`
- Modify: `backend/app/services/smart_plan_service.py`
- Modify: `backend/app/services/ai_insights_service.py`
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/services/health_trend_service.py`
- Modify: `backend/app/api/vision.py`

**迁移模式**（每个文件重复此模式）：

1. **找到 LLM 调用点**（`openai.ChatCompletion.create()` 或 `httpx.AsyncClient().post()`）

2. **替换为 Provider 调用**：
   ```python
   # 旧代码
   from openai import OpenAI
   client = OpenAI(api_key=settings.openai_api_key)
   response = client.chat.completions.create(model="gpt-4o-mini", messages=[...])
   result = response.choices[0].message.content

   # 新代码
   from app.services.llm import get_llm_provider
   provider = get_llm_provider()
   result = await provider.chat(messages=[...])
   ```

3. **视觉服务替换**（food_recognition, vision）：
   ```python
   # 旧代码
   response = client.chat.completions.create(model="gpt-4o", messages=[含图片消息])

   # 新代码
   result = await provider.chat_with_vision(messages=[...], images=[base64_data])
   ```

4. **流式服务替换**（chat_service）：
   ```python
   # 旧代码（_call_openclaw_stream）
   async with httpx.AsyncClient() as client:
       async with client.stream("POST", url, ...) as resp:
           ...

   # 新代码
   provider = get_llm_provider()
   async for token in await provider.chat(messages=[...], stream=True):
       yield token
   ```

5. **多模型分析替换**（health_trend_service, post_run_analyze）：
   ```python
   # 旧代码
   from app.services.openclaw_analyze import OpenClawAnalyzeClient
   client = OpenClawAnalyzeClient()
   result = await client.analyze(prompt)

   # 新代码
   provider = get_llm_provider()
   result = await provider.multi_model_analyze(prompt)
   ```

**关键文件改动说明：**

- **chat_service.py**: 最大改动。`_call_openclaw()` 和 `_call_openclaw_stream()` 改为调用 `provider.chat()` 和 `provider.chat(stream=True)`。保留 `_build_health_context()` 和 `_get_system_prompt()` 不变。
- **food_recognition.py**: `recognize_food_from_base64()` 改为 `provider.chat_with_vision()`
- **vision.py** (API 层): 同上，vision 分析改为 Provider 调用
- **smart_plan_service.py**: `_call_llm()` 改为 `provider.chat()`
- **ai_insights_service.py**: HTTP 调用改为 `provider.chat()`
- **health_trend_service.py**: `OpenClawAnalyzeClient` 改为 `provider.multi_model_analyze()`

**Step 1: 逐文件修改并验证**

每修改一个文件后运行现有测试确认不破坏：
```bash
cd backend && python -m pytest tests/ -v --timeout=30
```

**Step 2: Commit**

```bash
git add backend/app/services/ backend/app/api/vision.py
git commit -m "refactor: migrate all LLM services to unified Provider"
```

---

## Task 8: Dockerfile.backend

**Files:**
- Create: `Dockerfile.backend`
- Create: `backend/docker-entrypoint.sh`

**Step 1: Write Dockerfile**

```dockerfile
# Dockerfile.backend
FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY backend/ .

# 入口脚本
COPY backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Write entrypoint script**

```bash
#!/bin/bash
# backend/docker-entrypoint.sh
set -e

echo "=== Health App Backend Starting ==="

# 等待 PostgreSQL 就绪
if [ -n "$POSTGRES_HOST" ]; then
    echo "Waiting for PostgreSQL at $POSTGRES_HOST:${POSTGRES_PORT:-5432}..."
    for i in $(seq 1 30); do
        if python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('${POSTGRES_HOST}', ${POSTGRES_PORT:-5432}))
    s.close()
    exit(0)
except:
    exit(1)
" 2>/dev/null; then
            echo "PostgreSQL is ready!"
            break
        fi
        echo "Attempt $i/30: PostgreSQL not ready, waiting..."
        sleep 2
    done
fi

# 初始化数据库表（SQLAlchemy create_all）
echo "Initializing database tables..."
python -c "
from app.database import engine, Base
from app.models import *
Base.metadata.create_all(bind=engine)
print('Database tables initialized successfully')
"

echo "Starting application..."
exec "$@"
```

**Step 3: Commit**

```bash
git add Dockerfile.backend backend/docker-entrypoint.sh
git commit -m "feat: add backend Dockerfile with entrypoint"
```

---

## Task 9: Dockerfile.frontend

**Files:**
- Create: `Dockerfile.frontend`

**Step 1: Write Dockerfile**

```dockerfile
# Dockerfile.frontend
FROM node:18-alpine AS builder

WORKDIR /app

# 安装依赖
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install

# 构建
COPY frontend/ .

# 设置构建时环境变量
ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

RUN npm run build

# 运行阶段
FROM node:18-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# 复制构建产物
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]
```

注意：需要在 `frontend/next.config.js` 中添加 `output: "standalone"` 配置才能使用 standalone 模式。如果不方便修改，改用以下替代方案：

```dockerfile
# 替代方案（不需要 standalone）
FROM node:18-alpine

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --legacy-peer-deps 2>/dev/null || npm install

COPY frontend/ .

ARG BACKEND_URL=http://backend:8000
ENV BACKEND_URL=$BACKEND_URL

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
```

**Step 2: Commit**

```bash
git add Dockerfile.frontend
git commit -m "feat: add frontend Dockerfile"
```

---

## Task 10: Docker Compose

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example` (根目录)

**Step 1: Write docker-compose.yml**

```yaml
# docker-compose.yml
# Health Management System - 一键启动
# Usage: cp .env.example .env && docker compose up -d

version: "3.8"

services:
  # PostgreSQL 数据库
  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-health_db}
      POSTGRES_USER: ${POSTGRES_USER:-health_user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-health123}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-health_user}"]
      interval: 5s
      timeout: 5s
      retries: 5

  # Redis 缓存 + 消息队列
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  # FastAPI 后端
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    restart: unless-stopped
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:-health_db}
      - POSTGRES_USER=${POSTGRES_USER:-health_user}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-health123}
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - DEVICE_ENCRYPTION_KEY=${DEVICE_ENCRYPTION_KEY:-}
      - GARMIN_ENCRYPTION_KEY=${GARMIN_ENCRYPTION_KEY:-}
      # LLM Provider
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL:-}
      - LLM_MODEL=${LLM_MODEL:-gpt-4o-mini}
      - LLM_VISION_MODEL=${LLM_VISION_MODEL:-gpt-4o}
      - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
      - OLLAMA_MODEL=${OLLAMA_MODEL:-llama3}
      # 可选服务
      - OPENCLAW_BASE_URL=${OPENCLAW_BASE_URL:-}
      - OPENCLAW_API_KEY=${OPENCLAW_API_KEY:-}
      - OPENCLAW_MODEL=${OPENCLAW_MODEL:-openclaw:main}
      - APP_ENV=${APP_ENV:-production}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Celery Worker（异步任务）
  celery-worker:
    build:
      context: .
      dockerfile: Dockerfile.backend
    restart: unless-stopped
    command: celery -A app.celery_app worker -l info -c 2
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:-health_db}
      - POSTGRES_USER=${POSTGRES_USER:-health_user}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-health123}
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - LLM_PROVIDER=${LLM_PROVIDER:-openai}
      - LLM_API_KEY=${LLM_API_KEY}
      - LLM_BASE_URL=${LLM_BASE_URL:-}
      - LLM_MODEL=${LLM_MODEL:-gpt-4o-mini}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Celery Beat（定时任务调度）
  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile.backend
    restart: unless-stopped
    command: celery -A app.celery_app beat -l info
    environment:
      - POSTGRES_HOST=db
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:-health_db}
      - POSTGRES_USER=${POSTGRES_USER:-health_user}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-health123}
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  # Next.js 前端
  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
      args:
        BACKEND_URL: http://backend:8000
    restart: unless-stopped
    ports:
      - "${FRONTEND_PORT:-3000}:3000"
    depends_on:
      - backend

volumes:
  pgdata:
  redisdata:
```

**Step 2: Write root .env.example**

```env
# ============================================
# Health Management System Configuration
# ============================================
# Copy this file to .env and fill in your values:
#   cp .env.example .env
#
# Then start the system:
#   docker compose up -d
# ============================================

# --- Required ---

# JWT secret key (generate: python3 -c "import secrets; print(secrets.token_urlsafe(32))")
SECRET_KEY=change-me-to-a-random-string

# LLM API Key (required for AI features)
# Get yours at: https://platform.openai.com/api-keys
LLM_API_KEY=sk-your-api-key-here

# --- LLM Provider ---
# Options: openai (default) | ollama | openclaw
LLM_PROVIDER=openai

# For OpenAI / DeepSeek / compatible APIs:
LLM_MODEL=gpt-4o-mini
LLM_VISION_MODEL=gpt-4o
# LLM_BASE_URL=https://api.openai.com/v1  # Uncomment to use proxy

# For Ollama (local models - no API key needed):
# LLM_PROVIDER=ollama
# OLLAMA_BASE_URL=http://host.docker.internal:11434
# OLLAMA_MODEL=llama3

# --- Database ---
POSTGRES_DB=health_db
POSTGRES_USER=health_user
POSTGRES_PASSWORD=health123

# --- Ports ---
FRONTEND_PORT=3000
BACKEND_PORT=8000

# --- Optional: Encryption Keys ---
# Generate: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# DEVICE_ENCRYPTION_KEY=
# GARMIN_ENCRYPTION_KEY=

# --- Optional: Device Integrations ---
# GARMIN_EMAIL=
# GARMIN_PASSWORD=

# --- Optional: OpenClaw (multi-model analysis) ---
# OPENCLAW_BASE_URL=
# OPENCLAW_API_KEY=
# OPENCLAW_MODEL=openclaw:main
```

**Step 3: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat: add Docker Compose for one-click deployment"
```

---

## Task 11: .dockerignore + 构建验证

**Files:**
- Create: `.dockerignore`
- Verify: Docker build works

**Step 1: Write .dockerignore**

```
# .dockerignore
.git
.gitignore
*.md
docs/
.env
.env.local
.claude/

# Python
backend/venv/
backend/__pycache__/
backend/.pytest_cache/
backend/.coverage
backend/*.pyc
backend/health.db

# Node
frontend/node_modules/
frontend/.next/
frontend/.env.local

# OS
.DS_Store
*.swp
```

**Step 2: Verify Docker build**

```bash
# 验证后端镜像构建
docker build -f Dockerfile.backend -t health-backend .

# 验证前端镜像构建
docker build -f Dockerfile.frontend -t health-frontend .
```

**Step 3: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for Docker builds"
```

---

## Task 12: 整体集成验证

**Step 1: 运行全部测试**

```bash
cd backend && python -m pytest tests/ -v --timeout=60
```

确认所有现有测试 + 新增的 LLM Provider 测试都通过。

**Step 2: 验证 Docker Compose 启动**

```bash
# 从项目根目录
cp .env.example .env
# 编辑 .env 填入真实的 LLM_API_KEY 和 SECRET_KEY

docker compose up -d

# 等待服务启动
sleep 15

# 检查服务状态
docker compose ps

# 检查后端健康
curl http://localhost:8000/health

# 检查前端
curl -s http://localhost:3000 | head -5

# 清理
docker compose down -v
```

**Step 3: Commit final state**

```bash
git add -A
git commit -m "feat: open-source Phase 1 complete - LLM Provider + Docker Compose"
```

---

## 总结

| Task | 内容 | 关键文件 |
|------|------|---------|
| 1 | LLM Provider 基础接口 + 工厂 | `backend/app/services/llm/` |
| 2 | OpenAI Provider | `providers/openai_provider.py` |
| 3 | Ollama Provider | `providers/ollama_provider.py` |
| 4 | OpenClaw Provider | `providers/openclaw_provider.py` |
| 5 | Config 新增 + 敏感信息清理 | `config.py`, `openclaw_analyze.py` |
| 6 | 重构 LLMHealthAnalyzer | `llm_health_analyzer.py` |
| 7 | 重构剩余 LLM 服务 | `chat_service.py`, `food_recognition.py` 等 |
| 8 | Dockerfile.backend | `Dockerfile.backend` |
| 9 | Dockerfile.frontend | `Dockerfile.frontend` |
| 10 | Docker Compose | `docker-compose.yml`, `.env.example` |
| 11 | .dockerignore + 构建验证 | `.dockerignore` |
| 12 | 集成验证 | 全部测试 + Docker 启动 |

**依赖关系**：
- Tasks 1-4 可并行（LLM Provider 各实现）
- Task 5 依赖 Tasks 1-4
- Tasks 6-7 依赖 Task 5
- Tasks 8-11 可并行（Docker 相关，独立于 LLM 重构）
- Task 12 依赖所有任务
