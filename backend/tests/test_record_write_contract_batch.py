"""记录写入契约一批修复的回归测试（scan 找出的 P1/P2/P3 同类未修 bug）。

覆盖:
- #1 mood 写入端到端结构性损坏: score→mood_score + 1-10→1-5 + notes→journal
  （历史: 每一次经聊天记录心情都 422, 显示层 /5 早修但从没被触达）。
- #3 health_record 相对日期字面量未归一: record_date/start_date='昨天'/'前天' 在
  创建路径折成真 ISO（曾: record_date 被静默吞成今天 / start_date 直接 422）。
- #12 鼻炎 congestion/runny_nose 契约统一到 0-3 级（曾: validator 0-10·0-200）。
"""
from datetime import datetime, timedelta

from app.services.llm.tool_validator import validate_health_record, validate_tool_call
from app.services.agent_executor import (
    _prepare_health_record_args_for_validation,
    _normalize_relative_date,
    BEIJING_TZ,
)


# ───────────── #1 mood 写入契约 ─────────────

class TestMoodWriteContract:
    def test_legacy_score_renamed_and_rescaled_to_mood_score(self):
        # 弱模型按旧 schema 吐 {"score":7,"notes":...}(1-10) → 端点要 mood_score(1-5)+journal
        v = validate_health_record("mood", {"score": 7, "notes": "心情不错"})
        d = v["data"]
        assert "score" not in d           # 旧字段名清除
        assert "notes" not in d
        assert d["mood_score"] == 4        # 7/10 → round(3.5)=4, 落在 1-5
        assert d["journal"] == "心情不错"   # notes→journal
        assert v["error"] is None

    def test_native_mood_score_1_to_5_passes_through(self):
        v = validate_health_record("mood", {"mood_score": 4, "journal": "还行"})
        assert v["data"]["mood_score"] == 4
        assert v["data"]["journal"] == "还行"

    def test_low_score_not_rescaled(self):
        # score<=5 视为已是 1-5, 不折半(3 保持 3, 不变成 1.5→2)
        v = validate_health_record("mood", {"score": 3})
        assert v["data"]["mood_score"] == 3

    def test_score_10_clamps_to_5(self):
        v = validate_health_record("mood", {"score": 10})
        assert v["data"]["mood_score"] == 5

    def test_mood_score_never_dropped_as_out_of_range(self):
        # 修复前: score 进 mood_score 后被 _validate_numeric(1-5) 当超界 pop → 必填缺失 → 422。
        # 修复后: 归一在 _validate_numeric 之前, mood_score 恒存在。
        for raw in (6, 7, 8, 9, 10):
            v = validate_health_record("mood", {"score": raw})
            assert "mood_score" in v["data"], f"score={raw} 丢了 mood_score"
            assert 1 <= v["data"]["mood_score"] <= 5

    def test_type_alias_not_bypassing_mood_normalization(self):
        # 模型常吐 type=mood(而非 record_type) → validate_tool_call 必须也归一, 否则绕过 → 422
        args = {"type": "mood", "data": {"score": 8, "notes": "累"}}
        out = validate_tool_call("health_record", args)
        d = out["data"]["data"]
        assert d.get("mood_score") == 4    # 8/10 → 4
        assert "score" not in d
        assert d.get("journal") == "累"


# ───────────── #3 相对日期创建路径归一 ─────────────

class TestRelativeDateCreatePath:
    def _yesterday_iso(self):
        return (datetime.now(BEIJING_TZ).date() - timedelta(days=1)).isoformat()

    def _day_before_iso(self):
        return (datetime.now(BEIJING_TZ).date() - timedelta(days=2)).isoformat()

    def test_diet_record_date_yesterday_normalized(self):
        args = {"record_type": "diet", "data": {"food_items": "火锅", "record_date": "昨天"}}
        out = _prepare_health_record_args_for_validation("health_record", args)
        assert out["data"]["record_date"] == self._yesterday_iso()  # 不再静默变今天

    def test_illness_start_date_day_before_normalized(self):
        args = {"record_type": "illness", "data": {"name": "感冒", "start_date": "前天"}}
        out = _prepare_health_record_args_for_validation("health_record", args)
        assert out["data"]["start_date"] == self._day_before_iso()  # 不再原样发出→422

    def test_end_date_relative_normalized(self):
        args = {"record_type": "illness", "data": {"name": "溃疡", "end_date": "昨天"}}
        out = _prepare_health_record_args_for_validation("health_record", args)
        assert out["data"]["end_date"] == self._yesterday_iso()

    def test_iso_date_untouched(self):
        args = {"record_type": "diet", "data": {"food_items": "x", "record_date": "2026-07-01"}}
        out = _prepare_health_record_args_for_validation("health_record", args)
        assert out["data"]["record_date"] == "2026-07-01"

    def test_unparseable_left_for_downstream(self):
        # 折不出 → 留原值给下游默认(不覆盖), 归一函数返回 None
        assert _normalize_relative_date("下个季度某天") is None
        args = {"record_type": "diet", "data": {"food_items": "x", "record_date": "下个季度某天"}}
        out = _prepare_health_record_args_for_validation("health_record", args)
        assert out["data"]["record_date"] == "下个季度某天"


# ───────────── #12 鼻炎量表契约 0-3 ─────────────

class TestRhinitisScaleContract:
    def test_congestion_within_0_3_kept(self):
        v = validate_health_record("rhinitis", {"sneezing": 5, "congestion": 2, "runny_nose": 1})
        assert v["data"]["congestion"] == 2
        assert v["data"]["runny_nose"] == 1

    def test_congestion_above_3_rejected(self):
        # 曾: congestion 上限 10 放行幻觉值; 现在收紧到 0-3, 超界移除
        v = validate_health_record("rhinitis", {"sneezing": 1, "congestion": 8})
        assert "congestion" not in v["data"] or v["data"].get("congestion") in (0, None)
