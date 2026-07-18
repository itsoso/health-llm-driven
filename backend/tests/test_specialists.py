"""
3 个新 specialist 的单元测试：Recovery / Fuel / Movement。

测试策略：
- 构造合成 Twin（不依赖数据库）
- 每个 specialist 至少：
  - applies_to 正反例
  - run 产出结构
  - 关键算法的边界（readiness 缺数据/过载/正常）
"""

from datetime import datetime

import pytest

from app.agents.fuel_strategist import FuelStrategistSpecialist
from app.agents.longevity_specialist.specialist import LongevitySpecialist
from app.agents.movement_coach import MovementCoachSpecialist
from app.agents.recovery_coach import RecoveryCoachSpecialist, compute_readiness
from app.orchestrator.intent import classify_intent
from app.orchestrator.schema import SpecialistFinding
from app.orchestrator.specialists import all_specialists
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
    TwinMeta,
    AcuteHealthState,
    ProblemRedLine,
)


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


def _rich_twin() -> HealthTwin:
    t = _empty_twin()
    t.physiological = PhysiologicalState(
        hrv_latest=55.0,
        hrv_7d_avg=58.0,
        sleep_score_latest=78,
        sleep_duration_h_latest=7.2,
        body_battery_current=65,
        stress_level_current=35,
        resting_hr=52,
    )
    t.body_composition = BodyCompositionState(
        weight_kg=72.0, tdee_kcal=2700, bmr_kcal=1600, bmi=22.1, bmi_category="正常"
    )
    t.behavioral = BehavioralState(
        diet_calories_today=1800,
        diet_protein_g_today=110,
        diet_carbs_g_today=200,
        meals_logged_today=3,
        water_ml_today=1500,
        water_goal_ml=2000,
        workouts_this_week=4,
        training_load_7d=350,
        acute_chronic_ratio=1.1,
        acwr_zone="optimal",
    )
    return t


# ───────────────────── Registry ───────────────────────


class TestRegistration:
    def test_all_four_specialists_present(self):
        names = {s.name for s in all_specialists()}
        assert "safety_guardian" in names
        assert "recovery_coach" in names
        assert "fuel_strategist" in names
        assert "movement_coach" in names

    def test_ordering_places_recovery_before_movement(self):
        """Movement Coach 依赖 Recovery Coach 的 readiness_zone，必须后执行。"""
        names = [s.name for s in all_specialists()]
        assert names.index("recovery_coach") < names.index("movement_coach")


# ───────────────────── Recovery Coach ────────────────


