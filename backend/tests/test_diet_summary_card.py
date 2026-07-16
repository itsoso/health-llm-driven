"""汇总类卡结构化 v1 · diet_daily_summary composer 契约 + R4 测试。

契约字段必须与 mobile DietSummaryCard 的 parse*(meal_type/name/detail/calories/protein/
carbs/fat · totals · water.current_ml/target_ml · observations.severity/label/detail)一字对齐 ——
跨界漂移 = 静默空卡。observations 必须确定性 + factual(不命令,守 R4)。
"""
from app.services.genui.diet_summary import (
    build_diet_daily_summary,
    render_diet_summary_block,
    DIET_SUMMARY_TYPE,
)
from app.services.atomic_capability_registry import (
    get_atomic_capability,
    validate_dynamic_view,
)


def _summary():
    return {
        "record_date": "2026-07-16",
        "total_calories": 1710,
        "total_protein": 92.0,
        "total_carbs": 141.0,
        "total_fat": 75.0,
        "total_fiber": 4.0,
        "meals_count": 3,
        "meals": [
            {"meal_type": "dinner", "food_items": "牛肋排·汉堡面包·生菜",
             "calories": 730, "protein": 37, "carbs": 75, "fat": 26, "fiber": 2},
            {"meal_type": "breakfast", "food_items": "山药小米粥·蒸蛋羹×2·焯青菜",
             "calories": 400, "protein": 23, "carbs": 38, "fat": 13, "fiber": 1},
            {"meal_type": "lunch", "food_items": "三文鱼香草芝士鸡肉餐",
             "calories": 580, "protein": 32, "carbs": 28, "fat": 36, "fiber": 1},
        ],
    }


def test_descriptor_shape_matches_mobile_contract():
    d = build_diet_daily_summary(_summary(), water={"current_ml": 500, "target_ml": 2000},
                                 weight_kg=71.2)
    assert d is not None
    assert d["type"] == DIET_SUMMARY_TYPE == "diet_daily_summary"
    data = d["data"]
    assert data["record_date"] == "2026-07-16"
    # meals 排序 breakfast→lunch→dinner,字段逐一对齐 mobile parseMeals
    assert [m["meal_type"] for m in data["meals"]] == ["breakfast", "lunch", "dinner"]
    m0 = data["meals"][0]
    assert set(m0) == {"meal_type", "name", "detail", "calories", "protein", "carbs", "fat"}
    assert m0["name"] == "早餐"
    assert m0["detail"] == "山药小米粥·蒸蛋羹×2·焯青菜"
    assert m0["calories"] == 400  # 整数
    # totals 五值(mobile 表用前四列,fiber 供观察)
    assert set(data["totals"]) == {"calories", "protein", "carbs", "fat", "fiber"}
    assert data["totals"]["calories"] == 1710
    # water 契约字段
    assert data["water"] == {"current_ml": 500, "target_ml": 2000}
    # observations 字段 = severity/label/detail(mobile parseObservations 读 severity)
    for o in data["observations"]:
        assert set(o) == {"severity", "label", "detail"}
        assert o["severity"] in {"normal", "caution", "risk"}


def test_observations_deterministic_and_factual():
    s = _summary()
    a = build_diet_daily_summary(s, weight_kg=71.2)["data"]["observations"]
    b = build_diet_daily_summary(s, weight_kg=71.2)["data"]["observations"]
    assert a == b  # 同输入同输出
    joined = " ".join(o["label"] + o["detail"] for o in a)
    # R4:陈述语气,禁命令式
    for banned in ("必须", "务必", "一定要", "应该马上"):
        assert banned not in joined
    # 脂肪 75g/1710kcal ≈ 39% > 35% → caution;纤维 4<25 → caution
    labels = {o["label"]: o["severity"] for o in a}
    assert labels.get("脂肪偏高") == "caution"
    assert labels.get("膳食纤维不足") == "caution"
    # 蛋白 92g/71.2kg ≈ 1.29g/kg ≥ 1.0 → 充足
    assert labels.get("蛋白质充足") == "normal"


def test_no_weight_degrades_protein_to_grams_only():
    obs = build_diet_daily_summary(_summary())["data"]["observations"]
    prot = [o for o in obs if o["label"] == "蛋白质"]
    assert prot and prot[0]["severity"] == "normal"
    assert "g/kg" not in prot[0]["detail"]


def test_empty_meals_returns_none_fail_open():
    assert build_diet_daily_summary({"meals": []}) is None
    assert build_diet_daily_summary({}) is None
    assert build_diet_daily_summary(None) is None  # type: ignore[arg-type]


def test_water_omitted_when_absent_or_zero_target():
    assert "water" not in build_diet_daily_summary(_summary())["data"]
    assert "water" not in build_diet_daily_summary(
        _summary(), water={"current_ml": 500, "target_ml": 0})["data"]


def test_registered_capability_and_view_validates():
    cap = get_atomic_capability("diet_daily_summary")
    assert cap is not None
    assert cap.action_types == ("route.open",)  # 只读,无写路径(R4)
    assert cap.safety_boundary == "suggest_only"
    assert set(("record_date", "meals", "totals")).issubset(set(cap.data_required_fields))
    # 一张最小 diet_daily_summary 卡在 mobile.chat 面上经 view 校验:类型已注册、必填齐、
    # 无非法动作 → 零 violation(证明注册与 validate_dynamic_view 对齐)。
    d = build_diet_daily_summary(_summary())
    card = {"type": "diet_daily_summary", "surface": "mobile.chat", "data": d["data"]}
    view = {"sections": [{"cards": [card]}]}
    violations = validate_dynamic_view(view)
    assert violations == [], violations


def test_render_block_is_reva_ui_fence():
    d = build_diet_daily_summary(_summary())
    block = render_diet_summary_block(d)
    assert block.startswith("```reva-ui\n")
    assert block.rstrip().endswith("```")
    assert '"type":"diet_daily_summary"' in block
