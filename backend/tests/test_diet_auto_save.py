"""饮食自动补录工具函数单元测试"""
import pytest
from unittest.mock import patch
from app.api.openclaw import _is_diet_record_intent, _detect_meal_type, _extract_food_and_calories


class TestIsDietRecordIntent:
    """测试 _is_diet_record_intent 意图检测"""

    def test_record_lunch_with_ai_confirmed(self):
        """'记录午餐：鸡胸肉100克+米饭' + AI 回复 '已为你记录' → 应匹配"""
        msg = "记录午餐：鸡胸肉100克+米饭"
        reply = "已为你记录午餐，鸡胸肉100克+米饭，合计约 653 kcal。"
        assert _is_diet_record_intent(msg, reply) is True

    def test_complaint_with_exclude_keyword(self):
        """'饮食记录有问题' + AI 回复 '已记录' → 不应匹配（含排除关键词 '问题'）"""
        msg = "饮食记录有问题"
        reply = "已记录你的反馈，我们会改进。"
        assert _is_diet_record_intent(msg, reply) is False

    def test_negation_exclude_keyword(self):
        """'没有将热量记录到饮食中' → 不应匹配（含排除关键词 '没有'）"""
        msg = "没有将热量记录到饮食中"
        reply = "已记录你说的情况。"
        assert _is_diet_record_intent(msg, reply) is False

    def test_ate_pattern_with_checkmark(self):
        """'吃了牛肉面' + AI 回复 '已记录✅' → 应匹配"""
        msg = "吃了牛肉面"
        reply = "已记录✅ 牛肉面约 550 kcal"
        assert _is_diet_record_intent(msg, reply) is True

    def test_no_ai_confirmation(self):
        """用户说了吃了什么，但 AI 没说 '已记录' → 不应匹配"""
        msg = "吃了沙拉"
        reply = "沙拉是很好的选择，建议搭配蛋白质。"
        assert _is_diet_record_intent(msg, reply) is False

    def test_query_not_record(self):
        """'查询今天饮食' → 不应匹配（含排除关键词 '查询'）"""
        msg = "查询今天饮食"
        reply = "已记录以下数据..."
        assert _is_diet_record_intent(msg, reply) is False

    def test_record_breakfast(self):
        """'记录早餐：牛奶+面包' + AI 确认 → 应匹配"""
        msg = "记录早餐：牛奶+面包"
        reply = "已为你记录早餐。"
        assert _is_diet_record_intent(msg, reply) is True


class TestDetectMealType:
    """测试 _detect_meal_type 餐次检测"""

    def test_explicit_lunch(self):
        assert _detect_meal_type("记录午餐：鸡胸肉") == "lunch"

    def test_explicit_breakfast(self):
        assert _detect_meal_type("记录早餐：牛奶") == "breakfast"

    def test_explicit_dinner(self):
        assert _detect_meal_type("记录晚餐：牛排") == "dinner"

    def test_explicit_snack(self):
        assert _detect_meal_type("记录加餐：坚果") == "snack"

    def test_explicit_night_snack(self):
        assert _detect_meal_type("记录宵夜：泡面") == "snack"

    def test_time_based_morning(self):
        """没有餐次关键词时，根据时间推断"""
        with patch("app.api.openclaw.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 7
            result = _detect_meal_type("吃了面包")
            assert result == "breakfast"

    def test_time_based_noon(self):
        with patch("app.api.openclaw.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            result = _detect_meal_type("吃了米饭")
            assert result == "lunch"

    def test_time_based_evening(self):
        with patch("app.api.openclaw.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 19
            result = _detect_meal_type("吃了面条")
            assert result == "dinner"


class TestExtractFoodAndCalories:
    """测试 _extract_food_and_calories 食物和热量提取"""

    def test_extract_from_record_pattern(self):
        """从 '记录午餐：鸡胸肉+米饭' 提取食物"""
        food, cal = _extract_food_and_calories(
            "记录午餐：鸡胸肉+米饭",
            "已为你记录，= 653 kcal"
        )
        assert "鸡胸肉" in food
        assert cal == 653.0

    def test_extract_from_ate_pattern(self):
        """从 '吃了牛肉面' 提取食物"""
        food, cal = _extract_food_and_calories(
            "吃了牛肉面",
            "牛肉面约550kcal"
        )
        assert "牛肉面" in food
        assert cal == 550.0

    def test_approx_calorie_pattern(self):
        """'约400千卡' 格式"""
        food, cal = _extract_food_and_calories(
            "吃了沙拉",
            "沙拉约400千卡"
        )
        assert cal == 400.0

    def test_no_calorie_in_reply(self):
        """AI 回复没有热量信息"""
        food, cal = _extract_food_and_calories(
            "吃了苹果",
            "已为你记录苹果。"
        )
        assert "苹果" in food
        assert cal is None

    def test_too_large_calorie_ignored(self):
        """超过 3000 的热量被忽略"""
        food, cal = _extract_food_and_calories(
            "吃了沙拉",
            "今日总摄入 3500kcal"
        )
        # 3500 > 3000 should be ignored
        assert cal is None

    def test_equals_sign_calorie(self):
        """'= 653 kcal' 格式"""
        food, cal = _extract_food_and_calories(
            "记录晚餐：牛排+沙拉",
            "合计 = 653 kcal"
        )
        assert cal == 653.0

    def test_approx_sign_calorie(self):
        """'≈ 800 kcal' 格式"""
        food, cal = _extract_food_and_calories(
            "吃了汉堡",
            "热量 ≈ 800 kcal"
        )
        assert cal == 800.0