class TestRecoveryCoach:
    def test_readiness_empty_twin(self):
        b = compute_readiness(_empty_twin())
        assert b.score == 0
        assert b.zone == "unknown"
        assert len(b.missing_components) >= 4

    def test_readiness_rich_data(self):
        b = compute_readiness(_rich_twin())
        assert 50 <= b.score <= 100
        assert b.zone in ("moderate", "light", "hard")
        # 所有组件都应存在
        assert set(b.components.keys()) == {
            "hrv", "sleep_quality", "sleep_duration", "body_battery", "stress"
        }

    def test_readiness_partial_data_reweights(self):
        t = _empty_twin()
        t.physiological = PhysiologicalState(
            sleep_score_latest=90,
            sleep_duration_h_latest=8.0,
        )
        b = compute_readiness(t)
        # 只有 2 个组件有数据，权重应该重分配
        assert len(b.components) == 2
        # 两个组件都 >0.8 → score 至少 75+
        assert b.score >= 60

    def test_readiness_acwr_overload_penalty(self):
        t = _rich_twin()
        t.behavioral.acute_chronic_ratio = 1.7
        b = compute_readiness(t)
        assert b.penalty == 15

    def test_specialist_applies_on_recovery_intent(self):
        s = RecoveryCoachSpecialist()
        intent = classify_intent("我今天好累")
        # "累" 在 recovery 关键字里
        assert "recovery" in intent.categories
        assert s.applies_to(intent, _empty_twin()) is True

    def test_specialist_run_produces_findings(self):
        s = RecoveryCoachSpecialist()
        finding = s.run(_rich_twin(), {})
        assert finding.specialist_name == "recovery_coach"
        # 第一条必为 readiness_score
        assert finding.findings[0]["type"] == "readiness_score"
        # 至少应有一条 action
        assert any(f.get("type") == "action" for f in finding.findings)
        assert finding.raw.get("zone") is not None

    def test_high_readiness_emits_forecast_not_plan(self):
        """高分稳定 (readiness >= 70 + HRV 接近 baseline) → 应发 forecast 卡, 不发 plan."""
        from app.agents.recovery_coach.coach import _build_proposed_cards, compute_readiness
        # 构造 readiness ≥ 70 的高分态
        t = _empty_twin()
        t.physiological = PhysiologicalState(
            hrv_latest=58.0,           # ≥ baseline*0.9 = 52.2
            hrv_7d_avg=58.0,
            sleep_score_latest=85,
            sleep_duration_h_latest=8.0,
            body_battery_current=80,
            stress_level_current=20,
            resting_hr=50,
        )
        b = compute_readiness(t)
        assert b.score >= 70, f"前置条件不成立, score={b.score}"

        cards = _build_proposed_cards(b, t)
        forecast_cards = [c for c in cards if c.card_type == "forecast"]
        plan_cards = [c for c in cards if c.card_type == "plan"]

        assert len(forecast_cards) == 1
        assert len(plan_cards) == 0
        forecast = forecast_cards[0]
        assert forecast.metric_key == "hrv"
        assert forecast.verification_days == 3
        assert forecast.target_value.startswith(">"), f"forecast target 应是数值阈值: {forecast.target_value}"
        assert "纯预测" in forecast.content or "预测" in forecast.title

    def test_low_readiness_emits_plan_not_forecast(self):
        """低分态 (readiness < 60 + HRV 在 baseline 之下) 仍出 plan, 不出 forecast."""
        from app.agents.recovery_coach.coach import _build_proposed_cards, compute_readiness
        t = _empty_twin()
        t.physiological = PhysiologicalState(
            hrv_latest=35.0,           # 远低于 baseline
            hrv_7d_avg=55.0,
            sleep_score_latest=50,
            sleep_duration_h_latest=5.5,
            body_battery_current=30,
            stress_level_current=70,
            resting_hr=68,
        )
        b = compute_readiness(t)
        assert b.score < 60

        cards = _build_proposed_cards(b, t)
        forecast_cards = [c for c in cards if c.card_type == "forecast"]
        plan_cards = [c for c in cards if c.card_type == "plan"]

        assert len(forecast_cards) == 0
        assert len(plan_cards) == 1
        plan = plan_cards[0]
        assert plan.metric_key == "hrv"
        assert plan.verification_days == 7


# ───────────────────── Fuel Strategist ────────────────


class TestFuelStrategist:
    def test_applies_on_fuel_intent(self):
        s = FuelStrategistSpecialist()
        intent = classify_intent("今天吃什么好")
        assert "fuel" in intent.categories
        assert s.applies_to(intent, _empty_twin()) is True

    def test_run_computes_energy_and_protein(self):
        s = FuelStrategistSpecialist()
        finding = s.run(_rich_twin(), {})
        # 找到 energy finding
        energy = next(f for f in finding.findings if f.get("type") == "energy")
        assert energy["remaining_kcal"] == 900  # 2700 - 1800
        assert energy["progress_pct"] in (66, 67)

        protein = next(f for f in finding.findings if f.get("type") == "protein")
        # target = 72 * 1.8 (training_load > 200) = 129.6 → 130
        assert protein["target_g"] == 130
        # 110 / 130 ≈ 85%
        assert 80 <= protein["progress_pct"] <= 90

    def test_protein_target_low_activity(self):
        """训练负荷低时用 1.4 g/kg。"""
        from app.agents.fuel_strategist.strategist import _protein_target_g

        assert _protein_target_g(70.0, 100) == 70.0 * 1.4
        assert _protein_target_g(70.0, 250) == 70.0 * 1.8
        assert _protein_target_g(None, 200) is None

    def test_hydration_low_warning(self):
        s = FuelStrategistSpecialist()
        t = _rich_twin()
        t.behavioral.water_ml_today = 400
        finding = s.run(t, {})
        hyd = next(f for f in finding.findings if f.get("type") == "hydration")
        assert hyd["status"] == "low"

    def test_gene_nudge_mthfr(self):
        from app.agents.fuel_strategist.strategist import _gene_nudges

        t = _empty_twin()
        t.genetic = GeneticContext(
            has_profile=True,
            risk_variants=[
                {"gene_name": "MTHFR", "genotype": "TT", "result_label": "poor"},
            ],
        )
        nudges = _gene_nudges(t)
        assert any(n["gene"] == "MTHFR" for n in nudges)

    def test_stable_weight_emits_forecast(self):
        """没有减重诉求 + 体重存在 → 应发 forecast '7 天体重保持稳定'."""
        s = FuelStrategistSpecialist()
        t = _rich_twin()
        # rich_twin 默认 weight=72, 没设 goals → forecast 触发
        finding = s.run(t, {})
        forecasts = [c for c in finding.proposed_cards if c.card_type == "forecast"]
        plans = [c for c in finding.proposed_cards if c.card_type == "plan"]

        assert len(forecasts) == 1
        assert len(plans) == 0
        f = forecasts[0]
        assert f.metric_key == "weight"
        assert f.verification_days == 7
        assert f.target_value.startswith("<"), f"应是上限 target: {f.target_value}"
        assert "纯预测" in f.content

    def test_no_weight_no_forecast(self):
        """缺体重数据 → 不发 forecast (no metric to forecast)."""
        s = FuelStrategistSpecialist()
        t = _rich_twin()
        t.body_composition.weight_kg = None  # type: ignore[assignment]
        finding = s.run(t, {})
        forecasts = [c for c in finding.proposed_cards if c.card_type == "forecast"]
        assert len(forecasts) == 0


