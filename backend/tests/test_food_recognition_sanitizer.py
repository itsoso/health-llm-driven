from app.services.ai.food_recognition import sanitize_food_recognition_result


def test_sanitize_food_recognition_rejects_ui_card_copy():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {
                "name": "和午餐食品营养卡",
                "quantity": "",
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
            }
        ],
        "meal_description": "和午餐食品营养卡",
        "total_calories": 0,
        "total_protein": 0,
        "total_carbs": 0,
        "total_fat": 0,
    })

    assert result["success"] is False
    assert result["foods"] == []
    assert "未识别到可记录的食物" in result["error"]


def test_sanitize_food_recognition_keeps_real_food_and_recomputes_totals():
    result = sanitize_food_recognition_result({
        "success": True,
        "foods": [
            {"name": "今日饮食", "calories": 0, "protein": 0, "carbs": 0, "fat": 0},
            {
                "name": "鸡胸肉",
                "quantity": "200g",
                "calories": 330,
                "protein": 62,
                "carbs": 0,
                "fat": 7,
            },
        ],
        "total_calories": 999,
        "total_protein": 99,
        "total_carbs": 88,
        "total_fat": 77,
    })

    assert result["success"] is True
    assert [food["name"] for food in result["foods"]] == ["鸡胸肉"]
    assert result["total_calories"] == 330
    assert result["total_protein"] == 62
    assert result["total_carbs"] == 0
    assert result["total_fat"] == 7
