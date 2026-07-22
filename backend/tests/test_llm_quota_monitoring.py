from contextlib import nullcontext
from datetime import datetime, timezone

from app.models.llm_usage import LlmUsageLog
from app.models.user import User


def test_daily_llm_check_reports_local_quota_rejections(db, monkeypatch):
    from app.config import settings
    from app.tasks import maintenance

    user = User(
        username="quota_monitor_user",
        email="quota-monitor@example.com",
        hashed_password="x",
        name="Quota User",
        is_active=True,
        is_approved=True,
        is_admin=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add_all(
        [
            LlmUsageLog(
                user_id=user.id,
                provider="tokenplan",
                model="qwen3.7-plus",
                caller="agent.stream",
                prompt_tokens=900,
                completion_tokens=0,
                total_tokens=900,
                cost_usd=0,
                success=1,
                created_at=datetime.now(timezone.utc),
            ),
            LlmUsageLog(
                user_id=user.id,
                provider="tokenplan",
                model="qwen3.7-plus",
                caller="agent.stream",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost_usd=0,
                success=0,
                error_class="local_budget_policy",
                error_type="user_monthly_token_limit",
                error_code="llm_budget_exceeded",
                error_message="local quota policy rejected request",
                created_at=datetime.now(timezone.utc),
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(settings, "tokenplan_user_monthly_token_quota", 1_000)
    monkeypatch.setattr(maintenance, "SessionLocal", lambda: nullcontext(db))

    result = maintenance.llm_cost_daily_check.run()

    assert result["quota_rejections_24h"] == 1
    assert result["quota_rejection_reasons"]["user_monthly_token_limit"] == 1
    assert result["near_limit_users"][0]["user_id"] == user.id
    assert result["near_limit_users"][0]["monthly_token_utilization"] == 0.9