# ───────────────────── Movement Coach ────────────────


class TestMovementCoach:
    def test_training_status_classification(self):
        from app.agents.movement_coach.coach import _training_status

        assert _training_status(1.1, 4) == "optimal"
        assert _training_status(1.4, 4) == "peaking"
        assert _training_status(1.7, 4) == "overload"
        assert _training_status(0.6, 2) == "undertrained"
        assert _training_status(0.3, 1) == "detraining"
        assert _training_status(None, None) == "unknown"

    def test_intensity_matrix_overload(self):
        """过载状态下无论 readiness 如何都应限制强度。"""
        from app.agents.movement_coach.coach import _today_intensity

        code, _ = _today_intensity("overload", "hard")
        assert code in ("low", "rest")

        code, _ = _today_intensity("overload", "moderate")
        assert code in ("low", "rest")

    def test_intensity_optimal_with_readiness(self):
        from app.agents.movement_coach.coach import _today_intensity

        code, _ = _today_intensity("optimal", "hard")
        assert code == "high"
        code, _ = _today_intensity("optimal", "rest")
        assert code == "rest"

    def test_specialist_run_with_readiness_context(self):
        s = MovementCoachSpecialist()
        t = _rich_twin()
        t.behavioral.acute_chronic_ratio = 1.7  # 过载
        finding = s.run(t, {"readiness_zone": "hard"})
        pres = next(f for f in finding.findings if f.get("type") == "today_prescription")
        # 尽管 readiness=hard，过载必须限制
        assert pres["intensity"] in ("low", "rest")
        assert pres["based_on_readiness"] == "hard"

    def test_acute_cold_symptoms_force_rest_even_when_undertrained(self):
        s = MovementCoachSpecialist()
        t = _rich_twin()
        t.behavioral.acute_chronic_ratio = 0.6
        t.behavioral.workouts_this_week = 1
        t.acute = AcuteHealthState(
            has_active_illness=True,
            illness_names=["感冒"],
            recent_symptoms=["咳嗽", "嗓子疼"],
            suspected_cold=True,
            should_rest_from_training=True,
            training_guardrail="急性上呼吸道症状期暂停训练。",
        )

        finding = s.run(t, {"readiness_zone": "hard"})
        pres = next(f for f in finding.findings if f.get("type") == "today_prescription")

        assert pres["intensity"] == "rest"
        assert pres["reason"] == "acute_illness"
        assert "暂停" in pres["guidance"]
        assert finding.proposed_cards == []

    def test_specialist_applies_on_movement_intent(self):
        s = MovementCoachSpecialist()
        intent = classify_intent("我今天能跑步吗")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_actn3_gene_bias(self):
        s = MovementCoachSpecialist()
        t = _rich_twin()
        t.genetic = GeneticContext(
            has_profile=True,
            drug_sensitivity=[
                {"gene_name": "ACTN3", "genotype": "RR", "result_label": "power-biased"},
            ],
        )
        finding = s.run(t, {})
        gene_items = [f for f in finding.findings if f.get("type") == "gene_bias"]
        assert len(gene_items) == 1
        assert "力量" in gene_items[0]["bias"] or "爆发" in gene_items[0]["bias"]


