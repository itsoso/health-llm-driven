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
    # 回复压到 ≤2 句:头条确认(带头条数字) + 一句人话备注。完整宏量/进度只在卡上。
    reply = response["reply"]
    assert reply.startswith("已记录午餐：")
    assert "770 kcal" in reply and "蛋白 30g" in reply
    assert "今日累计 1040 kcal / 2 餐" in reply
    # 墙里的宏量标签行 / 逐条宏量 / 进度句不再复述进文本(卡承载)。
    assert "碳水" not in reply and "脂肪" not in reply and "纤维" not in reply
    assert "今日蛋白" not in reply
    assert "下一步" not in reply and "个人提醒" not in reply
    assert reply.count("。") <= 2  # 至多两句
    assert "✅" not in reply and "{" not in reply

    card = response["cards"][0]
    assert card["type"] == "record_quality"
    assert card["data"]["progress"]["protein_total_g"] == 37
    assert card["data"]["progress"]["protein_target_g"] == 112
    assert card["data"]["progress"]["remaining_protein_g"] == 75
    assert [action["label"] for action in card["actions"]] == ["看下一餐建议", "调整记录"]
    assert card["actions"][0]["action"] == "ui.inline.expand"
    assert card["actions"][0]["payload"]["target"] == "next_meal"
    assert "route" not in card["actions"][0]["payload"]
    assert card["actions"][0]["payload"]["patch"]["expanded_sections"] == ["next_meal"]
    assert card["actions"][0]["payload"]["patch"]["next_meal_detail"]["title"] == "下一餐建议"
    assert "煎牛肉能量碗" in card["actions"][0]["payload"]["patch"]["next_meal_detail"]["context"]

    # "调整记录" 从"跳记录 tab"改成聊天内展开调整器: result 带 id 时走 inline-expand,
    # 种子取 record_data 原始值(键名与 mobile 编辑器契约精确对齐)。
    adjust = card["actions"][1]
    assert adjust["id"] == "adjust-record"
    assert adjust["action"] == "ui.inline.expand"
    assert adjust["payload"]["target"] == "adjust_record"
    assert "route" not in adjust["payload"]
    assert adjust["payload"]["patch"]["expanded_sections"] == ["adjust_record"]
    assert adjust["payload"]["patch"]["adjust_record"] == {
        "record_id": 2,
        "meal_type": "lunch",
        "food_items": "煎牛肉能量碗, 水煮蛋, 姜黄鲜柠维C茶",
        "calories": 770.0,
        "protein": 30.0,
        "carbs": 70.0,
        "fat": 17.0,
    }
    assert all("问小巴" not in action["label"] for action in card["actions"])


def test_uncertain_write_never_builds_success_reply_or_card():
    response = build_post_record_quality_response(
        "diet",
        {
            "meal_type": "dinner",
            "food_items": "烤鱼",
            "calories": 605,
        },
        result='{"status":"uncertain","dispatch_started":true}',
        write_verified=False,
    )

    assert response is None


def test_diet_quality_response_ignores_numeric_contraindication_noise():
    response = build_post_record_quality_response(
        "diet",
        {
            "meal_type": "lunch",
            "food_items": "5分熟牛排, 杂粮饭, 西兰花",
            "calories": 720,
            "protein": 42,
            "carbs": 55,
            "fat": 20,
        },
        result='{"id": 12}',
        personal_context="[用户健康档案]\n过敏/禁忌: 5, 海鲜\n",
    )

    assert response is not None
    text = response["reply"] + " ".join(response["cards"][0]["data"]["personal_cautions"])
    assert "「5」" not in text
    assert "禁忌里包含" not in text


def test_diet_adjust_action_falls_back_to_diet_page_without_record_id():
    # 拿不到 record_id(result 非 JSON / 无 id) → 兜底跳真正饮食页, 不再去 /(tabs)/record。
    response = build_post_record_quality_response(
        "diet",
        {"meal_type": "dinner", "food_items": "牛肉饭", "protein": 28, "calories": 650},
        result="",
        personal_context="",
    )

    assert response is not None
    adjust = response["cards"][0]["actions"][1]
    assert adjust["id"] == "open-diet"
    assert adjust["label"] == "去饮食页调整"
    assert adjust["action"] == "route.open"
    assert adjust["payload"]["route"] == "/diet"
    assert "adjust_record" not in adjust["payload"]


def test_diet_adjust_seed_preserves_none_macros_and_normalizes_zh_meal():
    # 缺失宏量保留 None(不填 0), 中文 meal_type 归一到 english。
    response = build_post_record_quality_response(
        "diet",
        {"meal_type": "早餐", "food_items": "白粥", "calories": 200},
        result='{"id": 77}',
        personal_context="",
    )

    seed = response["cards"][0]["actions"][1]["payload"]["patch"]["adjust_record"]
    assert seed["record_id"] == 77
    assert seed["meal_type"] == "breakfast"
    assert seed["food_items"] == "白粥"
    assert seed["calories"] == 200.0
    assert seed["protein"] is None
    assert seed["carbs"] is None
    assert seed["fat"] is None


def test_exercise_actions_unchanged_by_diet_adjust_work():
    # 本次只改 diet;exercise 卡 actions 保持不变(查看运动记录/继续记录/问小巴恢复)。
    response = build_post_record_quality_response(
        "exercise",
        {"exercise_type": "俯卧撑", "sets": 3, "reps": 20, "duration": 8},
        result='{"id": 9}',
        personal_context="",
    )

    actions = response["cards"][0]["actions"]
    assert [a["id"] for a in actions] == ["open-workouts", "open-record", "ask-recovery"]
    assert actions[0]["payload"]["route"] == "/workout-list"
    assert actions[1]["payload"]["route"] == "/(tabs)/record"
    assert all(a["id"] != "adjust-record" for a in actions)


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
