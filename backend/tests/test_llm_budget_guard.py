from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.services.llm.usage_tracker import LLMBudgetExceeded, _enforce_monthly_token_quota


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
