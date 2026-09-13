"""Provider adapters preserve completion evidence rather than inventing stop."""
from unittest.mock import MagicMock

import pytest

from app.services.agent_executor import AgentExecutor
from app.services.llm.base import LLMProvider
from app.services.llm.providers.ollama_provider import OllamaProvider
from tests.test_llm_provider import _mock_httpx_client

pytestmark = pytest.mark.usefixtures("mock_ai_consent_for_provider_protocol")


class MetadataProvider(LLMProvider):
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    async def chat(self, **kwargs):
        self.kwargs = kwargs
        return self.response

    async def chat_with_vision(self, **kwargs):
        raise AssertionError("not a vision request")


@pytest.mark.asyncio
@pytest.mark.parametrize("response,reason", [
    ("INCOMPLETE", "error"),
    ({"content": "INCOMPLETE"}, None),
    ({"content": "INCOMPLETE", "finish_reason": "length"}, "length"),
    ({"content": "complete", "finish_reason": "stop"}, "stop"),
])
async def test_default_and_gateway_adapters_do_not_create_stop(response, reason):
    provider = MetadataProvider(response)
    events = [e async for e in provider.chat_stream(messages=[])]
    assert provider.kwargs["return_metadata"] is True
    assert events[-1] == {"type": "finish", "finish_reason": reason}
    gateway = [e async for e in AgentExecutor._result_to_stream_events(response)]
    assert gateway[-1] == events[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize("completion,expected", [
    ({"done": True, "done_reason": "stop"}, "stop"),
    ({"done": True, "done_reason": "length"}, "length"),
    ({"done": True, "done_reason": "error"}, "error"),
    ({"done": True}, "error"),
    ({"done": False, "done_reason": "stop"}, "error"),
    ({"done": 1, "done_reason": "stop"}, "error"),
    ({"done_reason": "stop"}, "error"),
    ({}, "error"),
])
async def test_ollama_metadata_requires_real_done_and_reason(monkeypatch, completion, expected):
    response = MagicMock()
    response.json.return_value = {"message": {"content": " text "}, **completion}
    client_cls, client = _mock_httpx_client(post_response=response)
    monkeypatch.setattr("app.services.llm.providers.ollama_provider.httpx.AsyncClient", client_cls)
    provider = OllamaProvider()
    assert await provider.chat(messages=[]) == "text"
    assert await provider.chat(messages=[], return_metadata=True) == {
        "content": "text", "finish_reason": expected,
    }
    events = [e async for e in provider.chat_stream(messages=[])]
    assert events[-1] == {"type": "finish", "finish_reason": expected}
    assert all("return_metadata" not in call.kwargs["json"] for call in client.post.call_args_list)
