"""LLM 用量追踪器测试 - 覆盖 model 名称解析 + caller 绑定 + unknown 诊断."""
import asyncio
import logging

import pytest

from app.services.llm.usage_tracker import (
    begin_usage_capture,
    end_usage_capture,
    summarize_usage_capture,
    set_caller,
    wrap_provider,
    record_usage,
    _caller_ctx,
)
from app.models.llm_usage import LlmUsageLog


class _FakeProvider:
    """模拟 LLMProvider —  暴露 self.model 与 provider_name."""
    def __init__(self, model="gpt-4o-mini"):
        self.model = model
        self.provider_name = "fake"

    async def chat(self, messages, model=None, temperature=0.7, max_tokens=2000, stream=False, **kwargs):
        return "完成回复"


@pytest.fixture
def patch_session(monkeypatch, db):
    """让 record_usage 写入测试 SessionLocal."""
    class _Ctx:
        def __enter__(self): return db
        def __exit__(self, *a): pass

    monkeypatch.setattr(
        "app.database.SessionLocal",
        lambda: _Ctx(),
    )
    yield db


@pytest.fixture(autouse=True)
def _reset_caller():
    """每个测试重置 ContextVar，避免泄漏。"""
    token = _caller_ctx.set(None)
    yield
    _caller_ctx.reset(token)


def test_wrap_provider_resolves_model_from_self_model(patch_session):
    """provider.model='gpt-4o-mini' → log row 的 model 字段非 'unknown'."""
    provider = wrap_provider(_FakeProvider(model="gpt-4o-mini"))
    set_caller("test.case_a", user_id=42)
    asyncio.run(provider.chat(messages=[{"role": "user", "content": "hi"}]))

    rows = patch_session.query(LlmUsageLog).all()
    assert len(rows) == 1
    assert rows[0].model == "gpt-4o-mini"
    assert rows[0].caller == "test.case_a"
    assert rows[0].user_id == 42
    assert rows[0].cost_usd > 0  # 价格表命中, cost 非 0


def test_wrap_provider_unknown_caller_logs_warning(patch_session, caplog):
    """没调 set_caller → caller=unknown，并打 warning 含 stack。"""
    provider = wrap_provider(_FakeProvider())
    with caplog.at_level(logging.WARNING, logger="app.services.llm.usage_tracker"):
        asyncio.run(provider.chat(messages=[{"role": "user", "content": "hi"}]))

    rows = patch_session.query(LlmUsageLog).all()
    assert len(rows) == 1
    assert rows[0].caller == "unknown"

    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("caller=unknown" in r.message and "stack" in r.message for r in warnings)


def test_wrap_provider_param_model_overrides_self(patch_session):
    """chat(messages, model='gpt-4o') 时, 显式参数优先于 self.model."""
    provider = wrap_provider(_FakeProvider(model="gpt-4o-mini"))
    set_caller("test.override")
    asyncio.run(provider.chat(messages=[{"role": "user", "content": "hi"}], model="gpt-4o"))

    rows = patch_session.query(LlmUsageLog).all()
    assert rows[0].model == "gpt-4o"


def test_wrap_provider_idempotent():
    """重复 wrap 同一个实例不应叠层包装。"""
    p = _FakeProvider()
    wrap_provider(p)
    first = p.chat
    wrap_provider(p)
    assert p.chat is first


def test_record_usage_failsoft_on_db_error(monkeypatch, caplog):
    """DB 异常时 record_usage 不抛, 只 log。"""
    class _Boom:
        def __enter__(self): raise RuntimeError("db down")
        def __exit__(self, *a): pass
    monkeypatch.setattr("app.database.SessionLocal", lambda: _Boom())

    with caplog.at_level(logging.WARNING, logger="app.services.llm.usage_tracker"):
        record_usage(
            provider="fake",
            model="gpt-4o-mini",
            prompt_text="hi",
            completion_text="ok",
            caller="test.failsoft",
        )

    assert any("写日志失败" in r.message for r in caplog.records)


def test_usage_capture_summarizes_calls_and_resets(patch_session):
    """请求级 capture 汇总本轮每次 LLM 调用的输入/输出 token, 且 reset 后不串轮."""
    token = begin_usage_capture()
    try:
        record_usage(
            provider="fake",
            model="gpt-4o-mini",
            prompt_text="hello world",
            completion_text="ok",
            caller="test.capture",
            user_id=7,
            latency_ms=123,
        )
        summary = summarize_usage_capture()
    finally:
        end_usage_capture(token)

    assert summary is not None
    assert summary["calls"] == 1
    assert summary["prompt_tokens"] > 0
    assert summary["completion_tokens"] > 0
    assert summary["total_tokens"] == summary["prompt_tokens"] + summary["completion_tokens"]
    assert summary["latency_ms"] == 123
    assert summary["models"] == ["gpt-4o-mini"]
    assert summary["items"][0]["caller"] == "test.capture"
    assert summary["items"][0]["prompt_tokens"] == summary["prompt_tokens"]
    assert summarize_usage_capture() is None
