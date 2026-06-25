"""MetabolicSpecialist 中心性肥胖判定:用腰围标准(central_obesity_flag,IDF/NCEP 权威)
替代 BMI≥28 简化代理 —— 但 (a) 无腰围数据、(b) 腰围读数过期 时退回 BMI,不丢信号。

central_obesity_flag 语义:True=腰围超性别阈值、False=腰围已测且未超、None=无腰围数据。
freshness 门(对抗评审 BLOCKING 修复):只信 ≤180 天的腰围;陈年「正常」腰围不能否定当前高 BMI
风险(否则 stale False 会把当前 BMI 驱动的代谢综合征命中静默抹掉 = under-alarm)。
设计:新鲜 True→计;新鲜 False→不计(去 BMI 伪阳);过期/None→退回 BMI≥28 代理。
"""
from datetime import datetime, timedelta

from app.agents.chronic_specialists.metabolic import _metabolic_syndrome_criteria
from app.twin.schema import BodyCompositionState, HealthTwin, LabsContext, TwinMeta
from app.utils.timezone import get_china_today

_FRESH = get_china_today() - timedelta(days=10)    # 新鲜腰围
_STALE = get_china_today() - timedelta(days=400)   # 过期腰围


def _twin(body=None, labs=None) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    if body:
        t.body_composition = BodyCompositionState(**body)
    if labs:
        t.labs = LabsContext(**labs)
    return t


def test_normal_weight_central_obesity_counted():
    # 新鲜腰围超标(flag=True)但 BMI 正常 → 必须计(BMI≥28 代理会漏诊正常体重中心性肥胖)
    r = _metabolic_syndrome_criteria(_twin(body={
        "bmi": 24.0, "central_obesity_flag": True, "waist_to_height_ratio": 0.58,
        "last_waist_measured": _FRESH}))
    assert r["criteria_hit"] == 1
    assert any("中心性肥胖" in f or "腰围" in f for f in r["factors"])


def test_muscular_high_bmi_fresh_normal_waist_not_counted():
    # BMI≥28 但新鲜腰围正常(flag=False)→ 不再被 BMI 误判为中心性肥胖
    r = _metabolic_syndrome_criteria(_twin(body={
        "bmi": 29.0, "central_obesity_flag": False, "waist_to_height_ratio": 0.45,
        "last_waist_measured": _FRESH}))
    assert r["criteria_hit"] == 0


def test_no_waist_data_falls_back_to_bmi():
    # 无腰围(flag=None)+ BMI≥28 → 退回 BMI 代理,不丢信号
    r = _metabolic_syndrome_criteria(_twin(body={"bmi": 29.0, "central_obesity_flag": None}))
    assert r["criteria_hit"] == 1
    assert any("BMI" in f for f in r["factors"])


def test_no_waist_bmi_normal_no_hit():
    r = _metabolic_syndrome_criteria(_twin(body={"bmi": 24.0, "central_obesity_flag": None}))
    assert r["criteria_hit"] == 0


def test_syndrome_reached_via_fresh_waist_when_bmi_would_miss():
    # 正常 BMI + 新鲜腰围超标 + TG高 + HDL低 → 3 项 → 代谢综合征(BMI 路径会漏诊)
    r = _metabolic_syndrome_criteria(_twin(
        body={"bmi": 25.0, "central_obesity_flag": True, "last_waist_measured": _FRESH},
        labs={"triglycerides": 2.0, "hdl": 0.9}))
    assert r["criteria_hit"] == 3 and r["is_metabolic_syndrome"]


def test_false_syndrome_avoided_when_fresh_waist_normal():
    # BMI≥28(旧代理会计)但新鲜腰围正常 + TG高 + HDL低 → 中心性肥胖不计 → 2 项 → 非综合征(去伪阳)
    r = _metabolic_syndrome_criteria(_twin(
        body={"bmi": 28.5, "central_obesity_flag": False, "last_waist_measured": _FRESH},
        labs={"triglycerides": 2.0, "hdl": 0.9}))
    assert r["criteria_hit"] == 2 and not r["is_metabolic_syndrome"]


# ── 对抗评审 BLOCKING:stale 腰围不得抹掉当前 BMI 风险 ──


def test_stale_normal_waist_does_not_suppress_bmi_hit():
    # 陈年正常腰围(flag=False 但 400 天前)+ 当前 BMI≥28 → 必须退回 BMI 计中(防 under-alarm)
    r = _metabolic_syndrome_criteria(_twin(body={
        "bmi": 30.0, "central_obesity_flag": False, "last_waist_measured": _STALE}))
    assert r["criteria_hit"] == 1
    assert any("BMI" in f and "过期" in f for f in r["factors"])


def test_stale_normal_waist_syndrome_preserved():
    # 完整 under-alarm 场景:BMI30 + 陈年正常腰围 + TG高 + HDL低 → 仍 3 项 → 综合征不被静默抹掉
    r = _metabolic_syndrome_criteria(_twin(
        body={"bmi": 30.0, "central_obesity_flag": False, "last_waist_measured": _STALE},
        labs={"triglycerides": 2.0, "hdl": 0.9}))
    assert r["criteria_hit"] == 3 and r["is_metabolic_syndrome"]


def test_stale_true_waist_not_trusted_falls_back_to_bmi():
    # 陈年腰围超标(flag=True 但过期)+ 当前 BMI 正常 → 不信陈年 True,退回 BMI(正常→不计)
    r = _metabolic_syndrome_criteria(_twin(body={
        "bmi": 24.0, "central_obesity_flag": True, "last_waist_measured": _STALE}))
    assert r["criteria_hit"] == 0


def test_other_criteria_unchanged_regression():
    r = _metabolic_syndrome_criteria(_twin(
        body={"central_obesity_flag": None},
        labs={"triglycerides": 2.0, "hdl": 0.9, "blood_pressure_systolic": 135, "blood_glucose": 6.0}))
    assert r["criteria_hit"] == 4


def test_empty_body_no_crash():
    r = _metabolic_syndrome_criteria(_twin())
    assert r["criteria_hit"] == 0 and not r["is_metabolic_syndrome"]
