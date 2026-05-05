"""
A-I 产品改进的 smoke test — 纯函数 / 浅入口.
不依赖 DB 复杂状态, 不调 LLM (会 mock), 防止改其它代码时打破语音稿生成.

覆盖:
  - alert_clarification.get_clarification_opener (D)
  - briefing_voice_script._format_* helpers (A)
  - weekly_review_voice_script._delta_str (E)
  - preworkout_voice_script._activity_zh (F)
  - events_timeline_service._workout_type_zh (H)
"""
import pytest


# ────────────────── D: 告警澄清模板 ──────────────────

class TestClarificationOpener:
    def test_unknown_alert_type(self):
        from app.services.alert_clarification import get_clarification_opener

        class FakeAlert:
            id = 1
            alert_type = "battery_low"  # 没模板
            current_value = 25
            baseline_value = 70

        assert get_clarification_opener(FakeAlert()) is None

    def test_spo2_low_with_data(self):
        from app.services.alert_clarification import get_clarification_opener

        class FakeAlert:
            id = 99
            alert_type = "spo2_low"
            current_value = 88
            baseline_value = 95

        result = get_clarification_opener(FakeAlert())
        assert result is not None
        assert "侧睡或者枕头" in result["opener"]
        assert "88" in result["opener"]
        assert result["alert_type"] == "spo2_low"

    def test_rhr_spike_with_delta(self):
        from app.services.alert_clarification import get_clarification_opener

        class FakeAlert:
            id = 1
            alert_type = "rhr_spike"
            current_value = 58
            baseline_value = 50

        result = get_clarification_opener(FakeAlert())
        assert result is not None
        assert "8" in result["opener"]  # delta
        assert "感冒" in result["opener"] or "酒" in result["opener"]


# ────────────────── A: 晨间简报短稿格式化 ──────────────────

class TestBriefingFormatters:
    def test_format_sleep_with_minutes(self):
        from app.services.briefing_voice_script import _format_sleep
        from types import SimpleNamespace

        twin = SimpleNamespace(
            physiological=SimpleNamespace(sleep_duration_h_latest=7.5)
        )
        out = _format_sleep(twin)
        assert "7" in out
        assert "30 分" in out  # 0.5 * 60 = 30 分

    def test_format_sleep_none(self):
        from app.services.briefing_voice_script import _format_sleep
        from types import SimpleNamespace

        twin = SimpleNamespace(
            physiological=SimpleNamespace(sleep_duration_h_latest=None)
        )
        assert _format_sleep(twin) is None

    def test_format_battery_low(self):
        from app.services.briefing_voice_script import _format_battery_or_stress
        from types import SimpleNamespace

        twin = SimpleNamespace(
            physiological=SimpleNamespace(
                body_battery_current=35, stress_level_current=None,
            )
        )
        out = _format_battery_or_stress(twin)
        assert "电量偏低" in out


# ────────────────── E: 周聊 delta 短语 ──────────────────

class TestWeeklyDeltaStr:
    def test_delta_below_threshold_returns_empty(self):
        from app.services.weekly_review_voice_script import _delta_str
        # 本周 vs 上周差异 < 5%, 不强调
        assert _delta_str(100, 102) == ""
        assert _delta_str(50, 51) == ""

    def test_delta_more(self):
        from app.services.weekly_review_voice_script import _delta_str
        # 跑量本周 12 公里 vs 上周 10 公里
        out = _delta_str(12, 10, " 公里")
        assert "比上周多" in out
        assert "2" in out

    def test_delta_less(self):
        from app.services.weekly_review_voice_script import _delta_str
        out = _delta_str(7, 10, " 公里")
        assert "比上周少" in out

    def test_delta_none_inputs(self):
        from app.services.weekly_review_voice_script import _delta_str
        assert _delta_str(None, 10) == ""
        assert _delta_str(10, None) == ""
        assert _delta_str(10, 0) == ""


# ────────────────── F: 跑前 — 活动类型中文化 ──────────────────

class TestPreworkoutActivityZh:
    def test_known_types(self):
        from app.services.preworkout_voice_script import _activity_zh

        assert _activity_zh("running") == "跑步"
        assert _activity_zh("cycling") == "骑行"
        assert _activity_zh("yoga") == "瑜伽"

    def test_case_insensitive(self):
        from app.services.preworkout_voice_script import _activity_zh

        assert _activity_zh("RUNNING") == "跑步"
        assert _activity_zh("Running") == "跑步"

    def test_unknown_default(self):
        from app.services.preworkout_voice_script import _activity_zh

        assert _activity_zh(None) == "今天的训练"
        assert _activity_zh("") == "今天的训练"
        assert _activity_zh("paragliding") == "今天的训练"


# ────────────────── H: Timeline workout 类型中文化 ──────────────────

class TestTimelineWorkoutTypeZh:
    def test_known(self):
        from app.services.events_timeline_service import _workout_type_zh
        assert _workout_type_zh("running") == "跑步"
        assert _workout_type_zh("hiit") == "HIIT"

    def test_unknown_returns_input_or_default(self):
        from app.services.events_timeline_service import _workout_type_zh
        assert _workout_type_zh("kayaking") == "kayaking"
        assert _workout_type_zh("") == "训练"
