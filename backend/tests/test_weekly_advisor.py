"""test_weekly_advisor —— 周建议产出 + 兜底 + 幂等 (P2-1)."""

from unittest.mock import patch, AsyncMock

import pytest

from app.models.action_card import ActionCard
from app.models.user import User
from app.orchestrator.schema import SpecialistFinding
from app.services import weekly_advisor


def _make_user(db, username="advisor_user"):
    u = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password="x",
        name=username,
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _llm_response(text: str):
    return {"content": text}


VALID_LLM_OUTPUT = """[
  {
    "title": "周三减量训练",
    "content": "本周三 RHR > 70, 把强度从 zone3 降到 zone1, 时长 30 分钟",
    "metric_key": "rhr",
    "baseline_value": "70",
    "target_value": "62",
    "verification_days": 7
  },
  {
    "title": "维 D 减量",
    "content": "上次化验 vit D > 80, 减到 2000 IU/天",
    "metric_key": "vitamin_d",
    "baseline_value": "82",
    "target_value": "60",
    "verification_days": 30
  },
  {
    "title": "22:30 前关蓝光",
    "content": "近 7 天深睡 < 60 分钟, 需要降低就寝前蓝光暴露",
    "metric_key": "sleep_score",
    "baseline_value": "68",
    "target_value": "78",
    "verification_days": 7
  }
]"""


def _patch_llm(text: str):
    """Patch app.services.llm.get_llm_provider 返回 FakeLLM 实例 (chat 返回固定文本)."""
    fake_provider = type(
        "FakeLLM",
        (),
        {"chat": AsyncMock(return_value=_llm_response(text))},
    )()
    return patch(
        "app.services.llm.get_llm_provider",
        return_value=fake_provider,
    )


@pytest.mark.asyncio
async def test_persists_3_to_5_suggestions_when_llm_ok(db):
    user = _make_user(db)

    with _patch_llm(VALID_LLM_OUTPUT), \
         patch("app.services.weekly_advisor.evaluate_safety", return_value=type("R", (), {"alerts": []})()), \
         patch("app.services.weekly_advisor.build_twin", return_value=type("T", (), {"meta": type("M", (), {"user_id": user.id, "data_sources": []})()})()), \
         patch("app.services.weekly_advisor.twin_to_prompt_blob", return_value="<blob>"), \
         patch("app.services.weekly_advisor._select_specialists", return_value=[]), \
         patch("app.services.weekly_advisor._run_specialists", return_value=[]):
        result = await weekly_advisor.generate_weekly_advice(db, user.id)

    assert result["created"] == 3
    assert result.get("fallback") is False
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user.id,
        ActionCard.source_type == "weekly_advisor",
    ).all()
    assert len(cards) == 3
    titles = {c.title for c in cards}
    assert "周三减量训练" in titles
    assert all(c.card_type == "recommendation" for c in cards)
    assert all(c.severity == "low" for c in cards)


@pytest.mark.asyncio
async def test_idempotent_within_same_week(db):
    """同一周已有 weekly_advisor 卡 → 跳过, 不重复写."""
    user = _make_user(db)

    with _patch_llm(VALID_LLM_OUTPUT), \
         patch("app.services.weekly_advisor.evaluate_safety", return_value=type("R", (), {"alerts": []})()), \
         patch("app.services.weekly_advisor.build_twin", return_value=type("T", (), {"meta": type("M", (), {"user_id": user.id, "data_sources": []})()})()), \
         patch("app.services.weekly_advisor.twin_to_prompt_blob", return_value="<blob>"), \
         patch("app.services.weekly_advisor._select_specialists", return_value=[]), \
         patch("app.services.weekly_advisor._run_specialists", return_value=[]):
        r1 = await weekly_advisor.generate_weekly_advice(db, user.id)
        r2 = await weekly_advisor.generate_weekly_advice(db, user.id)

    assert r1["created"] == 3
    assert r2["created"] == 0
    assert r2.get("skipped") == "already_has_weekly_card"


