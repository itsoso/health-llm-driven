from app.services.release_readiness import release_readiness_snapshot


def test_release_readiness_blocks_unknown_production_budget_and_manual_gates(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "llm_provider", "tokenplan")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 0)
    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", False)
    monkeypatch.setattr(settings, "sentry_dsn", None)

    report = release_readiness_snapshot()

    assert report["status"] == "blocked"
    assert report["checks"]["tokenplan_budget"]["status"] == "fail"
    assert report["checks"]["sentry"]["status"] == "fail"
    assert "physical_iphone_gate" in report["blocking_checks"]
    assert report["ready_for_app_store"] is False


def test_release_readiness_backend_can_be_ready_before_manual_app_store_gates(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "llm_provider", "tokenplan")
    monkeypatch.setattr(settings, "tokenplan_monthly_token_quota", 100000)
    monkeypatch.setattr(settings, "llm_auto_recovery_enabled", False)
    monkeypatch.setattr(settings, "sentry_dsn", "https://example@sentry.invalid/1")

    report = release_readiness_snapshot()

    assert report["ready_for_backend_release"] is True
    assert report["ready_for_app_store"] is False
    assert report["checks"]["account_deletion_drill"]["status"] == "manual"
