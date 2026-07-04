import pytest

from app.services.intake_intent_classifier import classify_intake_intent


@pytest.mark.parametrize(("query", "kind"), [
    ("记录午餐吃了牛肉面", "diet"),
    ("午餐吃了煎牛肉能量碗 770kcal", "diet"),
    ("记录刚吃了替普瑞酮", "medication"),
    ("刚服用了替普瑞酮胶囊（施维舒）", "medication"),
    ("记录刚吃了奥美拉唑20mg", "medication"),
    ("吃了鱼油", "supplement"),
    ("吃了维生素D3", "supplement"),
    ("喝了300ml水", "water"),
    ("删除这一餐", "diet_management"),
    ("我刚才不小心删除了", "diet_management"),
    ("刚吃了一个东西", "unknown"),
])
def test_classifies_common_intake_phrases(query, kind):
    result = classify_intake_intent(query)

    assert result.kind == kind


def test_extracts_basic_intake_slots():
    water = classify_intake_intent("记录我刚喝了 300ml 水")
    assert water.kind == "water"
    assert water.slots["amount_ml"] == 300

    medication = classify_intake_intent("记录刚吃了奥美拉唑20mg")
    assert medication.kind == "medication"
    assert medication.text == "奥美拉唑20mg"
    assert medication.slots["dose"] == "20mg"

    diet = classify_intake_intent("记录晚餐吃了牛肉面 680kcal")
    assert diet.kind == "diet"
    assert diet.text == "牛肉面"
    assert diet.slots["meal_type"] == "dinner"
