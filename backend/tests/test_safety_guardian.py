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
