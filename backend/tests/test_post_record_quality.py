# -*- coding: utf-8 -*-
"""记录后的回答质量层：结构化上下文、当天汇总、多记录聚合。"""
import logging
from datetime import date
from urllib.parse import unquote

from app.models.daily_health import DietRecord
from app.models.user_profile import UserProfile
from app.services.post_record_quality import (
    build_post_record_quality_response,
    combine_post_record_quality_responses,
    extract_personal_context_pack,
    fetch_today_diet_totals,
)


def test_personal_context_pack_merges_profile_and_prompt(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    db.add(
        UserProfile(
            user_id=user.id,
            current_weight_kg=72,
            target_water_ml=2200,
            chronic_conditions=["胃溃疡", "高血压"],
            allergies=["海鲜"],
            current_medications=[{"name": "奥美拉唑"}],
            primary_goal="weight_loss",
        )
    )
    db.commit()

    pack = extract_personal_context_pack(
        "[用户健康档案]\n慢性病: 糖尿病\n过敏/禁忌: 花生\n健康目标: 每日饮水2000ml",
        db=db,
        user_id=user.id,
    )

    assert {"胃溃疡", "高血压", "糖尿病"}.issubset(set(pack.conditions))
    assert {"海鲜", "花生"}.issubset(set(pack.allergies))
    assert "奥美拉唑" in pack.medications
    assert pack.primary_goal == "weight_loss"
    assert pack.target_water_ml == 2200
    assert pack.protein_target_g == 115


def test_personal_context_pack_logs_profile_lookup_failure(caplog):
    class BrokenDB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("db unavailable")

    with caplog.at_level(logging.WARNING):
        pack = extract_personal_context_pack(db=BrokenDB(), user_id=42)

    assert pack.protein_target_g == 80
    assert any("profile lookup failed" in rec.getMessage() for rec in caplog.records)


def test_today_diet_totals_logs_lookup_failure(caplog):
    class BrokenDB:
        def query(self, *_args, **_kwargs):
            raise RuntimeError("db unavailable")

    with caplog.at_level(logging.WARNING):
        totals = fetch_today_diet_totals(
            db=BrokenDB(),
            user_id=42,
            context=extract_personal_context_pack(),
        )

    assert totals is None
    assert any("diet totals lookup failed" in rec.getMessage() for rec in caplog.records)


def test_diet_quality_response_uses_today_totals_and_actionable_routes(db, auth_user_and_headers):
    user, _headers = auth_user_and_headers
    today = date.today()
    db.add(UserProfile(user_id=user.id, current_weight_kg=70, chronic_conditions=["胃溃疡"]))
    db.add_all([
        DietRecord(
            user_id=user.id,
            record_date=today,
            meal_type="breakfast",
            food_items="鸡蛋, 小米粥",
            calories=270,
            protein=7,
            carbs=38,
            fat=8,
        ),
        DietRecord(
            user_id=user.id,
            record_date=today,
            meal_type="lunch",
            food_items="煎牛肉能量碗, 水煮蛋, 姜黄鲜柠维C茶",
            calories=770,
            protein=30,
            carbs=70,
            fat=17,
        ),
    ])
    db.commit()

    response = build_post_record_quality_response(
        "diet",
        {
            "meal_type": "lunch",
            "food_items": "煎牛肉能量碗, 水煮蛋, 姜黄鲜柠维C茶",
            "calories": 770,
            "protein": 30,
            "carbs": 70,
            "fat": 17,
            "record_date": today.isoformat(),
        },
        result='{"id": 2}',
        personal_context="[用户健康档案]\n慢性病: 胃溃疡\n",
        db=db,
        user_id=user.id,
    )

    assert response is not None
    assert "已记录午餐" in response["reply"]
    assert "今日蛋白" in response["reply"]
    assert "{" not in response["reply"]

    card = response["cards"][0]
    assert card["type"] == "record_quality"
    assert card["data"]["progress"]["protein_total_g"] == 37
    assert card["data"]["progress"]["protein_target_g"] == 112
    assert card["data"]["progress"]["remaining_protein_g"] == 75
    assert card["actions"][0]["payload"]["route"] == "/diet-plan"
    assert card["actions"][1]["payload"]["route"] == "/(tabs)/record"
    assert card["actions"][2]["action"] == "route.open"
    assert "阿衡" in card["actions"][2]["label"]
    diet_follow_up_route = unquote(card["actions"][2]["payload"]["route"])
    assert diet_follow_up_route.startswith("/(tabs)/chat?")
    assert "煎牛肉能量碗" in diet_follow_up_route
    assert "下一餐" in diet_follow_up_route


def test_multi_record_quality_responses_are_aggregated_not_last_one_wins():
    diet = build_post_record_quality_response(
        "diet",
        {"meal_type": "lunch", "food_items": "牛肉饭", "protein": 28, "calories": 650},
        personal_context="",
    )
    exercise = build_post_record_quality_response(
        "exercise",
        {"exercise_type": "俯卧撑", "sets": 3, "reps": 20, "duration": 8},
        personal_context="",
    )

    combined = combine_post_record_quality_responses([diet, exercise])

    assert combined is not None
    assert "已记录 2 项" in combined["reply"]
    assert "午餐" in combined["reply"]
    assert "俯卧撑" in combined["reply"]
    assert len(combined["cards"]) == 2
    assert all(card["type"] == "record_quality" for card in combined["cards"])
    exercise_actions = combined["cards"][1]["actions"]
    exercise_follow_up_route = unquote(exercise_actions[2]["payload"]["route"])
    assert exercise_follow_up_route.startswith("/(tabs)/chat?")
    assert "俯卧撑" in exercise_follow_up_route
    assert "恢复" in exercise_follow_up_route