@pytest.mark.asyncio
async def test_fallback_to_findings_when_llm_empty(db):
    """LLM 输出空/失败 → 拉 Specialist findings top 3 兜底."""
    user = _make_user(db)

    fake_findings = [
        type("F", (), {"specialist_name": "recovery_coach", "summary": "本周睡眠评分偏低", "details": "深睡 < 60 分钟"})(),
        type("F", (), {"specialist_name": "fuel_strategist", "summary": "蛋白摄入低 70g/d", "details": "目标 1.6g/kg"})(),
        type("F", (), {"specialist_name": "movement_coach", "summary": "ACWR 1.5 偏高", "details": "建议本周减量"})(),
    ]

    with _patch_llm("[]"), \
         patch("app.services.weekly_advisor.evaluate_safety", return_value=type("R", (), {"alerts": []})()), \
         patch("app.services.weekly_advisor.build_twin", return_value=type("T", (), {"meta": type("M", (), {"user_id": user.id, "data_sources": []})()})()), \
         patch("app.services.weekly_advisor.twin_to_prompt_blob", return_value="<blob>"), \
         patch("app.services.weekly_advisor._select_specialists", return_value=[]), \
         patch("app.services.weekly_advisor._run_specialists", return_value=fake_findings):
        result = await weekly_advisor.generate_weekly_advice(db, user.id)

    assert result["created"] == 3
    assert result["fallback"] is True
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user.id,
        ActionCard.source_type == "weekly_advisor",
    ).all()
    titles = {c.title for c in cards}
    assert any("睡眠" in t for t in titles)


@pytest.mark.asyncio
async def test_fallback_filters_unsupported_same_domain_findings(db):
    """weekly_advisor 也必须复用 Planner evidence policy, 避免绕开 Orchestrator。"""
    user = _make_user(db, "advisor_evidence_policy")

    fake_findings = [
        SpecialistFinding(
            specialist_name="movement_coach",
            category="movement",
            summary="本周安排 30 分钟慢跑",
            findings=[{"title": "慢跑 30 分钟", "action": "Z1 慢跑"}],
        ),
        SpecialistFinding(
            specialist_name="recovery_coach",
            category="recovery",
            summary="恢复不足，本周先降强度",
            findings=[{"title": "本周降强度", "action": "改成散步和拉伸"}],
            evidence_refs=["claim:c_recovery_low_reduce_intensity"],
        ),
    ]

    with _patch_llm("[]"), \
         patch("app.services.weekly_advisor.evaluate_safety", return_value=type("R", (), {"alerts": []})()), \
         patch("app.services.weekly_advisor.build_twin", return_value=type("T", (), {"meta": type("M", (), {"user_id": user.id, "data_sources": []})()})()), \
         patch("app.services.weekly_advisor.twin_to_prompt_blob", return_value="<blob>"), \
         patch("app.services.weekly_advisor._select_specialists", return_value=[]), \
         patch("app.services.weekly_advisor._run_specialists", return_value=fake_findings):
        result = await weekly_advisor.generate_weekly_advice(db, user.id)

    assert result["created"] == 1
    assert result["evidence_policy"]["blocked_count"] == 1
    cards = db.query(ActionCard).filter(
        ActionCard.user_id == user.id,
        ActionCard.source_type == "weekly_advisor",
    ).all()
    assert len(cards) == 1
    assert "恢复" in cards[0].title or "降强度" in cards[0].title
    assert "慢跑" not in cards[0].title


def test_parse_llm_suggestions_handles_markdown_wrapping(db):
    text = "```json\n" + VALID_LLM_OUTPUT + "\n```"
    parsed = weekly_advisor._parse_llm_suggestions(text)
    assert len(parsed) == 3
    assert parsed[0]["title"] == "周三减量训练"


def test_validate_suggestion_rejects_missing_required(db):
    assert weekly_advisor._validate_suggestion({}) is None
    assert weekly_advisor._validate_suggestion({"title": "x"}) is None
    assert weekly_advisor._validate_suggestion({"content": "y"}) is None
    v = weekly_advisor._validate_suggestion({"title": "ok", "content": "fine"})
    assert v is not None
    assert v["verification_days"] == weekly_advisor.DEFAULT_VERIFICATION_DAYS


def test_validate_suggestion_coerces_numerics_to_str(db):
    v = weekly_advisor._validate_suggestion({
        "title": "x", "content": "y",
        "baseline_value": 70, "target_value": 62.5,
    })
    assert v["baseline_value"] == "70"
    assert v["target_value"] == "62.5"
