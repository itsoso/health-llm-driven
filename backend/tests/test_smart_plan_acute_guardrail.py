"""Smart weekly plan acute illness guardrail tests."""

from app.services.smart_plan_service import apply_acute_training_guardrail


def test_apply_acute_training_guardrail_replaces_exercise_items_with_rest():
    plan = {
        "days": {
            "1": [
                {
                    "category": "exercise",
                    "title": "跑步30分钟",
                    "description": "【依据】本周运动不足",
                    "target_value": 30,
                    "target_unit": "分钟",
                },
                {"category": "diet", "title": "午餐高蛋白", "description": "【依据】蛋白不足"},
            ],
            "2": [
                {
                    "category": "exercise",
                    "title": "力量训练",
                    "description": "【依据】保持肌肉",
                    "target_value": 20,
                    "target_unit": "分钟",
                },
            ],
        },
    }

    updated = apply_acute_training_guardrail(plan, "感冒/上呼吸道症状期不要求完成运动目标。")

    assert updated["days"]["1"][0]["category"] == "rest"
    assert updated["days"]["1"][0]["title"] == "暂停训练，优先恢复"
    assert updated["days"]["1"][0]["target_value"] is None
    assert updated["days"]["1"][0]["target_unit"] is None
    assert "感冒/上呼吸道症状期" in updated["days"]["1"][0]["description"]
    assert updated["days"]["1"][1]["category"] == "diet"
    assert updated["days"]["2"][0]["category"] == "rest"
