"""Policy rejections must never be retried as infrastructure failures."""

import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.llm.recovery import diagnose_llm_error
from app.services.llm.usage_tracker import LLMBudgetExceeded, wrap_provider


@pytest.mark.parametrize("error, expected", [
    (LLMBudgetExceeded(reason="user_monthly_token_limit"), "budget_exhausted"),
    (LLMBudgetExceeded(reason="budget_guard_unavailable"), "budget_guard_unavailable"),
    (HTTPException(403, detail={"code": "ai_consent_required"}), "consent_required"),
    (HTTPException(503, detail={"code": "ai_consent_unavailable"}), "consent_unavailable"),
    (HTTPException(403, detail={"code": "ai_recipient_not_disclosed"}), "recipient_not_disclosed"),
])
def test_policy_rejection_is_structured_blocked_and_not_recoverable(error, expected):
    diagnosis = diagnose_llm_error(error)
    assert diagnosis.error_class == expected
    assert diagnosis.execution_status == "blocked"
    assert diagnosis.recoverable is False


@pytest.mark.asyncio
async def test_consent_verifier_unavailable_never_constructs_fallback_provider(monkeypatch):
    import app.services.llm.recovery as recovery
    import app.services.llm.usage_tracker as tracker

    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)
    monkeypatch.setattr(settings, "llm_recovery_model_id", "test-fallback")
    monkeypatch.setattr(recovery, "_env_available", lambda _mid: True)
    monkeypatch.setattr(tracker, "_enforce_monthly_token_quota", lambda **_k: None)
    usage = []
    monkeypatch.setattr(tracker, "record_usage", lambda **kw: usage.append(kw))
    fallback_calls = []

    class Fallback:
        async def chat(self, *_a, **_k):
            fallback_calls.append("external-call")
            return "must not recover authorization errors"

    monkeypatch.setattr(recovery, "create_provider_for_model_id", lambda _mid: Fallback())

    class Primary:
        provider_name = "test-primary"
        model = "test-model"

        async def chat(self, *_a, **_k):
            raise HTTPException(503, detail={"code": "ai_consent_unavailable"})

    provider = wrap_provider(Primary())
    with pytest.raises(HTTPException) as raised:
        await provider.chat([{"role": "user", "content": "synthetic request"}])
    assert raised.value.detail["code"] == "ai_consent_unavailable"
    assert fallback_calls == []
    assert usage[-1]["error_class"] == "consent_unavailable"


def test_provider_outage_is_failed_not_policy_blocked():
    diagnosis = diagnose_llm_error(RuntimeError("503 service unavailable"))
    assert diagnosis.execution_status == "failed"
    assert diagnosis.recoverable is True


@pytest.mark.asyncio
async def test_fallback_policy_block_is_propagated_without_private_error_log(monkeypatch, caplog):
    import app.services.llm.recovery as recovery
    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)

    class Fallback:
        async def chat(self, *_a, **_k):
            raise HTTPException(503, detail={"code": "ai_consent_unavailable", "message": "SYNTHETIC_PRIVATE_SENTINEL"})

    monkeypatch.setattr(recovery, "create_provider_for_model_id", lambda _id: Fallback())
    with pytest.raises(HTTPException) as raised:
        await recovery.try_recover_chat(
            RuntimeError("provider 503"), messages=[], model=None, temperature=0,
            max_tokens=10, primary_provider="test", primary_model="test",
            kwargs={}, recovery_model_id="test-fallback",
        )
    assert raised.value.detail["code"] == "ai_consent_unavailable"
    assert "SYNTHETIC_PRIVATE_SENTINEL" not in caplog.text


@pytest.mark.asyncio
async def test_budget_recovery_still_rechecks_consent_before_external_io(monkeypatch):
    import app.services.llm.usage_tracker as tracker

    state = {"budget_blocked": True, "consented": False}
    calls = []
    retry_at = "2026-10-01T00:00:00+00:00"

    def budget_check(**_kwargs):
        calls.append("budget_check")
        if state["budget_blocked"]:
            raise LLMBudgetExceeded(reason="user_monthly_token_limit", retry_at=retry_at)

    class Provider:
        provider_name = "test-primary"
        model = "test-model"

        async def chat(self, *_a, **_k):
            calls.append("consent_check")
            if not state["consented"]:
                raise HTTPException(403, detail={"code": "ai_consent_required"})
            calls.append("external_call")
            return "synthetic response"

    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)
    monkeypatch.setattr(tracker, "_enforce_monthly_token_quota", budget_check)
    monkeypatch.setattr(tracker, "record_usage", lambda **_kw: None)
    provider = wrap_provider(Provider())
    messages = [{"role": "user", "content": "synthetic request"}]
    with pytest.raises(LLMBudgetExceeded) as blocked:
        await provider.chat(messages)
    assert diagnose_llm_error(blocked.value).retry_at == retry_at
    assert calls == ["budget_check"]

    state["budget_blocked"] = False
    with pytest.raises(HTTPException):
        await provider.chat(messages)
    assert "external_call" not in calls

    state["consented"] = True
    assert await provider.chat(messages) == "synthetic response"
    assert calls.count("budget_check") == 3
    assert calls.count("consent_check") == 2
    assert calls.count("external_call") == 1
