"""RecoveryCoach 暗信号点亮:sleep_consistency_score + training_readiness_factors。

两个 Garmin 计算好、回灌进 Twin 但**零消费**的信号,接进 readiness 行动/解释。
不变量(评审重点):
- **纯叙事、加法**:不改 compute_readiness 评分(consistency/factors 永不进加权分);
  不删/不改写既有 action;action 总数 ≤ 4(R15)。
- **None / 脏厂商载荷安全**:每个新字段访问都 guard None / 非 dict / 字符串值,缺失就省略该行,
  绝不抛异常崩掉整个 recovery finding(崩=静默欠教练)。
- **recoveryTime/hrvWeeklyAverage 单位不确定 → 不做数值解读**(只用 Garmin 自己的 feedback 文案
  或语义明确的 sleepScore),避免误述。
"""
from datetime import datetime

from app.agents.recovery_coach.coach import (
    ReadinessBreakdown,
    RecoveryCoachSpecialist,
    _build_actions,
    _readiness_driver_note,
    compute_readiness,
)
from app.twin.schema import HealthTwin, PhysiologicalState, TwinMeta


def _twin(**physio) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.physiological = PhysiologicalState(**physio)
    return t


def _bd(zone="moderate", score=72, components=None, penalty=0.0) -> ReadinessBreakdown:
    return ReadinessBreakdown(
        score=score, components=components or {}, weights_used={},
        penalty=penalty, missing_components=[], zone=zone,
    )


# ───────────────────── sleep_consistency_score ─────────────────────


def test_low_consistency_with_adequate_duration_emits_action():
    # 时长够(7.8h→component≈1.09)但作息不规律(35/100)→ 出「固定起床时间」建议
    bd = _bd(components={"sleep_duration": 1.09, "sleep_quality": 0.8})
    twin = _twin(sleep_consistency_score=35, sleep_duration_h_latest=7.8)
    actions = _build_actions(bd, twin)
    assert any("作息不规律" in a and "35" in a for a in actions)


def test_high_consistency_no_action():
    bd = _bd(components={"sleep_duration": 1.09})
    twin = _twin(sleep_consistency_score=88, sleep_duration_h_latest=7.8)
    actions = _build_actions(bd, twin)
    assert not any("作息不规律" in a for a in actions)


def test_consistency_none_no_action_no_crash():
    bd = _bd(components={"sleep_duration": 1.09})
    twin = _twin(sleep_consistency_score=None, sleep_duration_h_latest=7.8)
    actions = _build_actions(bd, twin)
    assert not any("作息不规律" in a for a in actions)


def test_short_sleep_suppresses_consistency_no_double_advice():
    # 时长不足已有专门建议 → 不再叠加「时长够但作息不规律」(矛盾)。短睡建议必须在。
    bd = _bd(zone="light", components={"sleep_duration": 0.5})
    twin = _twin(sleep_consistency_score=20, sleep_duration_h_latest=5.0)
    actions = _build_actions(bd, twin)
    assert any("睡眠仅" in a or "睡眠不足" in a for a in actions)  # 短睡建议在
    assert not any("作息不规律" in a for a in actions)            # 不叠加 consistency


def test_consistency_unknown_duration_skips_to_avoid_false_claim():
    # 时长未知 → 不能声称「时长尚可」→ 不出该建议(保守)
    bd = _bd(components={})
    twin = _twin(sleep_consistency_score=20, sleep_duration_h_latest=None)
    actions = _build_actions(bd, twin)
    assert not any("作息不规律" in a for a in actions)


def test_consistency_middle_zone_under_7h_makes_no_adequacy_claim():
    # 评审 NIT 修复:6.7h(component≈0.77)在短睡阈(<0.7)与「尚可」阈(>=0.85)之间——
    # 既不命中短睡建议,也不该声称时长尚可(系统短睡目标是 7.5h,7h 以下说「尚可」会自相矛盾)。
    bd = _bd(components={"sleep_duration": 0.77})  # ≈6.7h
    twin = _twin(sleep_consistency_score=30, sleep_duration_h_latest=6.7)
    actions = _build_actions(bd, twin)
    assert not any("作息不规律" in a for a in actions)  # 不在 7h 以下做时长尚可声称


# ───────────────────── training_readiness_factors driver note ─────────────────────


