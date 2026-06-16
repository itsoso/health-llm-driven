"""记录类响应的 display_message 成品话术。

背景: 弱模型 (deepseek-v4-pro 等) 不可靠地遵守 "禁止输出原始 JSON",
观测到 "记录20个俯卧撑" 被回成整坨 ORM JSON。确定性修法是让写端点的响应
自带成品话术 display_message (对齐 DietRecordResponse), skill 只需原样输出。
这里锁住 display_message 的计算, 防回归。
"""
from datetime import date, datetime

from app.schemas.daily_health import ExerciseRecordResponse
from app.schemas.checkin import CheckinRecordResponse


def _exercise(**kw):
    base = dict(id=1, user_id=3, record_date=date(2026, 6, 16), exercise_type="俯卧撑")
    base.update(kw)
    return ExerciseRecordResponse(**base)


def test_exercise_reps_only():
    assert _exercise(reps=20).display_message == "✅ 已记录俯卧撑 20 个"


def test_exercise_sets_times_reps():
    assert _exercise(sets=3, reps=15).display_message == "✅ 已记录俯卧撑 3 组 × 15 个"


def test_exercise_single_set_collapses_to_reps():
    # sets=1 不啰嗦成 "1 组 × N"
    assert _exercise(sets=1, reps=15).display_message == "✅ 已记录俯卧撑 15 个"


def test_exercise_duration_seconds():
    assert _exercise(exercise_type="平板支撑", duration_seconds=90).display_message == "✅ 已记录平板支撑 90 秒"


def test_exercise_duration_minutes():
    assert _exercise(exercise_type="跑步", duration=30).display_message == "✅ 已记录跑步 30 分钟"


def test_exercise_duration_and_distance():
    msg = _exercise(exercise_type="跑步", duration=30, distance=5.0).display_message
    assert msg == "✅ 已记录跑步 30 分钟，5 公里"


def test_exercise_bare_type():
    assert _exercise(exercise_type="瑜伽").display_message == "✅ 已记录瑜伽"


def test_exercise_never_leaks_raw_fields():
    # 回归锁: display_message 里不能出现 id/user_id 等裸字段名
    msg = _exercise(reps=20).display_message
    assert "id" not in msg and "user_id" not in msg and "{" not in msg


def _checkin(**kw):
    base = dict(
        id=1,
        user_id=3,
        template_id=19,
        checkin_date=date(2026, 6, 16),
        value=20.0,
        checkin_time=datetime(2026, 6, 16, 8, 0, 0),
        created_at=datetime(2026, 6, 16, 8, 0, 0),
        template_name="俯卧撑",
    )
    base.update(kw)
    return CheckinRecordResponse(**base)


def test_checkin_integer_value_no_decimal():
    assert _checkin(value=20.0).display_message == "✅ 已记录俯卧撑 20"


def test_checkin_fractional_value_kept():
    assert _checkin(template_name="拉伸", value=2.5).display_message == "✅ 已记录拉伸 2.5"


def test_checkin_missing_template_name_falls_back():
    assert _checkin(template_name=None, value=5.0).display_message == "✅ 已记录打卡 5"
