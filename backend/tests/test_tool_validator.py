"""tool_call_validator 单测 — 守门所有 LLM 给的 health_record 参数."""
from datetime import date, datetime, timedelta

import pytest

from app.services.llm.tool_validator import validate_health_record


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

    def test_water_default(self):
        # amount 缺失 → 用默认 250
        v = validate_health_record("water", {})
        assert v["data"]["amount"] == 250

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

    def test_water_no_required_ok(self):
        # water 没有必填字段, amount 用默认值
        v = validate_health_record("water", {})
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
