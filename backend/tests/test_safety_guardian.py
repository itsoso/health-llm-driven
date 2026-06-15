"""
Safety Guardian 单元测试。

策略：构造合成 Twin（不依赖数据库），给每个规则类别至少一条正例 + 一条反例。
"""

from datetime import date, datetime
from typing import List

import pytest

from app.agents.safety_guardian import evaluate_safety
from app.agents.safety_guardian.engine import registry
from app.agents.safety_guardian.schema import Alert, Severity
from app.twin.schema import (
    BehavioralState,
    BodyCompositionState,
    EnvironmentalState,
    GeneticContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    MentalState,
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
    def test_bp_hypertensive_crisis(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=185, blood_pressure_diastolic=125)
        report = evaluate_safety(twin)
        rule_ids = _rule_ids(report.alerts)
        assert "vitals.bp_hypertensive_crisis" in rule_ids
        crisis = next(a for a in report.alerts if a.rule_id == "vitals.bp_hypertensive_crisis")
        assert crisis.severity == Severity.CRITICAL
        assert crisis.requires_medical_attention is True
        # 高血压急症应该不触发 stage 2（互斥）
        assert "vitals.bp_stage_2_hypertension" not in rule_ids

    def test_bp_stage_2(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=155, blood_pressure_diastolic=95)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.bp_stage_2_hypertension" in rule_ids
        assert "vitals.bp_hypertensive_crisis" not in rule_ids

    def test_bp_normal_no_alert(self):
        twin = _empty_twin()
        twin.labs = LabsContext(blood_pressure_systolic=118, blood_pressure_diastolic=76)
        alerts = evaluate_safety(twin).alerts
        rule_ids = _rule_ids(alerts)
        assert "vitals.bp_hypertensive_crisis" not in rule_ids
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
        """min < 80% → CRITICAL，独立于 avg。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=92.0, spo2_min_overnight=74)
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.CRITICAL
        assert found.requires_medical_attention is True

    def test_spo2_min_nocturnal_high(self):
        """85 <= min < 88 → HIGH。"""
        twin = _empty_twin()
        twin.physiological = PhysiologicalState(spo2_avg=94.0, spo2_min_overnight=86)
        alerts = evaluate_safety(twin).alerts
        found = next((a for a in alerts if a.rule_id == "vitals.spo2_min_nocturnal_severe"), None)
        assert found is not None
        assert found.severity == Severity.HIGH

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

    def test_ldl_high(self):
        twin = _empty_twin()
        twin.labs = LabsContext(ldl=5.0)
        alerts = evaluate_safety(twin).alerts
        assert "labs.ldl_high" in _rule_ids(alerts)
        alert = next(a for a in alerts if a.rule_id == "labs.ldl_high")
        assert alert.severity == Severity.HIGH


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

    def test_cetirizine_alone_no_alert(self):
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "盐酸西替利嗪片"}])
        alerts = evaluate_safety(twin).alerts
        # 西替利嗪单独使用不该触发任何 DDI
        assert all(not a.rule_id.startswith("ddi.cetirizine") for a in alerts)


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

    def test_pgx_no_variant_no_alert(self):
        """基因缺失时 PGx 规则不触发。"""
        twin = _empty_twin()
        twin.medication = MedicationState(active_meds=[{"name": "可待因"}])
        # 没有基因数据
        alerts = evaluate_safety(twin).alerts
        assert not any(a.rule_id.startswith("pgx.cyp2d6") for a in alerts)


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
            acute_chronic_ratio=1.8, workouts_this_week=6
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.acwr_overload" in _rule_ids(alerts)

    def test_acwr_optimal_no_alert(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            acute_chronic_ratio=1.1, workouts_this_week=4
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.acwr_overload" not in _rule_ids(alerts)
        assert "training.acwr_undertraining" not in _rule_ids(alerts)

    def test_complete_inactivity(self):
        twin = _empty_twin()
        twin.behavioral = BehavioralState(
            workouts_this_week=0, training_load_7d=0.0
        )
        alerts = evaluate_safety(twin).alerts
        assert "training.complete_inactivity" in _rule_ids(alerts)


# ─────────────────────── Report ordering ──────────────────


class TestReportOrdering:
    def test_alerts_sorted_by_severity_desc(self):
        twin = _empty_twin()
        # 触发多级别
        twin.labs = LabsContext(
            blood_pressure_systolic=185,  # CRITICAL
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
        assert report.critical_count >= 1


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
