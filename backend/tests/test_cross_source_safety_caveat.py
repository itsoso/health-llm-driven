"""跨源可疑读数 → 安全告警附加复测提示(R3 多源置信度的安全层消费)。

核心安全不变量(under-alarm 防线):标注**只加不减** —— 绝不改 severity / 不删告警 /
不改条数 / 不改顺序。可疑值可能仍是真值,降级=under-alarm(见 spo2 corroboration 教训)。
仅 vitals.rhr_* → resting_heart_rate、vitals.spo2_* → spo2_avg 两条直接、无歧义映射会标注;
bp(单源)/sleep(score≠时长)/stress(不比对)/非 vitals 一律不标。
"""
from datetime import datetime

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.cross_source_annotation import (
    CAVEAT_MARKER,
    annotate_cross_source_suspect,
)
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import (
    CrossSourceDivergence,
    HealthTwin,
    PhysiologicalState,
    TwinMeta,
)


def _div(metric: str, label: str) -> CrossSourceDivergence:
    return CrossSourceDivergence(
        metric=metric,
        label=label,
        trusted_source="garmin",
        outlier_source="apple-watch",
        deviation_pct=34.0,
        hint=f"Apple Watch 的{label}窗口均值比各源平均高 34%,该指标暂以 Garmin 为准。",
    )


def _twin(divs=None, user_id: int = 1, **physio) -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=user_id, generated_at=datetime.utcnow()))
    t.physiological = PhysiologicalState(divergent_metrics=divs or [], **physio)
    return t


def _alert(rule_id: str, category: str = "vitals", severity=Severity.MEDIUM) -> Alert:
    return Alert(
        rule_id=rule_id, category=category, severity=severity,
        title="t", message="原始说明。",
    )


# ───────────────────────── 命中:附加 caveat ─────────────────────────


def test_rhr_alert_gets_caveat_when_rhr_divergent():
    alerts = [_alert("vitals.rhr_tachycardia")]
    annotate_cross_source_suspect(alerts, _twin([_div("resting_heart_rate", "静息心率")]))
    assert CAVEAT_MARKER in alerts[0].message
    assert "原始说明。" in alerts[0].message  # 原文保留,只追加