def test_driver_note_prefers_garmin_feedback():
    note = _readiness_driver_note(
        _twin(training_readiness_factors={"feedbackShort": "恢复时间未结束", "sleepScore": 80})
    )
    assert note and "恢复时间未结束" in note


def test_driver_note_falls_back_to_low_sleepscore():
    note = _readiness_driver_note(_twin(training_readiness_factors={"sleepScore": 45}))
    assert note and "45" in note


def test_driver_note_does_not_interpret_recoverytime_uncertain_unit():
    # recoveryTime 单位不确定 + 无 feedback + sleepScore 不低 → 不臆测,返回 None
    assert _readiness_driver_note(_twin(training_readiness_factors={"recoveryTime": 36})) is None


def test_driver_note_none_and_empty_factors():
    assert _readiness_driver_note(_twin(training_readiness_factors=None)) is None
    assert _readiness_driver_note(_twin(training_readiness_factors={})) is None


def test_driver_note_coerces_string_number_sleepscore():
    # 厂商常把数值塞成字符串:"45" 必须经 _safe 当 45 处理(<60→出 note),"85"→不出
    note = _readiness_driver_note(_twin(training_readiness_factors={"sleepScore": "45"}))
    assert note and "45" in note
    assert _readiness_driver_note(_twin(training_readiness_factors={"sleepScore": "85"})) is None


def test_driver_note_non_str_feedback_falls_through():
    # feedbackShort 非字符串(脏载荷)→ 不当文案用,退到 sleepScore
    note = _readiness_driver_note(_twin(training_readiness_factors={"feedbackShort": 123, "sleepScore": 40}))
    assert note and "40" in note


def test_driver_note_malformed_payload_no_crash():
    # 脏厂商载荷(字符串/None 值、空 feedback)→ 安全返回 None,不抛
    # (schema 是 Optional[Dict],非 dict 由 Pydantic 拦在构造期;此处验 dict 内值脏的情况)
    assert _readiness_driver_note(
        _twin(training_readiness_factors={"recoveryTime": "n/a", "sleepScore": None, "feedbackShort": ""})
    ) is None


# ───────────────────── 不变量 ─────────────────────


def test_readiness_score_unchanged_by_consistency():
    """consistency 纯叙事,绝不动 readiness 分。"""
    base = dict(hrv_latest=50, hrv_7d_avg=50, sleep_score_latest=80,
                sleep_duration_h_latest=7.0, body_battery_current=70, stress_level_current=30)
    s_with = compute_readiness(_twin(**base, sleep_consistency_score=15)).score
    s_without = compute_readiness(_twin(**base)).score
    assert s_with == s_without


def test_readiness_score_unchanged_by_factors():
    """training_readiness_factors 也纯叙事,绝不动 readiness 分。"""
    base = dict(hrv_latest=50, hrv_7d_avg=50, sleep_score_latest=80,
                sleep_duration_h_latest=7.0, body_battery_current=70, stress_level_current=30)
    s_with = compute_readiness(_twin(**base, training_readiness_factors={"feedbackShort": "x", "sleepScore": 10})).score
    s_without = compute_readiness(_twin(**base)).score
    assert s_with == s_without


def test_action_cap_preserved_under_full_load():
    # 同时触发: 训练建议 + 短睡 + 低质量 + 低HRV + 高压力 + penalty + driver note → 仍 ≤ 4
    bd = _bd(zone="rest", score=40, penalty=12.0,
             components={"sleep_duration": 0.4, "sleep_quality": 0.5, "hrv": 0.3, "stress": 0.3})
    twin = _twin(sleep_duration_h_latest=4.5,
                 training_readiness_factors={"feedbackShort": "恢复未完成"})
    actions = _build_actions(bd, twin)
    assert len(actions) <= 4


def test_driver_note_surfaces_when_components_sparse():
    # Garmin 官方 readiness 分 + factors,但细粒度 component 缺 → driver note 有空间冒出
    twin = _twin(training_readiness_score=45,
                 training_readiness_factors={"feedbackShort": "恢复尚未完成,建议低强度"})
    finding = RecoveryCoachSpecialist().run(twin, {})
    texts = [f.get("text", "") for f in finding.findings if f.get("type") == "action"]
    assert any("恢复尚未完成" in t for t in texts)


def test_empty_twin_still_unknown_and_safe():
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    bd = compute_readiness(t)
    assert bd.zone == "unknown"
    actions = _build_actions(bd, t)
    assert any("数据不足" in a for a in actions)
