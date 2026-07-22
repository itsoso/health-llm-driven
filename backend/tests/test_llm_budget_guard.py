from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.services.llm.usage_tracker import (
    LLMBudgetExceeded,
    _enforce_monthly_token_quota,
    _user_is_admin_ctx,
    _user_id_ctx,
    set_caller,
    wrap_provider,
)


class _ScalarQuery:
    def filter(self, *args, **kwargs):
        return self

    def scalar(self):
        return 99


class _FakeDb:
    def query(self, *args, **kwargs):
        return _ScalarQuery()


def test_tokenplan_budget_guard_blocks_before_provider_call(monkeypatch):
    from app.config import settings
    import app.database

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 100)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: nullcontext(_FakeDb()))
    monkeypatch.setattr(
        "app.services.llm.usage_tracker._estimate_tokens",
        lambda text, model: 10,
    )

    with pytest.raises(LLMBudgetExceeded):
        _enforce_monthly_token_quota(
            provider="tokenplan",
            model="qwen3.7-plus",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=2,
        )


def test_non_tokenplan_is_not_blocked_by_tokenplan_budget(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 1)
    _enforce_monthly_token_quota(
        provider="openai",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=2000,
    )


def test_tokenplan_budget_guard_enforces_per_user_monthly_tokens(monkeypatch):
    from app.config import settings
    import app.database

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 0)
    monkeypatch.setattr(settings, "tokenplan_user_monthly_token_quota", 100)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: nullcontext(_FakeDb()))
    monkeypatch.setattr(
        "app.services.llm.usage_tracker._estimate_tokens",
        lambda text, model: 10,
    )
    token = _user_id_ctx.set(42)
    admin_token = _user_is_admin_ctx.set(False)
    try:
        with pytest.raises(LLMBudgetExceeded) as raised:
            _enforce_monthly_token_quota(
                provider="tokenplan",
                model="qwen3.7-plus",
                messages=[{"role": "user", "content": "hello"}],
                max_tokens=2,
            )
        assert raised.value.reason == "user_monthly_token_limit"
        assert raised.value.scope == "user"
        assert raised.value.retry_at is not None
    finally:
        _user_is_admin_ctx.reset(admin_token)
        _user_id_ctx.reset(token)


def test_tokenplan_budget_guard_exempts_admin_from_per_user_limits(monkeypatch):
    from app.config import settings
    import app.database

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 0)
    monkeypatch.setattr(settings, "tokenplan_user_monthly_token_quota", 100)
    monkeypatch.setattr(settings, "tokenplan_global_daily_call_quota", 0)
    monkeypatch.setattr(settings, "tokenplan_user_daily_call_quota", 1)
    monkeypatch.setattr(settings, "tokenplan_monthly_credits", 0)
    monkeypatch.setattr(settings, "tokenplan_user_monthly_credit_quota", 1)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: nullcontext(_FakeDb()))
    monkeypatch.setattr(
        "app.services.llm.usage_tracker._estimate_tokens",
        lambda text, model: 10,
    )
    user_token = _user_id_ctx.set(42)
    admin_token = _user_is_admin_ctx.set(True)
    try:
        _enforce_monthly_token_quota(
            provider="tokenplan",
            model="qwen3.7-plus",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=2,
        )
    finally:
        _user_is_admin_ctx.reset(admin_token)
        _user_id_ctx.reset(user_token)


def test_tokenplan_budget_guard_resolves_admin_from_database(db, monkeypatch):
    from app.config import settings
    import app.database
    from app.models.user import User

    admin = User(
        username="budget_admin",
        email="budget-admin@example.com",
        hashed_password="x",
        name="Budget Admin",
        is_active=True,
        is_approved=True,
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 0)
    monkeypatch.setattr(settings, "tokenplan_user_monthly_token_quota", 1)
    monkeypatch.setattr(settings, "tokenplan_global_daily_call_quota", 0)
    monkeypatch.setattr(settings, "tokenplan_user_daily_call_quota", 1)
    monkeypatch.setattr(settings, "tokenplan_monthly_credits", 0)
    monkeypatch.setattr(settings, "tokenplan_user_monthly_credit_quota", 1)
    monkeypatch.setattr(app.database, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr(
        "app.services.llm.usage_tracker._estimate_tokens",
        lambda text, model: 10,
    )

    user_token = _user_id_ctx.set(admin.id)
    admin_token = _user_is_admin_ctx.set(None)
    try:
        _enforce_monthly_token_quota(
            provider="tokenplan",
            model="qwen3.7-plus",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=2,
        )
    finally:
        _user_is_admin_ctx.reset(admin_token)
        _user_id_ctx.reset(user_token)


def test_budget_error_has_actionable_user_message():
    from app.services.llm.error_messages import safe_llm_error_message

    monthly = LLMBudgetExceeded(
        reason="user_monthly_token_limit",
        retry_at="2026-08-01T00:00:00+00:00",
    )
    daily = LLMBudgetExceeded(
        reason="user_daily_call_limit",
        retry_at="2026-07-23T00:00:00+00:00",
    )

    assert "下月 1 日恢复" in safe_llm_error_message(monthly)
    assert "内容已保留" in safe_llm_error_message(monthly)
    assert "明日恢复" in safe_llm_error_message(daily)
    assert "下月 1 日恢复" in safe_llm_error_message("user_monthly_token_limit")


def test_new_user_caller_does_not_inherit_admin_exemption():
    admin_token = _user_is_admin_ctx.set(True)
    user_token = _user_id_ctx.set(1)
    try:
        set_caller("agent.stream", user_id=2)
        assert _user_id_ctx.get() == 2
        assert _user_is_admin_ctx.get() is None
    finally:
        _user_id_ctx.reset(user_token)
        _user_is_admin_ctx.reset(admin_token)


@pytest.mark.asyncio
async def test_tokenplan_stream_is_budget_checked_before_provider_call(monkeypatch):
    calls = []

    class _Provider:
        provider_name = "tokenplan"
        model = "qwen3.7-plus"

        async def chat(self, *args, **kwargs):
            return "unused"

        async def chat_stream(self, *args, **kwargs):
            calls.append("provider_called")
            yield {"type": "content", "text": "unsafe"}

    def block(**kwargs):
        raise LLMBudgetExceeded("daily call quota exceeded")

    monkeypatch.setattr(
        "app.services.llm.usage_tracker._enforce_monthly_token_quota",
        block,
    )
    provider = wrap_provider(_Provider())

    with pytest.raises(LLMBudgetExceeded):
        async for _ in provider.chat_stream(
            [{"role": "user", "content": "hello"}],
            max_tokens=20,
        ):
            pass

    assert calls == []