# ───────────────────── Orchestrator 集成（Readiness → Movement）──


# ───────────────────── Mental Health ──────────────────


class TestMentalHealthCompanion:
    def test_applies_on_mental_intent(self):
        from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

        s = MentalHealthCompanionSpecialist()
        intent = classify_intent("我最近情绪很低落")
        assert s.applies_to(intent, _empty_twin()) is True

    def test_crisis_detection(self):
        from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

        s = MentalHealthCompanionSpecialist()
        t = _empty_twin()
        t.mental = MentalState(mood_7d_avg=2.0, energy_7d_avg=3.0, stress_7d_avg=8.0)
        finding = s.run(t, {})
        assert finding.raw.get("has_crisis_signal") is True
        crisis = next((f for f in finding.findings if f.get("type") == "crisis_warning"), None)
        assert crisis is not None
        assert "hotlines" in crisis

    def test_no_crisis_when_mood_ok(self):
        from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

        s = MentalHealthCompanionSpecialist()
        t = _empty_twin()
        t.mental = MentalState(mood_7d_avg=7.0, energy_7d_avg=6.5)
        finding = s.run(t, {})
        assert finding.raw.get("has_crisis_signal") is False

    def test_support_actions_generated(self):
        from app.agents.mental_health_companion import MentalHealthCompanionSpecialist

        s = MentalHealthCompanionSpecialist()
        t = _empty_twin()
        t.mental = MentalState(mood_7d_avg=4.0, stress_7d_avg=7.0, sleep_quality_7d_avg=5.0)
        t.physiological = PhysiologicalState(stress_level_current=65)
        finding = s.run(t, {})
        actions = [f for f in finding.findings if f.get("type") == "support_action"]
        assert len(actions) >= 2


# ───────────────────── Chronic: Rhinitis ─────────────


