"""
Safety Guardian 单元测试。

策略：构造合成 Twin（不依赖数据库），给每个规则类别至少一条正例 + 一条反例。
"""

from datetime import date, datetime
from typing import List

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.engine import registry
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import (
    BehavioralState,
    GeneticContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    PhysiologicalState,
    SupplementState,
    TwinMeta,
)


def _empty_twin(user_id: int = 1) -> HealthTwin:
    return HealthTwin(
        meta=TwinMeta(user_id=user_id, generated_at=datetime.utcnow())
    )


def _rule_ids(alerts: List[Alert]) -> set:
    return {a.rule_id for a in alerts}


# ─────────────────────── Registry basics ──────────────────


class TestRegistry:
    def test_all_rules_loaded(self):
        rules = list(registry.all_rules())
        assert len(rules) >= 30, f"只有 {len(rules)} 条规则，少于预期"
        # 各类别都应该有
        categories = set()
        for name, _ in rules:
            if "." in name:
                categories.add(name.split(".")[0])
        # rule 函数名约定是 category_rest（在 fn.__name__ 里）
        # 验证 6 大类别都有规则（通过模块路径）
        module_paths = set()
        for name, fn in rules:
            module_paths.add(fn.__module__.split(".")[-1])
        assert "vitals" in module_paths
        assert "labs" in module_paths
        assert "ddi" in module_paths
        assert "dsi" in module_paths
        assert "pgx" in module_paths
        assert "training_load" in module_paths


class TestEmptyTwinSafe:
    def test_empty_twin_no_alerts(self):
        twin = _empty_twin()
        report = evaluate_safety(twin)
        # 空 Twin 不应该触发任何告警
        assert len(report.alerts) == 0
        assert report.total_rules_evaluated > 0
        assert report.evaluate_ms >= 0


class TestProblemRedLines:
    """个性化红线:用户登记的 HealthProblem.red_lines 命中症状即升级。"""

    def _twin_with_redline(self, condition, action, symptoms, risk="P1"):
        from app.twin.schema import ProblemRedLine
        twin = _empty_twin()
        twin.acute.problem_red_lines = [
            ProblemRedLine(problem_name="胃溃疡(Hp 阴性)", condition=condition,
                           action=action, risk_level=risk)
        ]
        twin.acute.symptom_texts_all = symptoms
        return twin

    def test_redline_hit_escalates_critical(self):
        twin = self._twin_with_redline("黑便/呕血", "立即就医/急诊", ["今早拉了黑便,有点担心"])
        report = evaluate_safety(twin)
        hit = next(a for a in report.alerts
                   if a.rule_id == "problem_red_lines.health_problem_red_line")
        assert hit.severity == Severity.CRITICAL
        assert hit.requires_medical_attention is True
        assert hit.action == "立即就医/急诊"
        assert hit.data_citation["matched"] == "黑便"

    def test_redline_no_symptom_no_alert(self):
        # 红线在 Twin 里但无匹配症状 → 不告警(不凭空升级)
        twin = self._twin_with_redline("黑便/呕血", "立即就医/急诊", ["轻微口渴"])
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "problem_red_lines.health_problem_red_line" not in ids

    def test_redline_p2_is_high_not_critical(self):
        twin = self._twin_with_redline("无诱因体重骤降", "消化内科评估",
                                       ["最近无诱因体重骤降明显"], risk="P2")
        hit = next(a for a in evaluate_safety(twin).alerts
                   if a.rule_id == "problem_red_lines.health_problem_red_line")
        assert hit.severity == Severity.HIGH

    def test_empty_redlines_silent(self):
        # 没有任何红线 → 规则静默(不报错)
        twin = _empty_twin()
        twin.acute.symptom_texts_all = ["黑便"]
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "problem_red_lines.health_problem_red_line" not in ids

    def test_negation_still_hits_by_design(self):
        # 否定语境(「没有呕血」)仍命中 —— 这是有意偏严,不是 bug。
        # 钉住此行为,免得日后有人当 bug 改成漏判。
        twin = self._twin_with_redline("黑便/呕血", "立即就医/急诊", ["这两天没有呕血"])
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "problem_red_lines.health_problem_red_line" in ids


# ─────────────────────── Vitals rules ─────────────────────


