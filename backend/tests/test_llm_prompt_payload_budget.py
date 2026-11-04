"""Provider-attempt budgets retain no prompt content or invented token truth."""

import asyncio
from copy import deepcopy
import json

import pytest

from app.services.llm import usage_tracker as usage


@pytest.fixture(autouse=True)
def isolated_usage(monkeypatch, db):
    class Session:
        def __enter__(self):
            return db

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("app.database.SessionLocal", Session)
    monkeypatch.setattr(usage, "_enforce_monthly_token_quota", lambda **kwargs: None)
    capture = usage.begin_usage_capture()
    caller = usage._caller_ctx.set("test.payload")
    api = usage._api_usage_ctx.set(None)
    yield
    usage._api_usage_ctx.reset(api)
    usage._caller_ctx.reset(caller)
    usage.end_usage_capture(capture)


MESSAGES = [
    {"role": "system", "content": "private system"},
    {"role": "user", "content": "old correction"},
    {"role": "assistant", "content": None, "tool_calls": [{"id": "private-call", "function": {"arguments": '{"private":42}'}}]},
    {"role": "tool", "content": '{"private_health":42}'},
    {"role": "user", "content": [{"type": "text", "text": "latest private request", "cache_control": {"type": "ephemeral"}}, {"type": "image_url", "image_url": {"url": "https://private.invalid/image"}}]},
]
TOOLS = [{"type": "function", "function": {"name": "private_tool", "description": "private schema", "parameters": {"type": "object"}}}]


class Provider:
    provider_name = "fake"
    model = "gpt-4o-mini"

    def __init__(self, fail=False, mutate=False):
        self.fail = fail
        self.mutate = mutate

    async def chat(self, messages, **kwargs):
        if self.mutate:
            messages.append({"role": "user", "content": "provider mutation"})
            kwargs["tools"].clear()
        if self.fail:
            raise RuntimeError("provider unavailable")
        usage.report_api_usage(1234, 56, 1000)
        return "answer"

    async def chat_stream(self, messages, **kwargs):
        yield {"type": "content", "content": "partial"}
        if self.fail:
            raise RuntimeError("provider unavailable")
        usage.report_api_usage(4321, 65, 2000)


def test_budget_is_numeric_and_preserves_legacy_accounting():
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    messages, tools = deepcopy(MESSAGES), deepcopy(TOOLS)
    result = prompt_payload_budget(messages, tools)
    assert messages == MESSAGES and tools == TOOLS
    assert all(type(value) is int and value >= 0 for value in result.values())
    assert result["system_chars"] == len("private system")
    assert result["dialogue_chars"] == len("old correction")
    assert result["tool_result_chars"] == len('{"private_health":42}')
    assert result["turn_chars"] == len(json.dumps(MESSAGES[-1]["content"], ensure_ascii=False, sort_keys=True, default=str))
    assert result["tool_count"] == 1
    assert result["tool_call_chars"] > 0
    assert result["input_approx_tokens"] == (result["system_chars"] + result["history_chars"] + result["turn_chars"] + result["tool_schema_chars"] + result["tool_call_chars"]) // 4
    assert "private" not in json.dumps(result)
    assert prompt_payload_budget([], None)["input_approx_tokens"] == 0


def test_chat_captures_payload_before_provider_mutation_and_keeps_api_truth():
    from app.services.llm.prompt_payload_budget import prompt_payload_budget
    from app.services.agent_send_meta import _build_usage

    expected = prompt_payload_budget(MESSAGES, TOOLS)
    provider = usage.wrap_provider(Provider(mutate=True), allow_recovery=False)
    asyncio.run(provider.chat(deepcopy(MESSAGES), tools=deepcopy(TOOLS)))
    summary = usage.summarize_usage_capture()
    item = summary["items"][0]
    assert item["prompt_payload"] == expected
    assert (item["prompt_tokens"], item["completion_tokens"], item["cached_tokens"], item["token_source"]) == (1234, 56, 1000, "api")
    assert _build_usage(summary)["items"][0]["prompt_payload"] == expected


@pytest.mark.parametrize("stream,failed", [(False, True), (True, False), (True, True)])
def test_stream_and_failure_attempts_keep_actual_payload(stream, failed):
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    provider = usage.wrap_provider(Provider(fail=failed), allow_recovery=False)

    async def run():
        if stream:
            async for _ in provider.chat_stream(deepcopy(MESSAGES), tools=deepcopy(TOOLS)):
                pass
        else:
            await provider.chat(deepcopy(MESSAGES), tools=deepcopy(TOOLS))

    if failed:
        with pytest.raises(RuntimeError, match="provider unavailable"):
            asyncio.run(run())
    else:
        asyncio.run(run())
    item = usage.summarize_usage_capture()["items"][0]
    assert item["prompt_payload"] == prompt_payload_budget(MESSAGES, TOOLS)
    assert item["success"] is not failed
    if not failed:
        assert (item["prompt_tokens"], item["cached_tokens"]) == (4321, 2000)


