# -*- coding: utf-8 -*-
"""7 日可穿戴摘要注入测试.

Task 4 要求:只给 LLM 传 sleep/HRV/RHR/activity 的聚合摘要和边界,
不能把原始逐日/分钟级可穿戴数据塞进 prompt。
"""
from datetime import date, timedelta

from app.models.daily_health import GarminData
from app.models.user import User
from app.services.health_context_lite_service import build_lite_health_context
from app.services.post_record_quality import build_post_record_quality_response


def _make_user(db, suffix: str) -> User:
    user = User(
        username=f"wearable_ctx_{suffix}",
        email=f"wearable_ctx_{suffix}@example.com",
        hashed_password="x",
        name=f"可穿戴测试{suffix}",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_wearable_week(db, user_id: int, *, poor_recovery: bool) -> None:
    today = date.today()
    for i in range(7):
        if poor_recovery:
            row = GarminData(
                user_id=user_id,
                record_date=today - timedelta(days=i),
                sleep_score=50 + (i % 3),
                total_sleep_duration=295 + i * 4,
                hrv=33.0 + (i % 2),
                resting_heart_rate=72 + (i % 3),
                steps=2800 + i * 80,
                active_minutes=8,
                body_battery_current=24,
                stress_level=72,
                data_source="garmin",
            )
        else:
            row = GarminData(
                user_id=user_id,
                record_date=today - timedelta(days=i),
                sleep_score=84 + (i % 4),
                total_sleep_duration=455 + i * 5,
                hrv=62.0 + (i % 4),
                resting_heart_rate=53 + (i % 2),
                steps=8800 + i * 160,
                active_minutes=42,
                body_battery_current=78,
                stress_level=26,
                data_source="garmin",
            )
        db.add(row)
    db.commit()


def _next_meal_payload(response: dict) -> dict:
    card = response["cards"][0]
    action = card["actions"][0]
    return action["payload"]["patch"]["next_meal_detail"]


def test_wearable_summary_data_gap_has_privacy_boundary(db):
    from app.services.health_context_summary import (
        build_wearable_context_summary,
        format_wearable_context_summary_for_prompt,
    )

    user = _make_user(db, "empty")

    summary = build_wearable_context_summary(db, user.id, days=7)

    assert summary["status"] == "data_gap"
    assert summary["data_gap"] is True
    assert "raw_daily" not in summary
    assert "records" not in summary
    assert "privacy_boundary" in summary
    assert "7日聚合摘要" in summary["privacy_boundary"]

    prompt = format_wearable_context_summary_for_prompt(summary)
    assert "data_gap" in prompt
    assert "隐私边界" in prompt
    assert "原始逐日记录" in prompt


def test_same_meal_gets_different_guidance_when_sleep_recovery_differs(db):
    from app.services.health_context_summary import build_wearable_context_summary

    good_user = _make_user(db, "good")
    poor_user = _make_user(db, "poor")
    _seed_wearable_week(db, good_user.id, poor_recovery=False)
    _seed_wearable_week(db, poor_user.id, poor_recovery=True)

    good_summary = build_wearable_context_summary(db, good_user.id, days=7)
    poor_summary = build_wearable_context_summary(db, poor_user.id, days=7)

    assert good_summary["meal_guidance_context"]["recovery_state"] == "recovered"
    assert poor_summary["meal_guidance_context"]["recovery_state"] == "strained"
    assert good_summary["meal_guidance_context"]["meal_advice_bias"] != poor_summary["meal_guidance_context"]["meal_advice_bias"]

    record_data = {
        "meal_type": "lunch",
        "food_items": "鸡胸肉饭, 西兰花",
        "calories": 650,
        "protein": 35,
        "carbs": 72,
        "fat": 18,
        "record_date": date.today().isoformat(),
    }
    good_response = build_post_record_quality_response("diet", record_data, result='{"id": 1}', db=db, user_id=good_user.id)
    poor_response = build_post_record_quality_response("diet", record_data, result='{"id": 2}', db=db, user_id=poor_user.id)

    assert good_response is not None
    assert poor_response is not None
    good_next = _next_meal_payload(good_response)
    poor_next = _next_meal_payload(poor_response)

    assert good_next["summary"] != poor_next["summary"]
    assert "恢复" in poor_next["summary"] or "睡眠" in " ".join(poor_next["rationale"])
    assert "恢复状态" in " ".join(poor_next["rationale"])


def test_lite_health_context_includes_compact_wearable_summary(db):
    user = _make_user(db, "lite")
    _seed_wearable_week(db, user.id, poor_recovery=True)

    ctx = build_lite_health_context(db, user.id)

    assert ctx is not None
    assert "[可穿戴7日摘要]" in ctx
    assert "恢复态: strained" in ctx
    assert "隐私边界" in ctx
    assert "原始逐日记录" in ctx
