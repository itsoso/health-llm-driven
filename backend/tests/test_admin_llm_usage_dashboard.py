"""Admin LLM usage dashboard: global and per-user token/cost metering."""
from datetime import datetime, timezone
import math
import uuid

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
    success: int = 1,
    latency_ms: int = 1200,
    error_type: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
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
            cost_usd=0.01,
            latency_ms=latency_ms,
            success=success,
            error_type=error_type,
            error_code=error_code,
            error_message=error_message,
            created_at=datetime.now(timezone.utc),
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
