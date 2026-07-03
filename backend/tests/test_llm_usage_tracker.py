"""LLM 用量追踪器测试 - 覆盖 model 名称解析 + caller 绑定 + unknown 诊断."""
import asyncio
import logging

import pytest

from app.services.llm.usage_tracker import (
    begin_usage_capture,
    clear_run_id,
    end_usage_capture,
    summarize_usage_capture,
    set_caller,
    set_run_id,
    wrap_provider,
    record_usage,
    estimate_usage_cost,
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


class _FailingProvider(_FakeProvider):
    """模拟 provider 抛出上游 429/额度类异常."""

    async def chat(self, messages, model=None, temperature=0.7, max_tokens=2000, stream=False, **kwargs):
        raise RuntimeError(
            "Error code: 429 - {'error': {'message': 'Your token-plan quota has been exhausted.', "
            "'type': 'insufficient_quota', 'code': 'insufficient_quota'}}"
        )


class _FallbackProvider(_FakeProvider):
    def __init__(self, model="commercial/GPT-5.5"):
        super().__init__(model=model)
        self.provider_name = "langbridge-proxy"

    async def chat(self, messages, model=None, temperature=0.7, max_tokens=2000, stream=False, **kwargs):
        return "备用模型回复"


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
    run_token = set_run_id(None)
    yield
    _caller_ctx.reset(token)
    clear_run_id(run_token)


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


def test_usage_capture_carries_run_id_to_rows_and_summary(patch_session):
    run_token = set_run_id("run_123")
    token = begin_usage_capture()
    try:
        record_usage(
            provider="fake",
            model="gpt-4o-mini",
            prompt_text="hello",
            completion_text="ok",
            caller="test.run",
            user_id=7,
        )
        summary = summarize_usage_capture()
    finally:
        end_usage_capture(token)
        clear_run_id(run_token)

    row = patch_session.query(LlmUsageLog).one()
    assert row.run_id == "run_123"
    assert summary["run_id"] == "run_123"
    assert summary["items"][0]["run_id"] == "run_123"


def test_wrap_provider_records_failure_error_context(patch_session, monkeypatch):
    """失败调用也要落每次调用账本,并保留可诊断的上游错误摘要."""
    from app.config import settings

    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", False)
    provider = wrap_provider(_FailingProvider(model="qwen3.7-plus"))
    set_caller("test.quota", user_id=99)
    token = begin_usage_capture()
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(provider.chat(messages=[{"role": "user", "content": "帮我分析"}]))
        summary = summarize_usage_capture()
    finally:
        end_usage_capture(token)

    rows = patch_session.query(LlmUsageLog).all()
    assert len(rows) == 1
    assert rows[0].success == 0
    assert rows[0].error_type == "insufficient_quota"
    assert rows[0].error_code == "insufficient_quota"
    assert "token-plan quota" in rows[0].error_message
    assert summary is not None
    assert summary["failed_calls"] == 1
    assert summary["items"][0]["error_type"] == "insufficient_quota"


def test_tokenplan_qwen_cost_is_estimated_and_exposed(patch_session):
    """TokenPlan/Qwen 新模型要有费用估算,不能因为旧价格表缺失显示 0."""
    token = begin_usage_capture()
    try:
        record_usage(
            provider="tokenplan",
            model="qwen3.7-plus",
            prompt_text="hello " * 1000,
            completion_text="ok " * 200,
            caller="test.cost",
            user_id=3,
            latency_ms=321,
        )
        summary = summarize_usage_capture()
    finally:
        end_usage_capture(token)

    row = patch_session.query(LlmUsageLog).one()
    assert row.cost_usd > 0
    assert summary is not None
    assert summary["cost_usd"] > 0
    assert summary["cost_cny"] > 0
    assert summary["cost_estimated"] is True
    assert "builtin:qwen3.7-plus" in summary["cost_sources"]
    assert summary["items"][0]["cost_source"] == "builtin:qwen3.7-plus"


def test_model_pricing_json_override(monkeypatch):
    """真实账单口径可通过环境配置覆盖,不需要改代码发版."""
    from app.config import settings

    monkeypatch.setattr(settings, "llm_model_pricing_json", '{"qwen3.7-plus":[2,4]}')
    estimate = estimate_usage_cost("tokenplan", "qwen3.7-plus", 1_000_000, 500_000)

    assert estimate.cost_usd == 4.0
    assert estimate.source == "env:qwen3.7-plus"


def test_wrap_provider_recovers_quota_error_with_fallback_provider(
    patch_session,
    monkeypatch,
):
    """额度类错误自动转备用模型:保留主模型失败账本,返回备用模型结果."""
    from app.config import settings

    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", True)
    monkeypatch.setattr(settings, "llm_recovery_model_id", "gpt-5.5")
    monkeypatch.setattr(
        "app.services.llm.recovery.create_provider_for_model_id",
        lambda model_id: wrap_provider(_FallbackProvider()),
    )
    # env 无关化:gpt-5.5 是 langbridge 条目,registry 按 LANGBRIDGE_* env 门控——
    # 本地带 .env 时 _env_available=True 假绿,CI 无 .env 时 False → 恢复中止 →
    # 429 直抛(CI 唯一红)。本测试的意图是 quota→fallback 流程,不是 env 可用性
    # 策略,故对 availability 打桩。
    monkeypatch.setattr("app.services.llm.recovery._env_available", lambda mid: True)

    provider = wrap_provider(_FailingProvider(model="qwen3.7-plus"))
    set_caller("test.recover", user_id=99)
    token = begin_usage_capture()
    try:
        result = asyncio.run(provider.chat(messages=[{"role": "user", "content": "帮我分析"}]))
        summary = summarize_usage_capture()
    finally:
        end_usage_capture(token)

    assert result == "备用模型回复"
    rows = patch_session.query(LlmUsageLog).order_by(LlmUsageLog.id.asc()).all()
    assert len(rows) == 2
    assert rows[0].success == 0
    assert rows[0].error_class == "quota_exhausted"
    assert rows[0].recovery_action == "fallback_attempted"
    assert rows[0].recovery_model == "gpt-5.5"
    assert rows[1].success == 1
    assert rows[1].provider == "langbridge-proxy"
    assert summary["failed_calls"] == 1
    assert summary["items"][0]["recovery_action"] == "fallback_attempted"