def test_fallback_captures_each_attempt_and_its_payload(monkeypatch):
    from app.config import settings
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    class QuotaProvider(Provider):
        async def chat(self, messages, **kwargs):
            raise RuntimeError("Error code: 429 - {'error': {'message': 'quota exhausted', 'type': 'insufficient_quota', 'code': 'insufficient_quota'}}")

    class FallbackProvider(Provider):
        provider_name = "langbridge-proxy"
        model = "commercial/GPT-5.5"

    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)
    monkeypatch.setattr(settings, "llm_recovery_model_id", "gpt-5.5")
    monkeypatch.setattr("app.services.llm.recovery._env_available", lambda model_id: True)
    monkeypatch.setattr("app.services.llm.recovery.create_provider_for_model_id", lambda model_id: usage.wrap_provider(FallbackProvider()))
    provider = usage.wrap_provider(QuotaProvider())
    assert asyncio.run(provider.chat(deepcopy(MESSAGES), tools=deepcopy(TOOLS))) == "answer"
    summary = usage.summarize_usage_capture()
    assert summary["calls"] == 2
    assert [item["success"] for item in summary["items"]] == [False, True]
    assert all(item["prompt_payload"] == prompt_payload_budget(MESSAGES, TOOLS) for item in summary["items"])
    assert summary["items"][1]["token_source"] == "api"


def test_capture_reports_retained_coverage_and_resets():
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    token = usage.begin_usage_capture()
    try:
        for index in range(23):
            usage.record_usage("fake", "gpt-4o-mini", "", "", prompt_payload=prompt_payload_budget([{"role": "user", "content": "x" * index}]) if index else None)
        summary = usage.summarize_usage_capture()
        assert summary["calls"] == 23
        assert summary["captured_items"] == 20
        assert summary["omitted_items"] == 3
        assert summary["prompt_payload_calls"] == 22
        assert summary["prompt_payload_items"] == 20
        assert summary["items"][0]["prompt_payload"]["turn_chars"] == 3
        assert len(summary["items"]) == 20
    finally:
        usage.end_usage_capture(token)
    assert usage.summarize_usage_capture() is None


def test_payload_survives_persisted_answer_metadata(db, auth_user_and_headers):
    from app.api.agent import _persist_done_llm_usage
    from app.models.agent_conversation import AgentConversation, AgentMessage
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    user, _ = auth_user_and_headers
    conversation = AgentConversation(user_id=user.id, title="budget fixture")
    db.add(conversation)
    db.flush()
    message = AgentMessage(conversation_id=conversation.id, role="assistant", content="ok", meta={"existing": 1})
    db.add(message)
    db.commit()
    provider = usage.wrap_provider(Provider(), allow_recovery=False)
    asyncio.run(provider.chat(deepcopy(MESSAGES), tools=deepcopy(TOOLS)))
    _persist_done_llm_usage(db, message.id, usage.summarize_usage_capture())
    db.refresh(message)
    saved = message.meta["llm_usage"]
    assert message.meta["existing"] == 1
    assert saved["items"][0]["prompt_payload"] == prompt_payload_budget(MESSAGES, TOOLS)
    assert saved["prompt_payload_calls"] == saved["prompt_payload_items"] == 1
    assert saved["items"][0]["prompt_tokens"] == 1234
    assert "private" not in json.dumps(saved)


@pytest.mark.asyncio
async def test_cancelled_stream_keeps_payload_and_propagates():
    from app.services.llm.prompt_payload_budget import prompt_payload_budget

    class CancelledProvider(Provider):
        async def chat_stream(self, messages, **kwargs):
            yield {"type": "content", "content": "partial"}
            raise asyncio.CancelledError()

    provider = usage.wrap_provider(CancelledProvider(), allow_recovery=False)
    with pytest.raises(asyncio.CancelledError):
        async for _ in provider.chat_stream(deepcopy(MESSAGES), tools=deepcopy(TOOLS)):
            pass
    item = usage.summarize_usage_capture()["items"][0]
    assert item["prompt_payload"] == prompt_payload_budget(MESSAGES, TOOLS)
    assert item["success"] is False
    assert item["error_class"] == "cancelled"