class TestRhinitisSpecialist:
    def test_applies_on_rhinitis_data(self):
        from app.agents.chronic_specialists import RhinitisSpecialist

        s = RhinitisSpecialist()
        t = _empty_twin()
        t.behavioral = BehavioralState(sneeze_count_today=5, nasal_wash_count_today=2)
        intent = classify_intent("你好")
        assert s.applies_to(intent, t) is True

    def test_severity_classification(self):
        from app.agents.chronic_specialists.rhinitis import _rhinitis_severity

        assert _rhinitis_severity(0, 0) == "stable"
        assert _rhinitis_severity(5, 1) == "mild"
        assert _rhinitis_severity(12, 3) == "moderate"
        assert _rhinitis_severity(25, 5) == "severe"

    def test_env_trigger_high_aqi(self):
        from app.agents.chronic_specialists import RhinitisSpecialist

        s = RhinitisSpecialist()
        t = _empty_twin()
        t.behavioral = BehavioralState(sneeze_count_today=3, nasal_wash_count_today=1)
        t.environment = EnvironmentalState(aqi=120, humidity_pct=80)
        finding = s.run(t, {})
        env_triggers = [f for f in finding.findings if f.get("type") == "env_trigger"]
        assert len(env_triggers) >= 1  # AQI 120 > 100

    # ── LPR 反流共现假说分支(锚点用户:伏诺拉生 + 胃溃疡 Hp- + 鼻症状)──

    @staticmethod
    def _reflux_twin(sneeze=12, wash=3, ppi="伏诺拉生", problem="胃溃疡(Hp 阴性,胃窦后壁)", extra_meds=None):
        from app.agents.chronic_specialists import RhinitisSpecialist  # noqa: F401
        t = _empty_twin()
        t.behavioral = BehavioralState(sneeze_count_today=sneeze, nasal_wash_count_today=wash)
        meds = []
        if ppi:
            meds.append({"name": ppi, "kind": "medication"})
        if extra_meds:
            meds += [{"name": m, "kind": "medication"} for m in extra_meds]
        if meds:
            t.medication = MedicationState(active_meds=meds)
        if problem:
            t.acute = AcuteHealthState(problem_red_lines=[
                ProblemRedLine(problem_name=problem, condition="黑便/呕血", action="立即就医", risk_level="P1")
            ])
        return t

    def test_reflux_hypothesis_fires_on_cooccurrence(self):
        from app.agents.chronic_specialists import RhinitisSpecialist
        finding = RhinitisSpecialist().run(self._reflux_twin(), {})
        rh = [f for f in finding.findings if f.get("type") == "reflux_hypothesis"]
        assert len(rh) == 1
        a = rh[0]
        assert a["confidence"] == "hypothesis"
        # 安全框架必须落在 LLM 实际可见的字段:title + summary(orchestrator 序列化器丢弃 message)
        assert "相关" in a.get("title", "") and "非诊断" in a.get("title", "")
        assert "非因果" in finding.summary or "非诊断" in finding.summary
        # message 也带(冗余,审计/前端用)
        assert "相关" in a["message"]
        assert "非因果" in a["message"] or "不是诊断" in a["message"]
        # R4:非处方 + 非诊断(命令式/确诊措辞均禁)—— 覆盖所有 LLM 可见 + 审计字段
        blob = a.get("title", "") + " " + a["message"] + " " + a.get("action", "")
        for banned in ["停药", "减量", "立即停", "请停", "你患有", "诊断为", "确诊", "mg"]:
            assert banned not in blob, f"R4/诊断越界: {banned}"

    def test_no_reflux_hypothesis_without_acid_suppression(self):
        from app.agents.chronic_specialists import RhinitisSpecialist
        # 有鼻症状 + 胃溃疡记录,但没在用抑酸药 → 不触发
        finding = RhinitisSpecialist().run(self._reflux_twin(ppi=None), {})
        assert not any(f.get("type") == "reflux_hypothesis" for f in finding.findings)

    def test_no_reflux_hypothesis_without_reflux_indicator(self):
        from app.agents.chronic_specialists import RhinitisSpecialist
        # 有鼻症状 + 在用伏诺拉生,但无任何反流/上消化道指标 → 不臆测,不触发
        finding = RhinitisSpecialist().run(self._reflux_twin(problem=None), {})
        assert not any(f.get("type") == "reflux_hypothesis" for f in finding.findings)

    def test_no_reflux_hypothesis_when_stable(self):
        from app.agents.chronic_specialists import RhinitisSpecialist
        # 无鼻症状(stable)即便有抑酸药+胃记录也不触发(避免对无症状者乱关联)
        finding = RhinitisSpecialist().run(self._reflux_twin(sneeze=0, wash=0), {})
        assert not any(f.get("type") == "reflux_hypothesis" for f in finding.findings)

    def test_reflux_hypothesis_preserves_severity_and_adherence(self):
        from app.agents.chronic_specialists import RhinitisSpecialist
        # 共现 + 在用莫米松 → 假说与既有 severity/依从 finding 并存,severity 不被改写
        finding = RhinitisSpecialist().run(self._reflux_twin(extra_meds=["莫米松"]), {})
        sev = [f for f in finding.findings if f.get("type") == "symptom_severity"]
        assert sev and sev[0]["severity"] == "moderate"  # 未被假说分支改写
        assert any(f.get("type") == "med_adherence" for f in finding.findings)
        assert any(f.get("type") == "reflux_hypothesis" for f in finding.findings)


# ───────────────────── Chronic: Hypertension ─────────


class TestHypertensionSpecialist:
    def test_bp_classification(self):
        from app.agents.chronic_specialists.hypertension import _bp_stage

        assert _bp_stage(115, 75) == "normal"
        assert _bp_stage(125, 78) == "elevated"
        assert _bp_stage(135, 85) == "stage1"
        assert _bp_stage(155, 95) == "stage2"
        assert _bp_stage(185, 125) == "severe"
        assert _bp_stage(None, None) == "unknown"

    def test_specialist_produces_findings(self):
        from app.agents.chronic_specialists import HypertensionSpecialist

        s = HypertensionSpecialist()
        t = _empty_twin()
        t.labs = LabsContext(blood_pressure_systolic=155, blood_pressure_diastolic=95)
        finding = s.run(t, {})
        assert "stage2" in finding.raw.get("stage", "")
        actions = [f for f in finding.findings if f.get("type") == "action"]
        assert len(actions) >= 2


