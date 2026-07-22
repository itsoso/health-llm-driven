"""Admin LLM usage dashboard: global and per-user token/cost metering."""
from datetime import datetime, timezone
import math
import uuid

import pytest

from app.models.llm_usage import LlmUsageLog
from app.models.user import User
from app.services.auth import auth_service


def _make_user(db, *, admin: bool = False, name: str = "用户") -> User:
    user = User(
        username=f"u_{uuid.uuid4().hex[:8]}",
        email=f"u_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        name=name,
        is_active=True,
        is_approved=True,
        is_admin=admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    token = auth_service.create_access_token({"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _log(
    db,
    *,
    user_id: int,
    provider: str,
    model: str,
    caller: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int | None = None,
    success: int = 1,
    latency_ms: int = 1200,
    cost_usd: float = 0.01,
    error_type: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    tokenplan_credits_estimate: float | None = None,
    tokenplan_cost_cny: float | None = None,
    tokenplan_payg_value_cny: float | None = None,
    tokenplan_cost_estimated: int | None = None,
    tokenplan_cost_source: str | None = None,
    tokenplan_monthly_fee_cny: float | None = None,
    tokenplan_monthly_credits: int | None = None,
    created_at: datetime | None = None,
) -> None:
    db.add(
        LlmUsageLog(
            user_id=user_id,
            provider=provider,
            model=model,
            caller=caller,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
            error_code=error_code,
            error_message=error_message,
            tokenplan_credits_estimate=tokenplan_credits_estimate,
            tokenplan_cost_cny=tokenplan_cost_cny,
            tokenplan_payg_value_cny=tokenplan_payg_value_cny,
            tokenplan_cost_estimated=tokenplan_cost_estimated,
            tokenplan_cost_source=tokenplan_cost_source,
            tokenplan_monthly_fee_cny=tokenplan_monthly_fee_cny,
            tokenplan_monthly_credits=tokenplan_monthly_credits,
            created_at=created_at or datetime.now(timezone.utc),
        )
    )
    db.commit()


def test_usage_dashboard_requires_admin(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="MiniMax-M2.5",
        caller="agent.chat",
        prompt_tokens=100,
        completion_tokens=50,
    )

    response = client.get("/api/v1/admin/llm/usage-dashboard", headers=headers)

    assert response.status_code == 403


def test_usage_dashboard_reports_global_user_and_plan_cost(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    alice = _make_user(db, name="Alice")
    bob = _make_user(db, name="Bob")

    _log(
        db,
        user_id=alice.id,
        provider="tokenplan",
        model="MiniMax-M2.5",
        caller="agent.chat",
        prompt_tokens=7000,
        completion_tokens=3000,
    )
    # Legacy TokenPlan rows were historically logged as provider=openai.
    _log(
        db,
        user_id=bob.id,
        provider="openai",
        model="qwen3.6-plus",
        caller="watch.ask",
        prompt_tokens=2500,
        completion_tokens=2500,
    )
    _log(
        db,
        user_id=bob.id,
        provider="openai",
        model="gpt-4o-mini",
        caller="admin.ping",
        prompt_tokens=1000,
        completion_tokens=2000,
        success=0,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["plan"]["monthly_budget_cny"] == 698.0
    assert payload["overall"]["calls"] == 3
    assert payload["overall"]["failed_calls"] == 1
    assert payload["overall"]["total_tokens"] == 18000
    assert payload["overall"]["tokenplan_tokens"] == 15000
    assert payload["overall"]["tokenplan_calls"] == 2
    assert payload["overall"]["effective_cny_per_1k_tokens"] > 0

    by_user = {row["user_id"]: row for row in payload["by_user"]}
    assert by_user[alice.id]["total_tokens"] == 10000
    assert by_user[alice.id]["tokenplan_tokens"] == 10000
    assert by_user[bob.id]["total_tokens"] == 8000
    assert by_user[bob.id]["tokenplan_tokens"] == 5000
    assert math.isclose(
        by_user[alice.id]["allocated_plan_cost_cny"]
        + by_user[bob.id]["allocated_plan_cost_cny"],
        698.0,
        abs_tol=0.02,
    )

    model_rows = {(row["provider"], row["model"]): row for row in payload["by_model"]}
    assert model_rows[("tokenplan", "MiniMax-M2.5")]["total_tokens"] == 10000
    assert model_rows[("tokenplan", "qwen3.6-plus")]["total_tokens"] == 5000
    assert model_rows[("openai", "gpt-4o-mini")]["failed_calls"] == 1

    caller_rows = {row["caller"]: row for row in payload["by_caller"]}
    assert caller_rows["agent.chat"]["total_tokens"] == 10000
    assert caller_rows["watch.ask"]["provider"] == "tokenplan"


def test_usage_dashboard_reports_tokenplan_quota_guard(client, db, monkeypatch):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_monthly_token_quota", 10_000)

    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=8_000,
        completion_tokens=1_600,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    guard = response.json()["plan"]["quota_guard"]
    assert guard["monthly_token_quota"] == 10_000
    assert guard["tokens_used_month"] == 9_600
    assert guard["quota_utilization_pct"] == 0.96
    assert guard["level"] == "critical"
    assert guard["recommended_runtime_policy"] == "degrade"
    assert any("备用模型" in action for action in guard["suggested_actions"])


def test_usage_dashboard_reports_user_quota_policy_and_rejections(client, db, monkeypatch):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_user_monthly_token_quota", 1_000)
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_user_daily_call_quota", 20)
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_user_monthly_credit_quota", 50.0)

    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=600,
        completion_tokens=100,
        tokenplan_credits_estimate=7.0,
    )
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=0,
        completion_tokens=0,
        success=0,
        error_type="user_monthly_token_limit",
        error_code="llm_budget_exceeded",
        error_message="local quota policy rejected request",
    )
    _log(
        db,
        user_id=admin.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=2_000,
        completion_tokens=500,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    by_user = {row["user_id"]: row for row in response.json()["by_user"]}
    assert by_user[user.id]["quota_policy"]["mode"] == "enforced"
    assert by_user[user.id]["quota_policy"]["monthly_tokens_used"] == 700
    assert by_user[user.id]["quota_policy"]["monthly_token_utilization"] == 0.7
    assert by_user[user.id]["quota_policy"]["rejections_month"] == 1
    assert by_user[admin.id]["quota_policy"]["mode"] == "admin_exempt"
    assert by_user[admin.id]["quota_policy"]["monthly_token_utilization"] is None


def test_usage_dashboard_estimates_cost_for_legacy_zero_cost_rows(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")

    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.chat",
        prompt_tokens=1_000_000,
        completion_tokens=500_000,
        cost_usd=0,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall"]["cost_usd"] == 1.0
    assert payload["overall"]["cost_cny_estimate"] == 7.2
    assert payload["by_user"][0]["cost_usd"] == 1.0


def test_usage_dashboard_converts_tokenplan_credits_to_capacity_rmb(client, db, monkeypatch):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_monthly_budget_cny", 698.0)
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_monthly_credits", 100_000)
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_credits_per_cny", 100.0)
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-max",
        caller="agent.chat",
        prompt_tokens=1_000_000,
        completion_tokens=0,
        cached_tokens=500_000,
        created_at=datetime(2026, 7, 16, tzinfo=timezone.utc),
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["monthly_credits"] == 100_000
    assert payload["plan"]["capacity_cny_per_credit"] == pytest.approx(0.00698)
    assert payload["overall"]["tokenplan_credits_estimate"] == pytest.approx(360.0)
    assert payload["overall"]["tokenplan_capacity_cost_cny"] == pytest.approx(2.5128)
    assert payload["overall"]["tokenplan_payg_value_cny"] == pytest.approx(3.6)
    assert payload["overall"]["cost_savings_vs_payg_cny"] > 0
    assert payload["by_user"][0]["tokenplan_capacity_cost_cny"] == pytest.approx(2.5128)


def test_usage_dashboard_does_not_price_unsupported_cached_rows(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.6-plus",
        caller="agent.chat",
        prompt_tokens=10_000,
        completion_tokens=100,
        cached_tokens=5_000,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["tokenplan_priced_calls"] == 0
    assert overall["tokenplan_unpriced_calls"] == 1
    assert overall["tokenplan_capacity_cost_cny"] is None


def test_usage_dashboard_uses_same_tokenplan_price_override_as_single_calls(client, db, monkeypatch):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    monkeypatch.setattr(
        "app.api.admin_llm.settings.tokenplan_model_pricing_cny_json",
        '{"qwen3.6-plus":[10,20]}',
    )
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.6-plus",
        caller="agent.chat",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["tokenplan_payg_value_cny"] == pytest.approx(10.0)
    assert overall["tokenplan_credits_estimate"] == pytest.approx(1_000.0)
    assert overall["tokenplan_capacity_cost_cny"] == pytest.approx(6.98)


def test_usage_dashboard_marks_unpriced_tokenplan_models_instead_of_fake_zero(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="future-model-without-price",
        caller="agent.chat",
        prompt_tokens=1_000,
        completion_tokens=100,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["tokenplan_priced_calls"] == 0
    assert overall["tokenplan_unpriced_calls"] == 1
    assert overall["tokenplan_capacity_cost_cny"] is None
    assert overall["tokenplan_payg_value_cny"] is None
    assert overall["tokenplan_cost_coverage_complete"] is False


def test_usage_dashboard_keeps_historical_models_when_registry_changes(client, db, monkeypatch):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    monkeypatch.setattr("app.services.llm.model_registry.MODELS", [])
    monkeypatch.setattr("app.api.admin_llm.settings.tokenplan_model", "MiniMax-M2.5")
    _log(
        db,
        user_id=user.id,
        provider="openai",
        model="qwen3.6-plus",
        caller="watch.ask",
        prompt_tokens=1_000,
        completion_tokens=100,
    )

    response = client.get(
        "/api/v1/admin/llm/usage-dashboard?days=30",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    overall = response.json()["overall"]
    assert overall["tokenplan_calls"] == 1
    assert overall["tokenplan_priced_calls"] == 1


def test_performance_stats_is_sqlite_safe_and_normalizes_tokenplan_provider(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    _log(
        db,
        user_id=user.id,
        provider="openai",
        model="MiniMax-M2.5",
        caller="agent.chat",
        prompt_tokens=400,
        completion_tokens=100,
        latency_ms=100,
    )
    _log(
        db,
        user_id=user.id,
        provider="openai",
        model="gpt-4o-mini",
        caller="agent.chat",
        prompt_tokens=100,
        completion_tokens=100,
        latency_ms=300,
        success=0,
    )

    response = client.get(
        "/api/v1/admin/llm/performance-stats?days=30&group_by=provider",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    rows = {row["label"]: row for row in response.json()["stats"]}
    assert rows["tokenplan"]["n"] == 1
    assert rows["tokenplan"]["p50_ms"] == 100
    assert rows["openai"]["success_rate"] == 0.0


def test_recent_calls_and_failures_include_error_context(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=1000,
        completion_tokens=200,
        success=0,
        latency_ms=3210,
        error_type="insufficient_quota",
        error_code="insufficient_quota",
        error_message="Your token-plan quota has been exhausted.",
    )

    calls = client.get(
        "/api/v1/admin/llm/recent-calls?days=30&limit=10",
        headers=_headers(admin),
    )
    assert calls.status_code == 200
    first = calls.json()["calls"][0]
    assert first["user_id"] == user.id
    assert first["email"] == user.email
    assert first["success"] is False
    assert first["total_tokens"] == 1200
    assert first["error_type"] == "insufficient_quota"
    assert "quota" in first["error_message"]

    failures = client.get(
        "/api/v1/admin/llm/performance-failures?days=30&limit=10",
        headers=_headers(admin),
    )
    assert failures.status_code == 200
    failed = failures.json()["failures"][0]
    assert failed["error_code"] == "insufficient_quota"
    assert "quota" in failed["error_message"]


def test_run_detail_groups_llm_calls_by_run_id(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    run_id = "run_abc123"
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=1000,
        completion_tokens=200,
    )
    db.query(LlmUsageLog).order_by(LlmUsageLog.id.desc()).first().run_id = run_id
    _log(
        db,
        user_id=user.id,
        provider="langbridge-proxy",
        model="commercial/GPT-5.5",
        caller="agent.stream",
        prompt_tokens=800,
        completion_tokens=300,
    )
    db.query(LlmUsageLog).order_by(LlmUsageLog.id.desc()).first().run_id = run_id
    db.commit()

    response = client.get(
        f"/api/v1/admin/llm/runs/{run_id}",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == run_id
    assert payload["summary"]["calls"] == 2
    assert payload["summary"]["total_tokens"] == 2300
    assert payload["calls"][0]["run_id"] == run_id


def test_recent_calls_prefers_persisted_tokenplan_cost(client, db):
    admin = _make_user(db, admin=True, name="管理员")
    user = _make_user(db, name="Alice")
    _log(
        db,
        user_id=user.id,
        provider="tokenplan",
        model="qwen3.7-plus",
        caller="agent.stream",
        prompt_tokens=1000,
        completion_tokens=200,
        tokenplan_credits_estimate=7.5,
        tokenplan_cost_cny=0.05235,
        tokenplan_payg_value_cny=0.081,
        tokenplan_cost_estimated=1,
        tokenplan_cost_source="persisted:test-rate",
        tokenplan_monthly_fee_cny=698.0,
        tokenplan_monthly_credits=100_000,
    )

    response = client.get(
        "/api/v1/admin/llm/recent-calls?days=30&limit=10",
        headers=_headers(admin),
    )

    assert response.status_code == 200
    call = response.json()["calls"][0]
    assert call["tokenplan_capacity_cost_cny"] == 0.05235
    assert call["tokenplan_cost_cny"] == 0.05235
    assert call["tokenplan_credits_estimate"] == 7.5
    assert call["tokenplan_payg_value_cny"] == 0.081
    assert call["tokenplan_cost_source"] == "persisted:test-rate"
