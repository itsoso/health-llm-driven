"""Synthetic background-generation status and idempotent delivery contracts."""

from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.agent_conversation import AgentMessage
from app.services.llm.usage_tracker import LLMBudgetExceeded


@pytest.mark.parametrize("error, status, reason", [
    (LLMBudgetExceeded(reason="user_monthly_token_limit", retry_at="2026-10-01T00:00:00+00:00"), "blocked", "budget_exhausted"),
    (LLMBudgetExceeded(reason="budget_guard_unavailable"), "blocked", "budget_guard_unavailable"),
    (HTTPException(503, detail={"code": "ai_consent_unavailable", "message": "PRIVATE_SENTINEL"}), "blocked", "consent_unavailable"),
    (RuntimeError("PRIVATE_SENTINEL provider 503"), "failed", "provider_error"),
])
def test_briefing_exposes_generation_state_without_error_payload(error, status, reason):
    from app.tasks.notification_helpers.briefing import ai_generation_failure

    metadata, message = ai_generation_failure(error)
    assert metadata["status"] == status
    assert metadata["reason"] == reason
    assert "PRIVATE_SENTINEL" not in str(metadata) + message
    assert "数据汇总" in message
    assert metadata.get("retry_at") == getattr(error, "retry_at", None)


def test_retry_updates_same_briefing_and_generation_status(db, auth_user_and_headers):
    from app.tasks.notifications import _write_briefing_message

    user, _headers = auth_user_and_headers
    day = date(2026, 9, 11)
    conv_id, first_id = _write_briefing_message(
        db, user.id, "确定性数据汇总。AI解读暂不可用。", day,
        ai_generation={"status": "blocked", "reason": "consent_unavailable"},
    )
    second_conv, second_id = _write_briefing_message(
        db, user.id, "确定性数据汇总。已获得AI解读。", day,
        ai_generation={"status": "complete"},
    )
    assert (second_conv, second_id) == (conv_id, first_id)
    rows = db.query(AgentMessage).filter(AgentMessage.conversation_id == conv_id).all()
    assert len(rows) == 1
    assert rows[0].meta["ai_generation"] == {"status": "complete"}


@pytest.mark.parametrize("error, expected", [
    (HTTPException(503, detail={"code": "ai_consent_unavailable"}), "blocked"),
    (None, "complete"),
])
def test_real_briefing_without_hrv_history_keeps_data_and_reports_ai_status(
    db, auth_user_and_headers, monkeypatch, error, expected,
):
    from app.models.daily_health import GarminData
    from app.tasks import notifications

    user, _headers = auth_user_and_headers
    day = date(2026, 9, 11)
    db.add(GarminData(user_id=user.id, record_date=day, sleep_score=80, steps=1000))
    db.commit()
    calls = []

    class Provider:
        async def chat(self, messages):
            assert isinstance(messages, list), "Provider chat requires message objects."
            calls.append(messages)
            if error is not None:
                raise error
            return "这是一条用于测试的合成解读，没有新增任何医学执行指令。"

    monkeypatch.setattr(notifications, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", lambda: Provider())
    monkeypatch.setattr("app.services.health_score_service.health_score_service.calculate_daily_score", lambda *_a, **_k: {"status": "ok", "total_score": 70})
    monkeypatch.setattr("app.services.clinical_journal_service.write_briefing_soap_entry", lambda *_a, **_k: None)
    # This test exercises the generation failure after an independently tested
    # admission seam; production has no reviewed daily-briefing claim contract.
    monkeypatch.setattr("app.services.health_advice_verifier.verify_advice", lambda *_a, **_k: SimpleNamespace(allowed=True))
    notifications._generate_daily_briefing_for_user(user.id, day)

    assert len(calls) == 1
    message = db.query(AgentMessage).filter(AgentMessage.role == "assistant").one()
    assert "| 睡眠 |" in message.content
    assert message.meta["ai_generation"]["status"] == expected
    if error is not None:
        assert "数据汇总" in message.content
        assert message.meta["ai_generation"]["reason"] == "consent_unavailable"


def test_unreviewed_daily_narrative_is_blocked_before_model_and_soap(db, auth_user_and_headers, monkeypatch):
    from app.models.daily_health import GarminData
    from app.models.genetic_data import GeneticProfile, GeneticVariant
    from app.tasks import notifications

    user, _headers = auth_user_and_headers
    day = date(2026, 9, 11)
    db.add(GarminData(user_id=user.id, record_date=day, sleep_score=80, steps=1000))
    profile = GeneticProfile(user_id=user.id, test_provider="synthetic", test_date=day)
    db.add(profile)
    db.flush()
    db.add(GeneticVariant(user_id=user.id, profile_id=profile.id, category="nutrition", gene_name="TEST_GENE", risk_level="high", description="SYNTHETIC_UNREVIEWED_PLAN 必须服用四粒补剂"))
    db.commit()
    monkeypatch.setattr(notifications, "SessionLocal", lambda: nullcontext(db))
    monkeypatch.setattr("app.services.health_score_service.health_score_service.calculate_daily_score", lambda *_a, **_k: {"status": "ok", "total_score": 70})
    def no_provider():
        pytest.fail("No approved claim contract: do not pay for or emit medical narrative.")
    monkeypatch.setattr("app.services.llm.factory.get_llm_provider", no_provider)
    journal = []
    monkeypatch.setattr("app.services.clinical_journal_service.write_briefing_soap_entry", lambda *_a, **kw: journal.append(kw))
    notifications._generate_daily_briefing_for_user(user.id, day)
    row = db.query(AgentMessage).filter(AgentMessage.role == "assistant").one()
    assert row.meta["ai_generation"] == {"status": "blocked", "reason": "high_risk_missing_evidence"}
    assert "数据汇总" in row.content
    assert "SYNTHETIC_UNREVIEWED_PLAN" not in row.content
    assert "SYNTHETIC_UNREVIEWED_PLAN" not in journal[0]["briefing_md"]
    assert journal[0]["ai_narrative"] is None
