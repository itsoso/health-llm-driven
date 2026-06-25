"""labs.uric_acid_high —— 高尿酸血症安全规则(痛风/代谢/心血管风险)。

阈值 420 μmol/L(中国指南性别中立);自动判别 mg/dL vs μmol/L;非急症最高 MEDIUM 不 CRITICAL;
R4 非处方;化验已标异常的临界值(≥360)给 LOW;并与 catch-all 去重(不双报)。
"""
from datetime import datetime

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.rules.labs import uric_acid_high
from app.agents.safety_guardian.schema import Severity
from app.twin.schema import HealthTwin, LabsContext, TwinMeta


def _twin(uric_acid=None, flagged=None) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.labs = LabsContext(uric_acid=uric_acid, flagged_abnormal=flagged or [])
    return t


def test_hyperuricemia_umol_medium():
    a = uric_acid_high(_twin(uric_acid=480.0))
    assert a is not None and a.severity == Severity.MEDIUM
    assert a.rule_id == "labs.uric_acid_high" and "高尿酸血症" in a.title


def test_unit_autodetect_mgdl():
    # 8.0 mg/dL(<50)→ ×59.48 ≈476 μmol/L ≥420 → MEDIUM
    a = uric_acid_high(_twin(uric_acid=8.0))
    assert a is not None and a.severity == Severity.MEDIUM
    assert "476" in a.message or "475" in a.message  # 换算后 μmol/L


def test_markedly_elevated_still_medium_not_critical():
    a = uric_acid_high(_twin(uric_acid=560.0))
    assert a.severity == Severity.MEDIUM and "显著升高" in a.title


def test_extreme_value_never_critical():
    # 过度告警守门:即便极高也只 MEDIUM(无症状高尿酸非急症)
    a = uric_acid_high(_twin(uric_acid=900.0))
    assert a.severity == Severity.MEDIUM
    assert a.severity < Severity.CRITICAL


def test_normal_no_alert():
    assert uric_acid_high(_twin(uric_acid=400.0)) is None   # <420 且未标异常
    assert uric_acid_high(_twin(uric_acid=6.5)) is None      # ≈386 μmol/L


def test_borderline_low_only_when_flagged():
    # 直接字段 380 未标异常 → 不报;同值但化验已标异常 → LOW 临界
    assert uric_acid_high(_twin(uric_acid=380.0)) is None
    a = uric_acid_high(_twin(flagged=[{"item_name": "尿酸", "value": 380}]))
    assert a is not None and a.severity == Severity.LOW and "临界" in a.title


def test_reads_from_flagged_abnormal():
    a = uric_acid_high(_twin(flagged=[{"item_name": "血尿酸", "value": 500}]))
    assert a is not None and a.severity == Severity.MEDIUM


def test_none_and_zero_safe():
    assert uric_acid_high(_twin()) is None
    assert uric_acid_high(_twin(uric_acid=0.0)) is None


def test_action_is_non_prescriptive_r4():
    a = uric_acid_high(_twin(uric_acid=500.0))
    # 不得出具体降尿酸药名 + 剂量(R4);用药须交医生
    for drug in ["别嘌醇", "非布司他", "allopurinol", "febuxostat", "苯溴马隆"]:
        assert drug not in a.action
    assert "医生" in a.action


def test_registered_and_fires_via_engine():
    report = evaluate_safety(_twin(uric_acid=480.0))
    assert any(al.rule_id == "labs.uric_acid_high" for al in report.alerts)


def test_dedup_not_double_reported_in_catchall():
    # 尿酸已被 uric_acid_high 覆盖(≥420 触发)→ 唯一异常时 catch-all 不再把它列成「未分类」
    report = evaluate_safety(_twin(flagged=[{"item_name": "尿酸", "value": 520}]))
    assert any(al.rule_id == "labs.uric_acid_high" for al in report.alerts)
    assert not any(al.rule_id == "labs.uncategorized_abnormal" for al in report.alerts)


# ── 评审 BLOCKING 修复:值感知去重,规则不触发的 flagged 尿酸不得静默丢 ──


def test_subthreshold_flagged_uric_acid_surfaces_in_catchall():
    # 化验标了异常但 <360(规则不触发)→ 必须落兜底,不能零告警(under-alarm)
    report = evaluate_safety(_twin(flagged=[{"item_name": "尿酸", "value": 350}]))
    assert not any(al.rule_id == "labs.uric_acid_high" for al in report.alerts)
    assert any(al.rule_id == "labs.uncategorized_abnormal" for al in report.alerts)


def test_hypouricemia_flagged_surfaces_in_catchall():
    # 低尿酸(Fanconi/肝病等关联)被化验标异常 → 规则不触发,但必须落兜底不消失
    report = evaluate_safety(_twin(flagged=[{"item_name": "尿酸", "value": 80}]))
    assert not any(al.rule_id == "labs.uric_acid_high" for al in report.alerts)
    assert any(al.rule_id == "labs.uncategorized_abnormal" for al in report.alerts)


def test_unit_garbage_value_no_false_alarm():
    # 49(对 mg/dL 太高、对 μmol/L 太低=疑数据错)→ 保守当 μmol/L 49 → 不假告警
    assert uric_acid_high(_twin(uric_acid=49.0)) is None


def test_urea_not_suppressed_by_uric_dedup():
    # 尿素(BUN)含「尿」但非「尿酸」→ uric 规则不碰、去重不误吞 → 落兜底
    report = evaluate_safety(_twin(flagged=[{"item_name": "尿素", "value": 15}]))
    assert not any(al.rule_id == "labs.uric_acid_high" for al in report.alerts)
    assert any(al.rule_id == "labs.uncategorized_abnormal" for al in report.alerts)
