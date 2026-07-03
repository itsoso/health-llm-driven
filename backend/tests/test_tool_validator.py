"""tool_call_validator 单测 — 守门所有 LLM 给的 tool_call 参数."""
from datetime import date, datetime, timedelta

import pytest

from app.services.llm.tool_validator import validate_health_record, validate_tool_call


# ───────────── 日期守门 ─────────────


class TestDateGuard:
    def test_far_past_date_coerced_to_today(self):
        v = validate_health_record("diet", {
            "meal_type": "dinner", "food_items": "牛肉面",
            "record_date": "2023-10-09",
        })
        assert v["error"] is None
        assert v["data"]["record_date"] != "2023-10-09"
        # 应该是今天附近 (允许时区 ±1 天)
        recorded = v["data"]["record_date"]
        assert "2026" in recorded or "2027" in recorded or "2028" in recorded
        assert any("偏离" in w for w in v["warnings"])

    def test_far_future_date_coerced(self):
        v = validate_health_record("diet", {
            "food_items": "x",
            "record_date": "2099-01-01",
        })
        assert v["data"]["record_date"] != "2099-01-01"

    def test_recent_date_kept(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        v = validate_health_record("diet", {
            "food_items": "x",
            "record_date": yesterday,
        })
        assert v["data"]["record_date"] == yesterday

    def test_invalid_date_format(self):
        v = validate_health_record("diet", {
            "food_items": "x",
            "record_date": "Tuesday",
        })
        assert "Tuesday" not in v["data"]["record_date"]
        assert any("非合法" in w for w in v["warnings"])


# ───────────── 数值范围 ─────────────


class TestNumericRanges:
    def test_weight_extreme_high_removed(self):
        v = validate_health_record("weight", {"weight": 720})
        # 触发 required 检查: weight 必填, 移除后报 error
        assert v["error"] is not None
        assert "weight" in v["error"]
        assert any("超界" in w for w in v["warnings"])

    def test_weight_normal_kept(self):
        v = validate_health_record("weight", {"weight": 75.5})
        assert v["error"] is None
        assert v["data"]["weight"] == 75.5

    def test_bp_too_low(self):
        v = validate_health_record("blood_pressure", {"systolic": 32, "diastolic": 20})
        # 都被超界移除, 必填触发 error
        assert v["error"] is not None
        assert "systolic" in v["error"] or "diastolic" in v["error"]

    def test_bp_normal(self):
        v = validate_health_record("blood_pressure", {"systolic": 118, "diastolic": 78})
        assert v["error"] is None

    def test_water_missing_amount_returns_error(self):
        # amount 缺失不能默认 250,否则弱模型漏参会写错饮水量
        v = validate_health_record("water", {})
        assert v["error"] is not None
        assert "amount" in v["error"]

    def test_diet_calories_extreme_removed_but_no_error(self):
        # diet calories 超界移除, 但不是 required, 不报 error
        v = validate_health_record("diet", {
            "food_items": "x", "calories": 99999,
        })
        assert v["error"] is None
        assert "calories" not in v["data"]
        assert any("calories" in w and "超界" in w for w in v["warnings"])

    def test_non_numeric_string_removed(self):
        v = validate_health_record("weight", {"weight": "abc"})
        assert v["error"] is not None  # weight 必填, "abc" 移除后空


# ───────────── 必填检查 ─────────────


class TestRequiredFields:
    def test_diet_missing_food_items_returns_error(self):
        v = validate_health_record("diet", {"meal_type": "dinner"})
        assert v["error"] is not None
        assert "food_items" in v["error"]

    def test_diet_with_food_items_ok(self):
        v = validate_health_record("diet", {"food_items": "牛肉面"})
        assert v["error"] is None

    def test_water_missing_amount_is_required(self):
        v = validate_health_record("water", {})
        assert v["error"] is not None
        assert "amount" in v["error"]


class TestDietManagementIntentGuard:
    @pytest.mark.parametrize("food_items", [
        "我刚才不小心删除了",
        "删除这一餐",
        "把这餐删掉",
        "撤销刚才这顿晚餐",
        "恢复刚才误删的晚餐",
        ["误删了这条饮食记录"],
    ])
    def test_delete_or_undo_intent_never_becomes_diet_food_items(self, food_items):
        v = validate_tool_call("health_record", {
            "record_type": "diet",
            "data": {
                "meal_type": "dinner",
                "food_items": food_items,
                "calories": 0,
                "protein": 0,
                "carbs": 0,
                "fat": 0,
            },
        })

        assert v["error"] is not None
        assert "health_manage" in v["error"]
        assert any("删除/撤销" in warning for warning in v["warnings"])

    def test_normal_dinner_record_still_passes(self):
        v = validate_tool_call("health_record", {
            "record_type": "diet",
            "data": {
                "meal_type": "dinner",
                "food_items": "酸菜牛肉面 400g + 青菜",
                "calories": 680,
                "protein": 36,
            },
        })

        assert v["error"] is None


# ───────────── 引用 ID 越权 ─────────────


class TestReferenceIDGuard:
    def test_unknown_medication_id_removed(self, db):
        v = validate_health_record(
            "medication",
            {"medication_id": 99999, "taken_time": "08:00"},
            db=db, user_id=1,
        )
        # medication_id 不存在 → 移除. 不报 error 因为 medication 没把 id 列必填
        assert "medication_id" not in v["data"]
        assert any("medication_id" in w for w in v["warnings"])

    def test_no_db_skips_id_check(self):
        # 不传 db (测试单元) → ID 校验跳过
        v = validate_health_record(
            "medication",
            {"medication_id": 99999},
        )
        # 没 db 不校验, 保留
        assert v["data"].get("medication_id") == 99999


# ───────────── End-to-end yesterday's bug ─────────────


def test_yesterday_repro_bug_now_caught():
    """重现昨天 prod 的 bug — 用户记半份牛肉面但 LLM 给 2023-10-09."""
    args = {
        "meal_type": "晚餐",
        "food_items": "半份牛肉面",
        "calories": 350,
        "record_date": "2023-10-09",
    }
    v = validate_health_record("diet", args)
    assert v["error"] is None
    # 日期被覆盖了
    assert v["data"]["record_date"] != "2023-10-09"
    today_year = str(datetime.now().year)
    assert today_year in v["data"]["record_date"]


# ═══════════════════════════════════════════════════════════════
# 统一入口 validate_tool_call — 覆盖所有 6 个工具
# ═══════════════════════════════════════════════════════════════


class TestDispatcher:
    def test_unknown_tool_silent_passthrough(self):
        v = validate_tool_call("unknown_tool", {"foo": "bar"})
        assert v["error"] is None
        assert v["warnings"] == []
        assert v["data"]["foo"] == "bar"

    def test_non_dict_args_passthrough(self):
        v = validate_tool_call("health_query", "not a dict")  # type: ignore
        assert v["error"] is None

    def test_health_record_routes_through(self):
        """health_record 分支复用 validate_health_record."""
        v = validate_tool_call("health_record", {
            "record_type": "weight",
            "data": {"weight": 72.0, "record_date": "2023-10-09"},
        })
        assert v["error"] is None
        assert v["data"]["data"]["record_date"] != "2023-10-09"

    def test_health_record_with_non_dict_data(self):
        """LLM 乱塞 data=str, 应当 coerce 成 dict 而不是崩."""
        v = validate_tool_call("health_record", {
            "record_type": "water",
            "data": "not a dict",
        })
        assert isinstance(v["data"]["data"], dict)

    def test_enum_registry_sync_with_schema(self):
        """validate_tool_call 的 enum 必须和 tool_schema_registry 一致."""
        from app.services.tool_schema_registry import HEALTH_TOOLS
        from app.services.llm.tool_validator import (
            _QUERY_DIMENSIONS, _ANALYSIS_TYPES, _ENV_CHECK_TYPES, _PLAN_ACTIONS,
            _MANAGE_RECORD_TYPES, _MANAGE_OPERATIONS,
        )
        schemas = {t["function"]["name"]: t["function"]["parameters"]["properties"]
                   for t in HEALTH_TOOLS}
        assert set(schemas["health_query"]["dimension"]["enum"]) == _QUERY_DIMENSIONS
        assert set(schemas["health_manage"]["record_type"]["enum"]) == _MANAGE_RECORD_TYPES
        assert set(schemas["health_manage"]["operation"]["enum"]) == _MANAGE_OPERATIONS
        assert set(schemas["health_analysis"]["analysis_type"]["enum"]) == _ANALYSIS_TYPES
        assert set(schemas["environment_check"]["check_type"]["enum"]) == _ENV_CHECK_TYPES
        assert set(schemas["manage_plan"]["action"]["enum"]) == _PLAN_ACTIONS

    def test_health_manage_delete_requires_record_id(self):
        v = validate_tool_call("health_manage", {
            "record_type": "diet",
            "operation": "delete",
        })
        assert "record_id" in (v["error"] or "")

    def test_health_manage_record_id_coerced_to_int(self):
        v = validate_tool_call("health_manage", {
            "record_type": "diet",
            "operation": "delete",
            "record_id": "605",
        })
        assert v["error"] is None
        assert v["data"]["record_id"] == 605


class TestQueryGuard:
    def test_unknown_dimension_coerced(self):
        v = validate_tool_call("health_query", {"dimension": "foo"})
        assert v["data"]["dimension"] == "comprehensive"
        assert any("dimension" in w for w in v["warnings"])

    def test_query_dimension_alias_normalized_before_enum_guard(self):
        v = validate_tool_call("health_query", {"type": "medical_records", "days": 1})
        assert v["data"]["dimension"] == "medical_exam"
        assert v["data"]["days"] == 1

        v = validate_tool_call("health_query", {"dimension": "mri"})
        assert v["data"]["dimension"] == "medical_exam"

    def test_valid_dimension_kept(self):
        v = validate_tool_call("health_query", {"dimension": "hrv", "days": 14})
        assert v["data"]["dimension"] == "hrv"
        assert v["data"]["days"] == 14
        assert v["warnings"] == []

    def test_days_out_of_range_coerced(self):
        v = validate_tool_call("health_query", {"dimension": "sleep", "days": 99999})
        assert v["data"]["days"] == 7

    def test_days_zero_coerced(self):
        v = validate_tool_call("health_query", {"dimension": "sleep", "days": 0})
        assert v["data"]["days"] == 7

    def test_days_not_int_coerced(self):
        v = validate_tool_call("health_query", {"dimension": "sleep", "days": "many"})
        assert v["data"]["days"] == 7

    def test_indicator_dropped_when_dim_irrelevant(self):
        v = validate_tool_call("health_query", {"dimension": "sleep", "indicator": "LDL"})
        assert "indicator" not in v["data"]

    def test_indicator_kept_for_medical_exam(self):
        v = validate_tool_call("health_query", {
            "dimension": "medical_exam", "indicator": "LDL",
        })
        assert v["data"]["indicator"] == "LDL"

    def test_indicator_truncated(self):
        v = validate_tool_call("health_query", {
            "dimension": "genetic", "indicator": "X" * 500,
        })
        assert len(v["data"]["indicator"]) == 64

    def test_dimension_missing_coerced_to_default(self):
        v = validate_tool_call("health_query", {})
        assert v["data"]["dimension"] == "comprehensive"


class TestAnalysisGuard:
    def test_unknown_type_coerced(self):
        v = validate_tool_call("health_analysis", {"analysis_type": "foo"})
        assert v["data"]["analysis_type"] == "comprehensive"
        assert any("analysis_type" in w for w in v["warnings"])

    def test_orchestrator_requires_question(self):
        v = validate_tool_call("health_analysis", {"analysis_type": "orchestrator"})
        assert v["error"] is not None
        assert "question" in v["error"]

    def test_orchestrator_with_question_ok(self):
        v = validate_tool_call("health_analysis", {
            "analysis_type": "orchestrator", "question": "我最近为什么 HRV 偏低?",
        })
        assert v["error"] is None

    def test_non_orchestrator_no_question_ok(self):
        v = validate_tool_call("health_analysis", {"analysis_type": "trend"})
        assert v["error"] is None

    def test_question_truncated(self):
        v = validate_tool_call("health_analysis", {
            "analysis_type": "orchestrator", "question": "x" * 3000,
        })
        assert len(v["data"]["question"]) == 2000

    def test_days_bounded(self):
        v = validate_tool_call("health_analysis", {
            "analysis_type": "trend", "days": -5,
        })
        assert v["data"]["days"] == 7


class TestEnvironmentGuard:
    def test_unknown_check_type_coerced(self):
        v = validate_tool_call("environment_check", {"check_type": "foo"})
        assert v["data"]["check_type"] == "weather"

    def test_valid_check_type_kept(self):
        v = validate_tool_call("environment_check", {"check_type": "air_quality"})
        assert v["data"]["check_type"] == "air_quality"
        assert v["warnings"] == []


class TestSupplementGuard:
    def test_empty_args_ok(self):
        v = validate_tool_call("supplement_guide", {})
        assert v["error"] is None

    def test_extra_args_stripped_silently(self):
        """LLM 乱塞字段是常见幻觉, 不 warn 不 error, silent strip."""
        v = validate_tool_call("supplement_guide", {"foo": "bar", "days": 7})
        assert v["error"] is None
        assert v["data"] == {}
        assert v["warnings"] == []


class TestManagePlanGuard:
    def test_unknown_action_error(self):
        v = validate_tool_call("manage_plan", {"action": "delete_everything", "data": {}})
        assert v["error"] is not None
        assert "action" in v["error"]

    def test_missing_action_error(self):
        v = validate_tool_call("manage_plan", {"data": {}})
        assert v["error"] is not None

    def test_generate_weekly_target_week_coerced(self):
        v = validate_tool_call("manage_plan", {
            "action": "generate_weekly",
            "data": {"target_week": "someday"},
        })
        assert v["data"]["data"]["target_week"] == "current"

    def test_generate_weekly_valid(self):
        v = validate_tool_call("manage_plan", {
            "action": "generate_weekly", "data": {"target_week": "next"},
        })
        assert v["error"] is None

    def test_complete_item_missing_plan_id_error(self):
        v = validate_tool_call("manage_plan", {
            "action": "complete_item", "data": {"item_id": 5},
        })
        assert v["error"] is not None
        assert "plan_id" in v["error"]

    def test_complete_item_no_db_skips_check(self):
        """测试模式 (无 db) 跳过越权检查."""
        v = validate_tool_call("manage_plan", {
            "action": "complete_item", "data": {"plan_id": 99, "item_id": 5},
        })
        assert v["error"] is None

    def test_complete_item_cross_user_blocked(self, db):
        """LLM 编造 plan_id 属于别人, 应当拦截."""
        v = validate_tool_call("manage_plan", {
            "action": "complete_item",
            "data": {"plan_id": 99999, "item_id": 5},
        }, db=db, user_id=1)
        assert v["error"] is not None
        assert "99999" in v["error"]

    def test_save_to_card_card_type_coerced(self):
        v = validate_tool_call("manage_plan", {
            "action": "save_to_card",
            "data": {"card_type": "foo", "title": "t", "content": "c"},
        })
        assert v["data"]["data"]["card_type"] == "insight"

    def test_save_to_card_content_truncated(self):
        v = validate_tool_call("manage_plan", {
            "action": "save_to_card",
            "data": {"card_type": "plan", "title": "t", "content": "x" * 20000},
        })
        assert len(v["data"]["data"]["content"]) == 10000

    def test_save_to_card_title_truncated(self):
        v = validate_tool_call("manage_plan", {
            "action": "save_to_card",
            "data": {"card_type": "plan", "title": "t" * 500, "content": "c"},
        })
        assert len(v["data"]["data"]["title"]) == 200


class TestBypassSafe:
    def test_validator_exception_does_not_propagate(self, monkeypatch):
        """validator 自身崩 → 放行, 不让工具调用挂."""
        from app.services.llm import tool_validator as tv

        def boom(*a, **k):
            raise RuntimeError("validator crashed")

        monkeypatch.setitem(tv._TOOL_VALIDATORS, "health_query", boom)
        v = tv.validate_tool_call("health_query", {"dimension": "sleep"})
        assert v["error"] is None
        assert v["warnings"] == []
