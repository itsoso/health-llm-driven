"""twin_to_prompt_blob 点亮 training_readiness(分 + Garmin 自己的判读)给 orchestrator LLM。

此前 formatter 发 HRV/睡眠/SpO2/VO2max 但**完全不发 training_readiness** → LLM 拿不到就绪度上下文,
只能从 specialist finding 看到一个裸数字。本增量补 LLM 侧视图(与已上线的 coach._readiness_driver_note
specialist 侧解释互补)。

护栏(同 vendor-unit 纪律):只发 Garmin 权威的 feedbackShort/Long,**不数值化 recoveryTime/
hrvWeeklyAverage**(原始透传、单位不确定)。全程 None/脏载荷安全,缺就只发分数,无数据不凭空造行。
"""
from datetime import datetime

from app.twin.formatter import twin_to_prompt_blob
from app.twin.schema import HealthTwin, PhysiologicalState, TwinMeta


def _twin(**physio) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.physiological = PhysiologicalState(**physio)
    return t


def test_readiness_score_in_blob():
    text = twin_to_prompt_blob(_twin(training_readiness_score=75))
    assert "训练就绪度 75" in text


def test_readiness_with_garmin_verdict():
    text = twin_to_prompt_blob(_twin(
        training_readiness_score=42,
        training_readiness_factors={"feedbackShort": "恢复时间未结束,建议低强度", "recoveryTime": 36},
    ))
    assert "训练就绪度 42" in text
    assert "恢复时间未结束" in text          # Garmin 权威判读进 blob
    assert "36" not in text                  # recoveryTime 单位不确定 → 不数值化进 blob


def test_readiness_falls_back_to_feedback_long():
    text = twin_to_prompt_blob(_twin(
        training_readiness_score=55,
        training_readiness_factors={"feedbackLong": "睡眠充足但急性负荷偏高"},
    ))
    assert "睡眠充足但急性负荷偏高" in text


def test_readiness_score_present_factors_none():
    text = twin_to_prompt_blob(_twin(training_readiness_score=88, training_readiness_factors=None))
    assert "训练就绪度 88" in text


def test_readiness_malformed_factors_no_crash_score_only():
    # feedbackShort 非字符串 / recoveryTime 字符串 → 只发分数,不抛,不臆造判读
    text = twin_to_prompt_blob(_twin(
        training_readiness_score=60,
        training_readiness_factors={"feedbackShort": 123, "recoveryTime": "n/a"},
    ))
    assert "训练就绪度 60" in text


def test_readiness_feedback_collapses_newlines_and_caps_length():
    # feedbackLong 是多句 prose:换行必须折叠(否则撑断生理单行)、长度必须截断(防 prompt 膨胀)
    long_fb = "就绪度中等。\n\nHRV 平衡,但急性负荷偏高。" + "尾巴" * 100
    text = twin_to_prompt_blob(_twin(
        training_readiness_score=42, training_readiness_factors={"feedbackLong": long_fb},
    ))
    assert "训练就绪度 42" in text
    seg = text.split("训练就绪度 42", 1)[1]
    verdict = seg[seg.index("(") + 1: seg.index(")")]
    assert "\n" not in verdict        # 换行已折叠
    assert len(verdict) <= 120        # 长度受限


def test_readiness_absent_no_line():
    text = twin_to_prompt_blob(_twin(hrv_latest=50.0))  # 有别的生理,但无就绪度
    assert "训练就绪度" not in text


def test_empty_twin_blob_stays_empty():
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    assert twin_to_prompt_blob(t) == ""  # 无生理 → 不凭空造就绪度行