# ───────────────────── Chronic: Metabolic ────────────


class TestMetabolicSpecialist:
    def test_metabolic_syndrome_detection(self):
        from app.agents.chronic_specialists.metabolic import _metabolic_syndrome_criteria

        t = _empty_twin()
        t.body_composition = BodyCompositionState(bmi=30.0)
        t.labs = LabsContext(
            triglycerides=2.0, hdl=0.9,
            blood_pressure_systolic=140, blood_pressure_diastolic=90,
            blood_glucose=6.0,
        )
        result = _metabolic_syndrome_criteria(t)
        assert result["is_metabolic_syndrome"] is True
        assert result["criteria_hit"] >= 3

    def test_no_metabolic_syndrome_normal(self):
        from app.agents.chronic_specialists.metabolic import _metabolic_syndrome_criteria

        t = _empty_twin()
        t.body_composition = BodyCompositionState(bmi=22.0)
        t.labs = LabsContext(blood_pressure_systolic=118, blood_pressure_diastolic=76)
        result = _metabolic_syndrome_criteria(t)
        assert result["is_metabolic_syndrome"] is False


# ───────────────────── needsSkill regex regression ───


class TestNeedsSkillRegex:
    """确保 needsSkill 正则不会误命中通用查询。"""

    def test_diet_queries_match(self):
        """饮食记录意图应命中。"""
        import re

        pattern = r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|早餐|午餐|晚餐|加餐"
        assert re.search(pattern, "记录午餐：牛奶200ml")
        assert re.search(pattern, "我吃了一个苹果")
        assert re.search(pattern, "打卡洗鼻")
        assert re.search(pattern, "记录今天血压 120/80")

    def test_general_queries_no_match(self):
        """通用查询不应命中。"""
        import re

        pattern = r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|早餐|午餐|晚餐|加餐"
        assert not re.search(pattern, "分析我的健康状况")
        assert not re.search(pattern, "我最近HRV怎么样")
        assert not re.search(pattern, "今天天气如何")

    def test_borderline_correctly_matches(self):
        """边界情况：含有关键字但语义确实是记录。"""
        import re

        pattern = r"记录|打卡|吃了|喝了|服药|补剂|体重|血压|洗鼻|喷嚏|早餐|午餐|晚餐|加餐"
        assert re.search(pattern, "帮我记录体重72kg")
        assert re.search(pattern, "早餐吃的燕麦")


# ───────────────────── Longevity (PhenoAge) ─────────────