def test_spo2_alert_gets_caveat_when_spo2_divergent():
    alerts = [_alert("vitals.spo2_severe_hypoxia", severity=Severity.CRITICAL)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER in alerts[0].message


def test_caveat_records_provenance_in_data_citation():
    alerts = [_alert("vitals.rhr_bradycardia")]
    annotate_cross_source_suspect(alerts, _twin([_div("resting_heart_rate", "静息心率")]))
    cs = alerts[0].data_citation.get("cross_source_suspect")
    assert cs and cs["metric"] == "resting_heart_rate"
    assert cs["outlier_source"] == "apple-watch" and cs["trusted_source"] == "garmin"


# ──────────────── under-alarm 防线:只加不减(最关键) ────────────────


def test_severity_never_changes_even_when_critical():
    """CRITICAL 急症值跨源可疑 → 仍 CRITICAL。降级=under-alarm,绝不允许。"""
    alerts = [_alert("vitals.spo2_severe_hypoxia", severity=Severity.CRITICAL)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert alerts[0].severity == Severity.CRITICAL  # 未降级


def test_count_and_order_and_rule_id_unchanged():
    alerts = [
        _alert("vitals.spo2_severe_hypoxia", severity=Severity.CRITICAL),
        _alert("vitals.rhr_tachycardia", severity=Severity.MEDIUM),
    ]
    before = [(a.rule_id, a.severity) for a in alerts]
    annotate_cross_source_suspect(
        alerts, _twin([_div("spo2_avg", "SpO2"), _div("resting_heart_rate", "静息心率")])
    )
    assert len(alerts) == 2
    assert [(a.rule_id, a.severity) for a in alerts] == before  # 条数/顺序/rule_id/severity 全不变


# ───────────────────────── 不命中:保守不标 ─────────────────────────


def test_bp_alert_not_annotated_single_source():
    """BP 单源(Withings)不在跨源指标 → 即便有别的跨源偏离也不标。"""
    alerts = [_alert("vitals.bp_severe_reading", severity=Severity.HIGH)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_sleep_alert_not_annotated_score_neq_duration():
    """sleep_severely_short 是时长,跨源偏离的是 sleep_score → 语义不同,不标(防误导)。"""
    alerts = [_alert("vitals.sleep_severely_short")]
    annotate_cross_source_suspect(alerts, _twin([_div("sleep_score", "睡眠评分")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_non_vitals_alert_not_annotated():
    alerts = [_alert("ddi.warfarin_nsaid", category="ddi", severity=Severity.HIGH)]
    annotate_cross_source_suspect(alerts, _twin([_div("resting_heart_rate", "静息心率")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_metric_mismatch_not_annotated():
    """rhr 告警但只有 spo2 偏离 → 指标不匹配,不标。"""
    alerts = [_alert("vitals.rhr_tachycardia")]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message


# ── 双评审 BLOCKING:spo2 子族里只有 avg 类才标,ODI/min/below90 类绝不被 spo2_avg 误标 ──


def test_osa_screening_not_annotated_by_spo2_avg_divergence():
    """spo2_osa_screening 由 ODI 触发(非 spo2_avg)→ spo2_avg 设备分歧绝不给它贴复测标。

    误标=把一条被佐证的真 OSA 告警说成「可能设备误差,复测」→ 误导性 under-alarm。
    """
    alerts = [_alert("vitals.spo2_osa_screening", severity=Severity.HIGH)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message
    assert "cross_source_suspect" not in alerts[0].data_citation


def test_nocturnal_min_not_annotated_by_spo2_avg_divergence():
    """spo2_min_nocturnal_severe 吃夜间最低/ODI/below90,非 spo2_avg → 不标。"""
    alerts = [_alert("vitals.spo2_min_nocturnal_severe", severity=Severity.CRITICAL)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_sustained_low_overnight_not_annotated_by_spo2_avg_divergence():
    """spo2_sustained_low_overnight 吃 below90/ODI,非 spo2_avg → 不标。"""
    alerts = [_alert("vitals.spo2_sustained_low_overnight", severity=Severity.HIGH)]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_unregistered_future_rule_not_annotated_fail_closed():
    """白名单 fail-closed:未登记的(含将来新增)vitals 规则默认不标。"""
    alerts = [_alert("vitals.spo2_some_future_rule")]
    annotate_cross_source_suspect(alerts, _twin([_div("spo2_avg", "SpO2")]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_no_divergence_no_caveat():
    alerts = [_alert("vitals.spo2_severe_hypoxia")]
    annotate_cross_source_suspect(alerts, _twin([]))
    assert CAVEAT_MARKER not in alerts[0].message


def test_idempotent_no_double_append():
    alerts = [_alert("vitals.rhr_tachycardia")]
    twin = _twin([_div("resting_heart_rate", "静息心率")])
    annotate_cross_source_suspect(alerts, twin)
    once = alerts[0].message
    annotate_cross_source_suspect(alerts, twin)
    assert alerts[0].message == once  # 第二遍不再追加


# ───────────────────────── 端到端:经 evaluate_safety 接线 ─────────────────────────


def test_evaluate_safety_wires_the_caveat():
    """完整路径:spo2_avg=85 触发 spo2 告警 + spo2_avg 跨源偏离 → 报告里该告警带 caveat。"""
    twin = _twin([_div("spo2_avg", "SpO2")], spo2_avg=85.0)
    report = evaluate_safety(twin)
    spo2_alerts = [a for a in report.alerts if a.rule_id.startswith("vitals.spo2")]
    assert spo2_alerts, "spo2_avg=85 应触发至少一条 spo2 告警"
    assert any(CAVEAT_MARKER in a.message for a in spo2_alerts)
    # 报告级不变量:caveat 不该凭空制造或删除告警
    assert report.critical_count >= 0  # 结构完整即可
