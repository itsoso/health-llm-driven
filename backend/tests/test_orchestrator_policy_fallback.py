"""Manual synthesis fallback must retain budget and consent boundaries."""
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.llm.usage_tracker import LLMBudgetExceeded


@pytest.fixture
def providers(monkeypatch):
    import app.services.llm as llm
    import app.services.llm.factory as factory
    import app.services.llm.usage_tracker as tracker
    import app.orchestrator.orchestrator as orchestrator
    from app.config import settings
    primary = SimpleNamespace(chat=AsyncMock())
    primary.provider_name = 'synthetic-primary'
    primary.model = 'synthetic-primary'
    fallback = SimpleNamespace(chat=AsyncMock())
    fallback.provider_name = 'synthetic-fallback'
    fallback.model = 'synthetic-fallback'
    primary.chat.return_value = 'primary result'
    fallback.chat.return_value = 'fallback result'
    fallback.external_chat = fallback.chat
    factory_calls = []
    monkeypatch.setattr(llm, 'get_llm_provider', lambda: primary)
    monkeypatch.setattr(factory, 'create_llm_provider', lambda kind: factory_calls.append(kind) or fallback)
    monkeypatch.setattr(tracker, '_enforce_monthly_token_quota', lambda **kw: None)
    monkeypatch.setattr(tracker, 'record_usage', lambda **kw: None)
    monkeypatch.setattr(settings, 'llm_auto_recovery_enabled', False)
    return orchestrator, primary, fallback, factory_calls


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [
    LLMBudgetExceeded(reason='budget_guard_unavailable'),
    LLMBudgetExceeded(reason='user_monthly_token_limit'),
    HTTPException(503, detail={'code': 'ai_consent_unavailable', 'message': 'SYNTHETIC_PRIVATE_SENTINEL'}),
    HTTPException(403, detail={'code': 'ai_consent_required', 'message': 'SYNTHETIC_PRIVATE_SENTINEL'}),
])
async def test_policy_block_never_constructs_fallback(providers, caplog, error):
    orchestrator, primary, fallback, factory_calls = providers
    primary.chat.side_effect = error
    with pytest.raises(type(error)) as raised:
        await orchestrator._call_llm('synthetic system', 'synthetic input')
    assert raised.value is error
    assert factory_calls == []
    fallback.external_chat.assert_not_called()
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in caplog.text


@pytest.mark.asyncio
async def test_real_provider_failure_recovers_once_without_raw_error_log(providers, caplog):
    orchestrator, primary, fallback, factory_calls = providers
    primary.chat.side_effect = RuntimeError('503 SYNTHETIC_PRIVATE_SENTINEL')
    assert await orchestrator._call_llm('synthetic system', 'synthetic input') == 'fallback result'
    assert factory_calls == ['openai']
    assert fallback.external_chat.await_count == 1
    assert 'SYNTHETIC_PRIVATE_SENTINEL' not in caplog.text


@pytest.mark.asyncio
async def test_fallback_rechecks_budget_before_external_call(providers, monkeypatch):
    orchestrator, primary, fallback, _ = providers
    import app.services.llm.usage_tracker as tracker
    primary.chat.side_effect = RuntimeError('503 synthetic outage')
    def unavailable(**kwargs):
        raise LLMBudgetExceeded(reason='budget_guard_unavailable')
    monkeypatch.setattr(tracker, '_enforce_monthly_token_quota', unavailable)
    with pytest.raises(LLMBudgetExceeded):
        await orchestrator._call_llm('synthetic system', 'synthetic input')
    fallback.external_chat.assert_not_called()