class TestLongevitySpecialist:
    """LongevitySpecialist —— 解读 PhenoAge + 委托四件套(抗衰 MVP Step 2)。"""

    @staticmethod
    def _twin_with_phenoage() -> HealthTwin:
        """模拟 builder 已填充 PhenoAge 派生字段的 Twin。"""
        t = _empty_twin()
        t.labs = LabsContext(
            albumin=45.0,
            creatinine=80.0,
            blood_glucose=5.2,
            crp=0.08,
            lymphocyte_pct=32.0,
            mcv=89.0,
            rdw=13.0,
            alp=70.0,
            wbc=6.0,
            phenotypic_age=47.0,
            phenotypic_age_delta_years=5.0,
            phenotypic_age_inputs_complete=True,
            phenoage_evidence_tier="validated",
            phenoage_claim_boundary="PhenoAge 是基于血检的死亡风险代理指标...",
        )
        return t

    def test_applies_on_keyword(self):
        sp = LongevitySpecialist()
        intent = classify_intent("我的身体年龄是多少")
        assert sp.applies_to(intent, _empty_twin())

    def test_applies_on_phenoage_available_in_general(self):
        """PhenoAge 已算出 + general 对话 → 也参与(给一句解读)。"""
        sp = LongevitySpecialist()
        intent = classify_intent("我的健康怎么样")  # → general
        assert "general" in intent.categories
        assert sp.applies_to(intent, self._twin_with_phenoage())

    def test_does_not_apply_when_no_phenoage_no_keyword(self):
        sp = LongevitySpecialist()
        intent = classify_intent("今天HRV怎么样")
        # 普通查询且 phenoage 缺失 → 不参与(避免噪声)
        assert not sp.applies_to(intent, _empty_twin())

    def test_run_with_phenoage_emits_age_finding(self):
        sp = LongevitySpecialist()
        twin = self._twin_with_phenoage()
        finding = sp.run(twin, {})
        assert isinstance(finding, SpecialistFinding)
        assert finding.specialist_name == "longevity"
        types = {f.get("type") for f in finding.findings}
        assert "phenotypic_age" in types
        # W4: "委托文字" 升级为真实编排的四件套整合协议(科学仍由各专家产出)
        assert "longevity_protocol" in types
        proto = next(f for f in finding.findings if f.get("type") == "longevity_protocol")
        assert proto["pillars"] and all(p.get("action") for p in proto["pillars"])
        # summary 含核心数字
        assert "47" in finding.summary

    def test_run_emits_claim_boundary(self):
        """诚实纪律:展示侧能拿到 claim_boundary + evidence_tier。"""
        sp = LongevitySpecialist()
        finding = sp.run(self._twin_with_phenoage(), {})
        pa = next(f for f in finding.findings if f.get("type") == "phenotypic_age")
        assert pa["evidence_tier"] == "validated"
        assert pa["claim_boundary"]  # 非空
        assert "levine_2018_phenoage" in finding.evidence_refs

    def test_run_without_phenoage_lists_missing_inputs(self):
        """没算出来不假装有结果,列缺啥让用户补。"""
        sp = LongevitySpecialist()
        # 抗衰意图但 Twin 完全空 → 9 项全缺
        finding = sp.run(_empty_twin(), {})
        assert finding.findings
        unavail = finding.findings[0]
        assert unavail["type"] == "phenoage_unavailable"
        assert len(unavail["missing_inputs"]) == 9  # 全部 9 项血检

    def test_run_identifies_drags_when_present(self):
        """高 CRP / 高血糖等明显异常应进入 drags(由 orchestrator 转发四件套处理)。"""
        sp = LongevitySpecialist()
        twin = self._twin_with_phenoage()
        twin.labs.crp = 0.5      # 升高
        twin.labs.blood_glucose = 6.5  # 偏高
        finding = sp.run(twin, {})
        drags = next((f for f in finding.findings if f.get("type") == "drags"), None)
        assert drags is not None
        metrics = {d["metric"] for d in drags["items"]}
        assert "crp" in metrics
        assert "blood_glucose" in metrics


class TestLongevityRegistry:
    def test_longevity_specialist_registered(self):
        names = {s.name for s in all_specialists()}
        assert "longevity" in names

    def test_specialists_count_is_13(self):
        """注册表 13: 12 (含 LongevitySpecialist) + CrossSourceValidatorSpecialist。"""
        assert len(all_specialists()) == 13


# ───────────────────── Orchestrator + memory ─────────


@pytest.mark.asyncio
async def test_orchestrator_propagates_readiness(monkeypatch, db):
    """端到端验证 Recovery Coach 的 readiness_zone 会传到 Movement Coach。"""
    import uuid

    from app.models.user import User
    from app.orchestrator import OrchestratorRequest
    from app.orchestrator import orchestrator as orch_mod

    user = User(
        username=f"prop_{uuid.uuid4().hex[:6]}",
        email=f"prop_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="prop test",
        is_active=True,
        is_approved=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 伪造 LLM (signature 跟随 _call_llm: lite_mode + 2026-07-15 起 allow_synthesis_override)
    async def fake_llm(sp, up, *, lite_mode=False, **kwargs):
        return "(fake synthesis)"

    monkeypatch.setattr(orch_mod, "_call_llm", fake_llm)

    # 伪造 build_twin 返回 rich twin
    def fake_build(db_, user_id):
        return _rich_twin()

    monkeypatch.setattr(orch_mod, "build_twin", fake_build)

    req = OrchestratorRequest(
        query="我今天能不能高强度训练",
        specialists=["recovery_coach", "movement_coach"],
        stream=False,
    )
    resp = await orch_mod.run_orchestrator(db, user.id, req)

    assert "recovery_coach" in resp.used_specialists
    assert "movement_coach" in resp.used_specialists

    # Movement Coach 的 finding 应该带上 based_on_readiness
    movement_finding = next(
        f for f in resp.findings if f.specialist_name == "movement_coach"
    )
    prescription = next(
        item for item in movement_finding.findings
        if item.get("type") == "today_prescription"
    )
    assert prescription["based_on_readiness"] is not None