class TestVitalsRules:
    def test_bp_severe_reading_requires_recheck_and_symptom_triage(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=185, blood_pressure_diastolic=125)
        report = evaluate_safety(twin)
        rule_ids = _rule_ids(report.alerts)
        assert "vitals.bp_severe_reading" in rule_ids
        severe = next(a for a in report.alerts if a.rule_id == "vitals.bp_severe_reading")
        assert severe.severity == Severity.HIGH
        assert severe.requires_medical_attention is True
        assert "复测" in severe.action
        assert "胸痛" in severe.action
        assert "高血压急症" not in severe.title + severe.message
        assert "vitals.bp_stage_2_hypertension" not in rule_ids

    def test_bp_stage_2(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=155, blood_pressure_diastolic=95)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.bp_stage_2_hypertension" in rule_ids
        assert "vitals.bp_severe_reading" not in rule_ids

    def test_bp_normal_no_alert(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=118, blood_pressure_diastolic=76)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.bp_severe_reading" not in rule_ids
        assert "vitals.bp_stage_2_hypertension" not in rule_ids
        assert "vitals.bp_hypotension" not in rule_ids

    def test_spo2_critical(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=85.0)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.spo2_severe_hypoxia" in rule_ids

    def test_spo2_multisource_worst_value_still_alerts(self):
        """端到端:戒指(优先源) spo2 正常 + 手表低 → 合并取最差 → 严重低氧告警仍触发,
        不被优先源的正常读数掩盖(安全回归:防 worst-value masking)。"""
        from app.services.device_source_priority import merge_daily_by_priority

        rows = [
            {"data_source": "ringconn", "spo2_avg": 97.0},
            {"data_source": "apple-watch", "spo2_avg": 85.0},
        ]
        merged = merge_daily_by_priority(rows, ["spo2_avg"])
        assert merged["spo2_avg"] == 85.0  # 取最差
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=merged["spo2_avg"])
        rule_ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "vitals.spo2_severe_hypoxia" in rule_ids

    def test_spo2_min_nocturnal_severe_critical(self):
        """min < 80% + 持续负荷佐证 (ODI/below90) → CRITICAL，独立于 avg。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=92.0, spo2_min_overnight=74, spo2_odi=12.0, spo2_below_90_pct=6.0
        )
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.CRITICAL
        assert found.requires_medical_attention is True

    def test_spo2_min_nocturnal_high(self):
        """85 <= min < 88 + 持续负荷佐证 → HIGH。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=94.0, spo2_min_overnight=86, spo2_odi=7.0
        )
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.HIGH

    def test_spo2_min_low_no_corroboration_downgrades_to_info(self):
        """单点低值但无逐秒佐证 (ODI/below90 全 None) → 不拉 CRITICAL,降级 INFO。

        对抗用例:回退到旧版"只看 spo2_min_overnight"会让这里仍判 CRITICAL → 红。
        复现锚点用户 Apple Watch/RingConn 96% 但日聚合 min 伪低触发的误报场景。
        """
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=96.0, spo2_min_overnight=74)
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.INFO
        assert found.requires_medical_attention is False

    def test_spo2_min_low_corroborated_benign_is_artifact_info(self):
        """单点低值 + 逐秒佐证显示整夜负荷可忽略 (ODI<5 且 below90<1%) → 判伪影,INFO。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=96.0, spo2_min_overnight=82, spo2_odi=1.0, spo2_below_90_pct=0.2
        )
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.INFO
        assert found.requires_medical_attention is False

    def test_spo2_min_low_corroborated_burden_below90_keeps_critical(self):
        """below90% 单独达标 (>=1%) 也算持续负荷 → 保持 CRITICAL。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=91.0, spo2_min_overnight=78, spo2_below_90_pct=3.5
        )
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.CRITICAL

    def test_spo2_min_odi_exactly_threshold_keeps_severity(self):
        """边界:ODI 恰好 == 5.0 应算持续负荷(>=),钉住 `>` 误改会静默放过真 OSA。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=92.0, spo2_min_overnight=86, spo2_odi=5.0)
        found = next((a for a in evaluate_safety(twin).alerts
                      if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.HIGH

    def test_spo2_min_below90_exactly_threshold_keeps_severity(self):
        """边界:below_90_pct 恰好 == 1.0 应算持续负荷(>=)。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=90.0, spo2_min_overnight=78, spo2_below_90_pct=1.0
        )
        found = next((a for a in evaluate_safety(twin).alerts
                      if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.CRITICAL

    def test_spo2_min_exactly_88_no_alert(self):
        """边界:min 恰好 == 88 是 tier 下沿,`< 88` 应不触发任何分支。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            spo2_avg=95.0, spo2_min_overnight=88, spo2_odi=20.0, spo2_below_90_pct=10.0
        )
        rule_ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "vitals.spo2_min_nocturnal_severe" not in rule_ids

    def test_spo2_min_above_threshold_no_alert(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=95.0, spo2_min_overnight=90)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.spo2_min_nocturnal_severe" not in rule_ids

    def test_spo2_min_none_no_alert(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=95.0, spo2_min_overnight=None)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.spo2_min_nocturnal_severe" not in rule_ids

    def test_spo2_osa_screening_odi_above_5(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_odi=8.5)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.spo2_osa_screening" in rule_ids

    def test_spo2_osa_no_alert_odi_below_5(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_odi=3.0)
        alerts = evaluate_safety(twin).alerts
        assert "vitals.spo2_osa_screening" not in _rule_ids(alerts)

    def test_spo2_sustained_low_overnight(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_below_90_pct=15.0)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.spo2_sustained_low_overnight" in rule_ids

    def test_spo2_sustained_low_no_alert(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_below_90_pct=5.0)
        alerts = evaluate_safety(twin).alerts
        assert "vitals.spo2_sustained_low_overnight" not in _rule_ids(alerts)

    def test_tachycardia(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(resting_hr=108)
        alerts = evaluate_safety(twin).alerts
        assert "vitals.rhr_tachycardia" in _rule_ids(alerts)


# ─────────────────────── Cardiac (ECG / AFib) rules ────────────────────────


class TestCardiacRules:
    """Apple Watch ECG 房颤分类 → 筛查信号非诊断告警。"""

    def test_afib_single_high(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            ecg_classification="AtrialFibrillation",
            afib_event_count=1,
            afib_recent=True,
        )
        alerts = evaluate_safety(twin).alerts
        afib = next(a for a in alerts if a.rule_id == "cardiac.ecg_atrial_fibrillation")
        assert afib.severity == Severity.HIGH
        assert afib.requires_medical_attention is True
        # 非诊断 + 就医动作
        assert "不是诊断" in afib.message
        assert "心内科" in (afib.action or "") or "就医" in (afib.action or "")

    def test_afib_classification_without_count_still_alerts(self):
        """分类命中但 afib_event_count 缺失(默认 0) → 仍按 1 次告警 (HIGH)。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            ecg_classification="AtrialFibrillation",
            afib_event_count=0,
        )
        alerts = evaluate_safety(twin).alerts
        afib = next(a for a in alerts if a.rule_id == "cardiac.ecg_atrial_fibrillation")
        assert afib.severity == Severity.HIGH

    def test_afib_recurring_escalates_to_critical(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(
            ecg_classification="AtrialFibrillation",
            afib_event_count=3,
            afib_recent=True,
        )
        alerts = evaluate_safety(twin).alerts
        afib = next(a for a in alerts if a.rule_id == "cardiac.ecg_atrial_fibrillation")
        assert afib.severity == Severity.CRITICAL
        assert "不是诊断" in afib.message  # 升级措辞仍非诊断

    def test_afib_count_only_alerts(self):
        """分类字段缺失但 afib_event_count>=1 → 仍告警 (容错路径)。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(afib_event_count=2)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "cardiac.ecg_atrial_fibrillation" in rule_ids

    def test_sinus_rhythm_no_alert(self):
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(ecg_classification="SinusRhythm")
        rule_ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "cardiac.ecg_atrial_fibrillation" not in rule_ids

    def test_inconclusive_no_alert(self):
        for cls in ("InconclusiveLowHeartRate", "InconclusiveHighHeartRate", "Unrecognized"):
            twin = _empty_twin()
            twin.physiological = PhysiologicalState(ecg_classification=cls)
            rule_ids = _rule_ids(evaluate_safety(twin).alerts)
            assert "cardiac.ecg_atrial_fibrillation" not in rule_ids, cls

    def test_missing_ecg_no_alert(self):
        twin = _empty_twin()
        rule_ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "cardiac.ecg_atrial_fibrillation" not in rule_ids


# ─────────────────────── Lab rules ────────────────────────


class TestLabsRules:
    def test_liver_enzyme_pattern_moderate(self):
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "谷丙转氨酶", "value": 54, "unit": "U/L", "reference_range": "0-40"},
                {"item_name": "谷草转氨酶", "value": 67, "unit": "U/L", "reference_range": "15-40"},
                {"item_name": "谷氨酰转肽酶", "value": 72, "unit": "U/L", "reference_range": "0-60"},
            ]
        )
        alerts = evaluate_safety(twin).alerts
        assert "labs.liver_enzyme_pattern" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "labs.liver_enzyme_pattern")
        # 这些值 max_ratio = 67/40 = 1.675 → MEDIUM
        assert alert.severity == Severity.MEDIUM

    def test_liver_enzyme_severe(self):
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "谷丙转氨酶", "value": 250, "unit": "U/L", "reference_range": "0-40"},
                {"item_name": "谷草转氨酶", "value": 210, "unit": "U/L", "reference_range": "15-40"},
            ]
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "labs.liver_enzyme_pattern")
        # 250/40 = 6.25 → CRITICAL
        assert alert.severity == Severity.CRITICAL
        assert alert.requires_medical_attention is True

    def test_single_liver_enzyme_not_triggered(self):
        """只有一项升高不应触发 pattern 规则。"""
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "谷丙转氨酶", "value": 54, "unit": "U/L"},
            ]
        )
        alerts = evaluate_safety(twin).alerts
        assert "labs.liver_enzyme_pattern" not in _rule_ids(alerts)

    def test_red_cell_elevation_both_high(self):
        """HGB + HCT 同向超(男)上限 → MEDIUM 告警(非诊断、无处方/剂量)。"""
        twin = _empty_twin()
        twin.labs = LabsContext(hemoglobin=173, hematocrit=54)
        alerts = evaluate_safety(twin).alerts
        assert "labs.red_cell_elevation" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "labs.red_cell_elevation")
        assert alert.severity == Severity.MEDIUM
        # R4: 复查/评估框架, 不下诊断、不出药/剂量
        text = (alert.message or "") + (alert.action or "")
        assert "非诊断" in alert.message
        assert "复查" in text and "血液科" in text
        for forbidden in ("确诊", "诊断为", "处方", "mg", "毫克", "剂量"):
            assert forbidden not in text

    def test_red_cell_elevation_only_one_high(self):
        """只有 HGB 高 / 只有 HCT 高 → 不触发(必须两项佐证)。"""
        only_hgb = _empty_twin()
        only_hgb.labs = LabsContext(hemoglobin=173, hematocrit=46)
        assert "labs.red_cell_elevation" not in _rule_ids(evaluate_safety(only_hgb).alerts)

        only_hct = _empty_twin()
        only_hct.labs = LabsContext(hemoglobin=160, hematocrit=54)
        assert "labs.red_cell_elevation" not in _rule_ids(evaluate_safety(only_hct).alerts)

    def test_ldl_high(self):
        twin = _empty_twin()
        twin.labs = LabsContext(ldl=5.0)
        alerts = evaluate_safety(twin).alerts
        assert "labs.ldl_high" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "labs.ldl_high")
        assert alert.severity == Severity.HIGH

    def test_hba1c_diabetes_alert_fires_for_standard_a1c(self):
        """标准糖化 A1c 7.0% 仍应触发糖尿病告警 (回归保护: 修 total-HbA1 误判别误伤本体)。"""
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "糖化血红蛋白A1c", "value": 7.0, "unit": "%",
                 "reference_range": "0-5.7"},
            ]
        )
        alerts = evaluate_safety(twin).alerts
        assert "labs.hba1c_diabetes" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "labs.hba1c_diabetes")
        assert alert.severity == Severity.HIGH

    def test_total_hba1_does_not_trigger_diabetes_false_positive(self):
        """总糖化 HbA1 (糖化血红蛋白A1, 参考 6.3–9.0%) 与标准 A1c 是不同指标。

        7.0% 对总糖化是正常值, 绝不能落进糖尿病/前期阈值 (≥6.5 / ≥5.7) 产生假告警。
        历史 bug: 子串匹配「糖化血红蛋白」吞下「糖化血红蛋白A1」→ 假 HIGH 糖尿病告警。
        """
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "糖化血红蛋白A1", "value": 7.0, "unit": "%",
                 "reference_range": "6.3-9.0"},
            ]
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "labs.hba1c_diabetes" not in ids
        assert "labs.hba1c_prediabetes" not in ids

    def test_hba1c_diabetes_alert_fires_for_english_a1c(self):
        """英文名 "Hemoglobin A1c" (最长子串解析会判成 hemoglobin) 仍须触发糖尿病告警。

        关键字兜底护栏: 不让本规则单点依赖 resolve_code 而漏报真糖尿病。
        """
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "Hemoglobin A1c", "value": 9.2, "unit": "%",
                 "reference_range": "4.0-5.7"},
            ]
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "labs.hba1c_diabetes" in ids

    def test_abnormal_total_hba1_surfaces_as_uncategorized(self):
        """真异常的总糖化 HbA1 不能被「已覆盖」误判而静默丢弃 —— 落到 uncategorized 兜底。"""
        twin = _empty_twin()
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "糖化血红蛋白A1", "value": 10.5, "unit": "%",
                 "reference_range": "6.3-9.0"},
            ]
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "labs.hba1c_diabetes" not in ids
        assert "labs.uncategorized_abnormal" in ids


# ─────────────────────── DDI rules ────────────────────────


class TestDDIRules:
    def test_glp1_with_sulfonylurea(self):
        twin = _empty_twin()
        twin.medication = MedicationState(
            active_meds=[
                {"name": "替尔泊肽"},
                {"name": "格列美脲"},
            ]
        )
        alerts = evaluate_safety(twin).alerts
        ids = _rule_ids(alerts)
        assert "ddi.glp1_hypoglycemia" in ids
        alert = next(a for a in alerts if a.rule_id == "ddi.glp1_hypoglycemia")
        assert alert.severity == Severity.HIGH
        assert alert.requires_medical_attention is True

    def test_glp1_gastric_emptying_info_alone(self):
        """只有 GLP-1 没有其他糖尿病药 → 只有信息性提示。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "替尔泊肽"}])
        alerts = evaluate_safety(twin).alerts
        ids = _rule_ids(alerts)
        assert "ddi.glp1_gastric_emptying" in ids
        assert "ddi.glp1_hypoglycemia" not in ids
        alert = next(a for a in alerts if a.rule_id == "ddi.glp1_gastric_emptying")
        # 不得出现被对抗验证证伪的捏造分钟范围
        assert "30-70" not in alert.message
        # 抗凝建议应是「按医嘱监测 INR」而非时间错开
        assert "INR" in alert.action
        assert "注射日" not in alert.action or "无关" in alert.action
        # 替尔泊肽（GIP/GLP-1）才给避孕屏障法提示
        assert "屏障" in alert.action

    def test_glp1_gastric_emptying_pure_glp1_no_contraceptive_caveat(self):
        """纯 GLP-1（司美格鲁肽）不降低口服避孕药暴露 → 不得带屏障避孕提示。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "司美格鲁肽"}])
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "ddi.glp1_gastric_emptying")
        assert "屏障" not in alert.action
        assert "避孕" not in alert.action
        # 左甲状腺素的同日间隔 + TSH 监测建议对所有 GLP-1 都给
        assert "TSH" in alert.action

    def test_warfarin_nsaid(self):
        twin = _empty_twin()
        twin.medication = MedicationState(
            active_meds=[{"name": "华法林"}, {"name": "布洛芬"}]
        )
        alerts = evaluate_safety(twin).alerts
        assert "ddi.warfarin_bleeding" in _rule_ids(alerts)

    def test_ssri_maoi_critical(self):
        twin = _empty_twin()
        twin.medication = MedicationState(
            active_meds=[{"name": "舍曲林"}, {"name": "苯乙肼"}]
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "ddi.ssri_maoi")
        assert alert.severity == Severity.CRITICAL
        assert alert.requires_medical_attention is True
        # 非氟西汀 SSRI（舍曲林）→ 洗脱期 ≥2 周，不得提到 5 周
        assert "2 周" in alert.message
        assert "5 周" not in alert.message

    def test_ssri_maoi_fluoxetine_five_week_washout(self):
        """氟西汀（长半衰期 + 去甲氟西汀蓄积）与 MAOI → 洗脱期必须按 ≥5 周给，而非 2 周。"""
        twin = _empty_twin()
        twin.medication = MedicationState(
            active_meds=[{"name": "氟西汀"}, {"name": "苯乙肼"}]
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "ddi.ssri_maoi")
        assert alert.severity == Severity.CRITICAL
        # 氟西汀 → 必须提到 5 周洗脱期
        assert "5 周" in alert.message
        # action 仍交回处方医生裁决
        assert "处方医生" in alert.action

    def test_cetirizine_alone_no_alert(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "盐酸西替利嗪片"}])
        alerts = evaluate_safety(twin).alerts
        # 西替利嗪单独使用不该触发任何 DDI
        assert all(not a.rule_id.startswith("ddi.cetirizine") for a in alerts)

    def test_ibuprofen_not_opioid_no_cns_depressant_alert(self):
        # 布洛芬是 NSAID，不是阿片类——西替利嗪 + 布洛芬不该走阿片中枢抑制逻辑。
        # 回归保护：曾误把"布洛芬"列进 opioid 别名表。
        twin = _empty_twin()
        twin.medication = MedicationState(
            active_meds=[{"name": "盐酸西替利嗪片"}, {"name": "布洛芬"}]
        )
        alerts = evaluate_safety(twin).alerts
        cns = [a for a in alerts if a.rule_id == "ddi.cetirizine_cns_depressants"]
        assert cns == []


# ─────────────────────── DSI rules ────────────────────────


class TestDSIRules:
    def test_calcium_iron_together(self):
        twin = _empty_twin()
        twin.supplement = SupplementState(
            active_supplements=[
                {"name": "Calcium Citrate"},
                {"name": "Ferrous Bisglycinate Iron"},
            ],
            total_active_count=2,
        )
        alerts = evaluate_safety(twin).alerts
        assert "dsi.calcium_iron_competition" in _rule_ids(alerts)

    def test_warfarin_vitamin_k(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "华法林"}])
        twin.supplement = SupplementState(
            active_supplements=[{"name": "Vitamin K2 MK-7"}],
            total_active_count=1,
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "dsi.vitamink_warfarin")
        assert alert.severity == Severity.HIGH
        assert alert.requires_medical_attention is True

    def test_glp1_oral_absorption_info(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "替尔泊肽"}])
        twin.supplement = SupplementState(
            active_supplements=[{"name": "Iron Bisglycinate"}, {"name": "Vitamin B12"}],
            total_active_count=2,
        )
        alerts = evaluate_safety(twin).alerts
        assert "dsi.glp1_oral_absorption" in _rule_ids(alerts)


class TestLongTermAcidSuppression:
    """长期抑酸(PPI/P-CAB)× 营养缺乏化验感知规则(dsi)。非处方、确定性、fail-loud。"""

    TODAY = date(2026, 6, 25)

    def _twin_on_ppi(self, start_date):
        twin = _empty_twin()
        med = {"name": "伏诺拉生", "kind": "medication"}
        if start_date is not None:
            med["start_date"] = start_date
        twin.medication = MedicationState(active_meds=[med])
        return twin

    def _pin_today(self, monkeypatch, day=None):
        monkeypatch.setattr(
            "app.agents.safety_guardian.rules.dsi.get_china_today",
            lambda: day or self.TODAY,
        )

    def test_ppi_long_term_low_b12_fires_medium(self, monkeypatch):
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")  # ~12 周 ≥ 8
        twin.labs = LabsContext(
            flagged_abnormal=[
                {"item_name": "维生素B12", "value": 120, "unit": "pmol/L", "reference_range": "180-914"},
            ],
            last_exam_date=date(2026, 6, 20),
        )
        alerts = evaluate_safety(twin).alerts
        assert "dsi.long_term_acid_suppression_lab" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "dsi.long_term_acid_suppression_lab")
        assert alert.severity == Severity.MEDIUM
        assert alert.requires_medical_attention is True
        assert "不是停药建议" in alert.message  # R4 自我声明

    def test_ppi_long_term_no_recent_lab_fires_info(self, monkeypatch):
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(last_exam_date=None)  # 无近期化验
        alerts = evaluate_safety(twin).alerts
        assert "dsi.long_term_acid_suppression_monitor" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "dsi.long_term_acid_suppression_monitor")
        assert alert.severity == Severity.INFO

    def test_ppi_short_term_no_alert(self, monkeypatch):
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-05-28")  # ~4 周 < 8
        twin.labs = LabsContext(last_exam_date=None)
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "dsi.long_term_acid_suppression_lab" not in ids
        assert "dsi.long_term_acid_suppression_monitor" not in ids

    def test_ppi_no_start_date_no_alert(self, monkeypatch):
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi(None)  # 无 start_date → 不臆测时长
        twin.labs = LabsContext(last_exam_date=None)
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "dsi.long_term_acid_suppression_lab" not in ids
        assert "dsi.long_term_acid_suppression_monitor" not in ids

    def test_ppi_recent_labs_no_low_nutrient_no_alert(self, monkeypatch):
        # 长期但近期已查、无相关营养异常 → 不唠叨(避免对已查正常者误推)
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "谷丙转氨酶", "value": 50, "unit": "U/L", "reference_range": "0-40"}],
            last_exam_date=date(2026, 6, 1),  # 近期
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "dsi.long_term_acid_suppression_lab" not in ids
        assert "dsi.long_term_acid_suppression_monitor" not in ids

    def test_ppi_rule_nonprescriptive_adversarial(self, monkeypatch):
        self._pin_today(monkeypatch)
        scenarios = [
            LabsContext(
                flagged_abnormal=[{"item_name": "血清镁", "value": 0.5, "unit": "mmol/L", "reference_range": "0.75-1.02"}],
                last_exam_date=date(2026, 6, 20),
            ),
            LabsContext(last_exam_date=None),
        ]
        for labs in scenarios:
            twin = self._twin_on_ppi("2026-04-01")
            twin.labs = labs
            alerts = [a for a in evaluate_safety(twin).alerts
                      if a.rule_id.startswith("dsi.long_term_acid_suppression")]
            assert alerts, "规则应触发"
            for a in alerts:
                blob = (a.message + " " + (a.action or ""))
                # 禁命令式/处方式表述(允许免责声明里出现"不是停药建议");与 deprescribing
                # test_disclaimer_never_says_stop 同口径:禁的是 imperative,不是 bare substring。
                for banned in ["立即停", "请停药", "应停药", "可以停药", "建议停药", "停掉",
                               "自行停", "自行减", "自行调整", "减量到", "减为", "改成", "换成", "mg"]:
                    assert banned not in blob, f"R4 越界: '{banned}' in {a.rule_id}"

    def test_ppi_rule_coexists_with_another_dsi_rule(self, monkeypatch):
        # 与同类别(dsi)另一条规则正交,可同帧共存(防同类别误抑制)
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.medication = MedicationState(
            active_meds=[{"name": "伏诺拉生", "kind": "medication", "start_date": "2026-04-01"},
                         {"name": "替尔泊肽", "kind": "medication"}]  # GLP-1
        )
        twin.supplement = SupplementState(
            active_supplements=[{"name": "Vitamin B12"}], total_active_count=1
        )
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "维生素B12", "value": 120, "unit": "pmol/L", "reference_range": "180-914"}],
            last_exam_date=date(2026, 6, 20),
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "dsi.long_term_acid_suppression_lab" in ids
        assert "dsi.glp1_oral_absorption" in ids  # 两条 dsi 规则共存

    def test_ppi_rule_uses_china_today_not_date_today(self, monkeypatch):
        # start_date 在「真实今天」(2026-06)是未来→date.today() 算负时长→不触发;
        # 在 mock 京历今天(2027-01-01)是 ~8.7 周→触发。证明规则用 get_china_today。
        self._pin_today(monkeypatch, day=date(2027, 1, 1))
        twin = self._twin_on_ppi("2026-11-01")
        twin.labs = LabsContext(last_exam_date=None)
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert "dsi.long_term_acid_suppression_monitor" in ids, \
            "规则必须用 get_china_today(mock 2027-01-01),而非 date.today()"

    def test_ppi_fullwidth_tilde_range_low_b12_fires_medium(self, monkeypatch):
        # 中国 LIS 报告常用全角波浪号 180～914;旧正则漏 → 真低值静默丢(审评 BLOCKING)
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "维生素B12", "value": 120, "reference_range": "180～914"}],
            last_exam_date=date(2026, 6, 20),
        )
        alerts = evaluate_safety(twin).alerts
        a = next((x for x in alerts if x.rule_id == "dsi.long_term_acid_suppression_lab"), None)
        assert a is not None and a.severity == Severity.MEDIUM
        assert "偏低" in a.message  # 全角范围被正确解析为"确证偏低"

    def test_ppi_unparseable_range_flagged_nutrient_fires_unclear_not_dropped(self, monkeypatch):
        # 方向不可解析的 flagged-abnormal 营养素不能静默当正常 → 兜底 MEDIUM(方向待医生核读)
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "血清镁", "value": 0.5, "reference_range": "参考见报告"}],
            last_exam_date=date(2026, 6, 20),  # 近期(不会落 INFO 分支)
        )
        alerts = evaluate_safety(twin).alerts
        a = next((x for x in alerts if x.rule_id == "dsi.long_term_acid_suppression_lab"), None)
        assert a is not None and a.severity == Severity.MEDIUM
        assert "标记为异常" in a.message  # unclear 措辞,不谎称"偏低"
        assert "偏低" not in a.message

    def test_ppi_transferrin_not_matched_as_ferritin(self, monkeypatch):
        # 转铁蛋白(transferrin)≠ 铁蛋白(ferritin),不得误配
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "转铁蛋白", "value": 1.5, "reference_range": "2.0-3.6"}],
            last_exam_date=date(2026, 6, 20),
        )
        assert "dsi.long_term_acid_suppression_lab" not in _rule_ids(evaluate_safety(twin).alerts)

    def test_ppi_urine_magnesium_not_matched(self, monkeypatch):
        # 尿镁(肾排)≠ 血清镁(缺乏),不得误配
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "尿镁", "value": 1.0, "reference_range": "3.0-5.0"}],
            last_exam_date=date(2026, 6, 20),
        )
        assert "dsi.long_term_acid_suppression_lab" not in _rule_ids(evaluate_safety(twin).alerts)

    def test_ppi_high_ferritin_not_counted_low(self, monkeypatch):
        # flagged-HIGH 铁蛋白不得误判为"低"
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")
        twin.labs = LabsContext(
            flagged_abnormal=[{"item_name": "铁蛋白", "value": 800, "reference_range": "30-400"}],
            last_exam_date=date(2026, 6, 20),
        )
        assert "dsi.long_term_acid_suppression_lab" not in _rule_ids(evaluate_safety(twin).alerts)

    def test_ppi_pcab_caveat_present_for_vonoprazan(self, monkeypatch):
        # 锚点用户在用伏诺拉生(P-CAB)→ message 必带 P-CAB 数据更少的 caveat
        self._pin_today(monkeypatch)
        twin = self._twin_on_ppi("2026-04-01")  # 伏诺拉生
        twin.labs = LabsContext(last_exam_date=None)
        a = next((x for x in evaluate_safety(twin).alerts
                  if x.rule_id == "dsi.long_term_acid_suppression_monitor"), None)
        assert a is not None and "P-CAB" in a.message


# ─────────────────────── PGx rules ────────────────────────


class TestPGxRules:
    def test_cyp2d6_pm_with_codeine(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "可待因"}])
        twin.genetic = GeneticContext(
            has_profile=True,
            total_variants=1,
            drug_sensitivity=[
                {
                    "gene_name": "CYP2D6",
                    "genotype": "*4/*4",
                    "result_label": "poor metabolizer",
                    "risk_level": "中风险",
                }
            ],
        )
        alerts = evaluate_safety(twin).alerts
        assert "pgx.cyp2d6_opioid_pm" in _rule_ids(alerts)

    def test_cyp2d6_um_with_codeine_critical(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "可待因"}])
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {
                    "gene_name": "CYP2D6",
                    "genotype": "*1/*1xN",
                    "result_label": "ultrarapid metabolizer",
                }
            ],
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "pgx.cyp2d6_opioid_um")
        assert alert.severity == Severity.CRITICAL

    def test_g6pd_deficiency_contraindicated(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "伯氨喹"}])
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {
                    "gene_name": "G6PD",
                    "genotype": "c.563C>T",
                    "result_label": "deficiency",
                    "risk_level": "高风险",
                }
            ],
        )
        alerts = evaluate_safety(twin).alerts
        alert = next(a for a in alerts if a.rule_id == "pgx.g6pd_contraindicated")
        assert alert.severity == Severity.CRITICAL

    def test_aldh2_variant(self):
        twin = _empty_twin()
        twin.genetic = GeneticContext(
            has_profile=True,
            risk_variants=[
                {
                    "gene_name": "ALDH2",
                    "genotype": "*1/*2",
                    "result_label": "reduced activity",
                    "risk_level": "中风险",
                }
            ],
        )
        alerts = evaluate_safety(twin).alerts
        assert "pgx.aldh2_alcohol" in _rule_ids(alerts)

    def test_aldh2_references_replaced_and_conclusion_intact(self):
        """Phase 0: 引用换成 IARC + 食管癌精准预防权威源;戒酒结论不软化;CV 关联降级并列。"""
        twin = _empty_twin()
        twin.genetic = GeneticContext(
            has_profile=True,
            risk_variants=[
                {
                    "gene_name": "ALDH2",
                    "genotype": "*1/*2",
                    "result_label": "reduced activity",
                    "risk_level": "中风险",
                }
            ],
        )
        alerts = evaluate_safety(twin).alerts
        aldh2 = next(a for a in alerts if a.rule_id == "pgx.aldh2_alcohol")

        # 旧单篇机制类文献已移除
        assert all("cell-metabolism" not in r and "cell.com" not in r for r in aldh2.references)
        # 换成 IARC (致癌物分类) + 食管癌精准预防权威源
        assert any("iarc" in r.lower() for r in aldh2.references)
        assert any("plosmedicine" in r.lower() for r in aldh2.references)
        # 结论(戒酒最安全)不软化
        assert "完全戒酒" in aldh2.action
        # 食管癌作主要关联,心血管降级为"次要/争议"并列
        assert "食管癌" in aldh2.message
        assert "争议" in aldh2.message
        # 规则严重度不变
        assert aldh2.severity == Severity.MEDIUM

    def _slco1b1_twin(self, genotype, label, drug="辛伐他汀", risk="高风险"):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": drug}])
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {
                    "gene_name": "SLCO1B1",
                    "genotype": genotype,
                    "result_label": label,
                    "risk_level": risk,
                }
            ],
        )
        return twin

    def _slco1b1_alert(self, twin):
        return next(
            a for a in evaluate_safety(twin).alerts
            if a.rule_id == "pgx.slco1b1_simvastatin"
        )

    def test_slco1b1_simvastatin_heterozygous_decreased(self):
        """杂合 T/C（功能降低）→ OR≈1.8，剂量帽 ≤20mg/日 或换药都可。"""
        a = self._slco1b1_alert(self._slco1b1_twin("CT", "decreased function"))
        assert a.severity == Severity.HIGH
        assert a.requires_medical_attention
        # 表型化倍数，且不再出现旧的 "3-5"
        assert "1.8" in a.message
        assert "3-5" not in a.message and "3-5" not in a.action
        # 杂合可走剂量帽
        assert "≤20mg" in a.action

    def test_slco1b1_simvastatin_homozygous_poor_no_dose_cap(self):
        """纯合 C/C（功能差）→ OR≈2.8，CPIC 只换药，不给减量辛伐他汀的后路。"""
        a = self._slco1b1_alert(self._slco1b1_twin("CC", "poor function"))
        assert a.severity == Severity.HIGH
        assert "2.8" in a.message
        # 纯合不得把 "辛伐他汀 ≤20mg/日" 当安全选项
        assert "≤20mg" not in a.action
        assert "替代他汀" in a.action

    def test_slco1b1_simvastatin_star_allele_homozygous_poor(self):
        """星号等位基因 *5/*5 同样判为纯合 poor，不走剂量帽。"""
        a = self._slco1b1_alert(self._slco1b1_twin("*5/*5", "功能降低"))
        assert "2.8" in a.message
        assert "≤20mg" not in a.action

    def test_slco1b1_simvastatin_unknown_zygosity_clinician_determined(self):
        """无法区分纯合/杂合（仅有变异命名）→ 不把 ≤20mg/日当自行可采用的安全选项。"""
        a = self._slco1b1_alert(self._slco1b1_twin("c.521T>C", "功能降低"))
        assert a.severity == Severity.HIGH
        # 两档倍数都给出
        assert "1.8" in a.message and "2.8" in a.message
        # 措辞为「交医生判定」，并明确劝阻自行减量
        assert "请勿自行" in a.action
        assert "医生" in a.action
        assert "3-5" not in a.message and "3-5" not in a.action

    def test_slco1b1_no_simvastatin_no_alert(self):
        """有 SLCO1B1 风险变异但未在服辛伐他汀 → 不触发。"""
        twin = self._slco1b1_twin("CC", "poor function", drug="二甲双胍")
        assert not any(
            a.rule_id == "pgx.slco1b1_simvastatin"
            for a in evaluate_safety(twin).alerts
        )

    def test_pgx_no_variant_no_alert(self):
        """基因缺失时 PGx 规则不触发。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "可待因"}])
        # 没有基因数据
        alerts = evaluate_safety(twin).alerts
        assert not any(a.rule_id.startswith("pgx.cyp2d6") for a in alerts)

    def test_hla_b5701_abacavir_scans_all_hla_b_variants(self):
        """同一 gene 多条 HLA-B 记录时,手写 HLA-B*57:01 规则不能只看第一条。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "阿巴卡韦"}])
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {
                    "gene_name": "HLA-B",
                    "genotype": "*15:02 positive",
                    "result_label": "HLA-B*15:02 阳性",
                    "risk_level": "高风险",
                },
                {
                    "gene_name": "HLA-B",
                    "genotype": "*57:01 positive",
                    "result_label": "HLA-B*57:01 阳性",
                    "risk_level": "高风险",
                },
            ],
        )

        alerts = evaluate_safety(twin).alerts

        assert "pgx.hla_b5701_abacavir" in _rule_ids(alerts)


class TestPGxCpicTable:
    """CPIC Level-A 表驱动规则 (pgx_cpic_table_check)。"""

    def _twin_with(self, gene, genotype, label, drug, pool="drug_sensitivity", risk="高风险"):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": drug}])
        variant = {
            "gene_name": gene,
            "genotype": genotype,
            "result_label": label,
            "risk_level": risk,
        }
        twin.genetic = GeneticContext(has_profile=True, **{pool: [variant]})
        return twin

    def test_tpmt_thiopurine_critical(self):
        twin = self._twin_with("TPMT", "*3A/*3A", "poor metabolizer", "硫唑嘌呤")
        alerts = evaluate_safety(twin).alerts
        a = next(a for a in alerts if a.rule_id.startswith("pgx.cpic.tpmt"))
        assert a.severity == Severity.CRITICAL
        assert a.requires_medical_attention
        assert any("cpicpgx.org" in r for r in a.references)

    def test_rule_id_uses_canonical_drug_keyword_not_display_name(self):
        """同一药物带剂量/商品名时 rule_id 必须稳定,否则解释、去重、静默设置都会漂移。"""
        twin = self._twin_with("TPMT", "*3A/*3A", "poor metabolizer", "硫唑嘌呤片 50mg")
        alerts = evaluate_safety(twin).alerts
        a = next(a for a in alerts if a.rule_id.startswith("pgx.cpic.tpmt"))
        assert a.rule_id == "pgx.cpic.tpmt_硫唑嘌呤"

    def test_nudt15_mercaptopurine(self):
        twin = self._twin_with("NUDT15", "*3/*3", "intermediate metabolizer", "6-巯基嘌呤")
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert any(i.startswith("pgx.cpic.nudt15") for i in ids)

    def test_hla_b1502_carbamazepine_critical(self):
        twin = self._twin_with(
            "HLA-B", "*15:02 positive", "HLA-B*15:02 阳性", "卡马西平"
        )
        a = next(
            x for x in evaluate_safety(twin).alerts
            if x.rule_id.startswith("pgx.cpic.hla-b")
        )
        assert a.severity == Severity.CRITICAL

    def test_hla_b1502_carbamazepine_scans_all_hla_b_variants(self):
        """同一 gene 多条 HLA-B 记录时,CPIC 表驱动规则不能只看第一条。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "卡马西平"}])
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {
                    "gene_name": "HLA-B",
                    "genotype": "*57:01 positive",
                    "result_label": "HLA-B*57:01 阳性",
                    "risk_level": "高风险",
                },
                {
                    "gene_name": "HLA-B",
                    "genotype": "*15:02 positive",
                    "result_label": "HLA-B*15:02 阳性",
                    "risk_level": "高风险",
                },
            ],
        )

        a = next(
            x for x in evaluate_safety(twin).alerts
            if x.rule_id.startswith("pgx.cpic.hla-b")
        )

        assert a.severity == Severity.CRITICAL

    def test_hla_b5801_allopurinol(self):
        twin = self._twin_with("HLA-B", "*58:01 positive", "阳性", "别嘌醇")
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert any("hla-b" in i and "别嘌醇" in i for i in ids)

    def test_cyp3a5_tacrolimus_expresser(self):
        twin = self._twin_with("CYP3A5", "*1/*3", "expresser", "他克莫司")
        ids = _rule_ids(evaluate_safety(twin).alerts)
        assert any(i.startswith("pgx.cpic.cyp3a5") for i in ids)

    def test_cyp3a5_nonexpresser_no_alert(self):
        """阻断-1 回归：non-expresser (*3/*3) 是非表达者，方向与 expresser 相反，
        绝不能误报"他克莫司需加量"(会致他克莫司中毒)；而 *1/*1 expresser 应报。"""
        # non-expresser → exclude 命中 → 不报
        twin_ne = self._twin_with("CYP3A5", "*3/*3", "non-expresser", "他克莫司")
        assert not any(
            a.rule_id.startswith("pgx.cpic.cyp3a5")
            for a in evaluate_safety(twin_ne).alerts
        )
        # expresser *1/*1 → 报
        twin_e = self._twin_with("CYP3A5", "*1/*1", "expresser", "他克莫司")
        assert any(
            a.rule_id.startswith("pgx.cpic.cyp3a5")
            for a in evaluate_safety(twin_e).alerts
        )

    def test_ryr1_anesthetic_critical(self):
        twin = self._twin_with(
            "RYR1", "c.7300G>A", "malignant hyperthermia susceptibility", "七氟烷",
            pool="risk_variants",
        )
        a = next(
            x for x in evaluate_safety(twin).alerts
            if x.rule_id.startswith("pgx.cpic.ryr1")
        )
        assert a.severity == Severity.CRITICAL

    def test_ryr1_negative_no_alert(self):
        """阻断-2 回归："no MH risk detected" / "low risk" 是阴性，绝不能误触发
        CRITICAL 恶性高热告警；而 "MH susceptible" 应报。"""
        # 阴性 → exclude 命中 → 不报
        twin_neg = self._twin_with(
            "RYR1", "wild-type", "no MH risk detected", "七氟烷",
            pool="risk_variants",
        )
        assert not any(
            a.rule_id.startswith("pgx.cpic.ryr1")
            for a in evaluate_safety(twin_neg).alerts
        )
        # 易感 → 报
        twin_pos = self._twin_with(
            "RYR1", "c.7300G>A", "MH susceptible", "七氟烷",
            pool="risk_variants",
        )
        assert any(
            a.rule_id.startswith("pgx.cpic.ryr1")
            for a in evaluate_safety(twin_pos).alerts
        )

    def test_ryr1_chinese_negative_phrasings_no_alert(self):
        """阻断收尾：中文报告非连续否定写法 "未检出致病变异" 是阴性 MH 报告，
        绝不能被 phenotype 子串 "致病" 命中而误报 CRITICAL 恶性高热（患者即将麻醉）。"""
        twin_neg = self._twin_with(
            "RYR1", "wild-type", "未检出致病变异", "七氟烷",
            pool="risk_variants",
        )
        assert not any(
            a.rule_id.startswith("pgx.cpic.ryr1")
            for a in evaluate_safety(twin_neg).alerts
        )

    def test_cacna1s_chinese_negative_phrasing_no_alert(self):
        """同形防漂移：CACNA1S 阴性写法 "未见致病性变异" 同样不能误报。"""
        twin_neg = self._twin_with(
            "CACNA1S", "wild-type", "未见致病性变异", "七氟烷",
            pool="risk_variants",
        )
        assert not any(
            a.rule_id.startswith("pgx.cpic.cacna1s")
            for a in evaluate_safety(twin_neg).alerts
        )

    def test_ryr1_chinese_positive_still_alerts(self):
        """避免误杀：真阳性中文写法 "恶性高热易感（致病变异）" 仍必须报 CRITICAL。"""
        twin_pos = self._twin_with(
            "RYR1", "c.7300G>A", "恶性高热易感（致病变异）", "七氟烷",
            pool="risk_variants",
        )
        a = next(
            x for x in evaluate_safety(twin_pos).alerts
            if x.rule_id.startswith("pgx.cpic.ryr1")
        )
        assert a.severity == Severity.CRITICAL

    def test_no_drug_no_alert(self):
        """有变异但没在用相关药 → 不报。"""
        twin = _empty_twin()
        twin.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[{
                "gene_name": "TPMT",
                "genotype": "*3A/*3A",
                "result_label": "poor metabolizer",
                "risk_level": "高风险",
            }],
        )
        # 没有任何药物
        assert not any(
            a.rule_id.startswith("pgx.cpic") for a in evaluate_safety(twin).alerts
        )

    def test_ambiguous_phenotype_no_alert(self):
        """phenotype 标签不明确（关键词没命中）→ 保守不报。"""
        twin = self._twin_with(
            "TPMT", "未知", "normal metabolizer", "硫唑嘌呤", risk="低风险"
        )
        assert not any(
            a.rule_id.startswith("pgx.cpic.tpmt") for a in evaluate_safety(twin).alerts
        )

    def test_no_double_report_with_handwritten(self):
        """CYP2D6 × 可待因已有手写规则 → 表驱动不重复出 CPIC 告警。"""
        twin = self._twin_with(
            "CYP2D6", "*4/*4", "poor metabolizer", "可待因"
        )
        ids = _rule_ids(evaluate_safety(twin).alerts)
        # 手写规则照常触发
        assert "pgx.cyp2d6_opioid_pm" in ids
        # 表驱动不应对可待因再出 CPIC 告警
        assert not any(i.startswith("pgx.cpic.cyp2d6") and "可待因" in i for i in ids)

    def test_action_is_medical_oriented(self):
        """所有表驱动 action 都是就医导向, 绝不含'自行停药'。"""
        twin = self._twin_with("TPMT", "*3A/*3A", "poor metabolizer", "硫唑嘌呤")
        a = next(
            x for x in evaluate_safety(twin).alerts
            if x.rule_id.startswith("pgx.cpic.tpmt")
        )
        assert "自行" not in a.action or "切勿自行" in a.action or "不要自行" in a.action


# ─────────────────────── Training load ────────────────────


class TestTrainingLoad:
    def test_acwr_overload(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            acute_chronic_ratio=1.8,
            acwr_reliable=True,
            training_load_7d=180,
            workouts_this_week=6,
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.acwr_overload" in _rule_ids(alerts)

    def test_acwr_optimal_no_alert(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            acute_chronic_ratio=1.1,
            acwr_reliable=True,
            training_load_7d=110,
            workouts_this_week=4,
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.acwr_overload" not in _rule_ids(alerts)
        assert "training.acwr_undertraining" not in _rule_ids(alerts)

    def test_acwr_overload_ignored_when_acute_load_is_zero(self):
        """陈旧/不一致 ACWR 不得在近期无训练时触发高风险告警。"""
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            acute_chronic_ratio=4.0,
            acwr_reliable=True,
            training_load_7d=0.0,
            workouts_this_week=0,
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.acwr_overload" not in _rule_ids(alerts)

    def test_acwr_alerts_require_reliable_chronic_baseline(self):
        """缺慢性基线时，高低 ACWR 数值都不得进入安全告警。"""
        for acwr in (0.5, 4.0):
            twin = _empty_twin()
            twin.behavioral = BehavioralState(
                acute_chronic_ratio=acwr,
                acwr_reliable=False,
                training_load_7d=25.0,
                workouts_this_week=1,
            )
            rule_ids = _rule_ids(evaluate_safety(twin).alerts)
            assert "training.acwr_overload" not in rule_ids
            assert "training.acwr_undertraining" not in rule_ids

    def test_legacy_cached_acwr_without_reliability_never_alerts(self):
        """旧 Twin 缓存没有 reliability 字段时必须 fail closed。"""
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            acute_chronic_ratio=4.0,
            training_load_7d=120.0,
            workouts_this_week=1,
        )

        rule_ids = _rule_ids(evaluate_safety(twin).alerts)

        assert "training.acwr_overload" not in rule_ids
        assert "training.acwr_undertraining" not in rule_ids

    def test_non_finite_acwr_never_alerts_even_if_marked_reliable(self):
        for acwr in (float("nan"), float("inf"), float("-inf")):
            twin = _empty_twin()
            twin.behavioral = BehavioralState(
                acute_chronic_ratio=acwr,
                acwr_reliable=True,
                training_load_7d=120.0,
                workouts_this_week=3,
            )
            rule_ids = _rule_ids(evaluate_safety(twin).alerts)
            assert "training.acwr_overload" not in rule_ids
            assert "training.acwr_undertraining" not in rule_ids

    def test_complete_inactivity_requires_explicit_complete_coverage(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            workouts_this_week=0,
            training_load_7d=0.0,
            acwr_unavailable_reason="insufficient_data_coverage",
        )

        alerts = evaluate_safety(twin).alerts

        assert "training.complete_inactivity" not in _rule_ids(alerts)

    def test_complete_inactivity(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            workouts_this_week=0,
            training_load_7d=0.0,
            acwr_unavailable_reason="no_recent_training",
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.complete_inactivity" in _rule_ids(alerts)


# ─────────────────────── Report ordering ──────────────────


class TestReportOrdering:
    def test_alerts_sorted_by_severity_desc(self):
        twin = _empty_twin()
        # 触发多级别
        twin.labs = LabsContext(
            blood_pressure_systolic=185,  # HIGH: 单次严重升高，需复测和症状分流
            blood_pressure_diastolic=125,
        )
        twin.physiological = PhysiologicalState(
            resting_hr=105,  # MEDIUM (tachycardia)
        )
        report = evaluate_safety(twin)
        assert len(report.alerts) >= 2
        # 第一条应该是严重度最高的
        severities = [int(a.severity) for a in report.alerts]
        assert severities == sorted(severities, reverse=True)
        assert report.high_count >= 1


# ─────────────────────── API shape ────────────────────────


class TestSafetyAPI:
    def test_api_unauthenticated(self, client):
        resp = client.get("/api/v1/safety/me")
        assert resp.status_code in (401, 403)

    def test_api_empty_user(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        resp = client.get(
            "/api/v1/safety/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "user_id" in body
        assert "alerts" in body
        assert "summary" in body
        assert body["summary"]["rules_evaluated"] > 0
        assert "timing" in body

    def test_severity_filter(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        resp = client.get(
            "/api/v1/safety/me?severity_min=3",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        # 空用户应该没有 HIGH+ 告警
        assert all(a["severity"]["value"] >= 3 for a in resp.json()["alerts"])

    def test_list_rules_endpoint(self, client, db):
        from tests.conftest import create_authenticated_user

        _, token = create_authenticated_user(db)
        resp = client.get(
            "/api/v1/safety/rules",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 30
        assert isinstance(body["rules"], list)
