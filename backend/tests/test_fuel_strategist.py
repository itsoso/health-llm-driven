"""Fuel Strategist 深度单测 (#70).

test_specialists.py 已覆盖 applies_to / energy / protein / hydration_low /
MTHFR nudge / forecast / no-weight-no-forecast (7 个).

这里补的是之前没碰过的分支:
  - _meal_slot_now 时间边界
  - _next_meal_guidance 4 个 kcal bucket
  - supplement finding 发出条件
  - labs_concern (LDL 异常时)
  - 14 天减重 plan card (cur_weight > target_weight + 0.5)
  - 多个 gene_nudges (APOE4 / FADS1 / ALDH2 / FTO)
  - failed run 路径 (异常被 catch 包起来)
  - 空 twin 不 crash, 只发 hydration + next_meal
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from app.agents.fuel_strategist import FuelStrategistSpecialist
from app.agents.fuel_strategist.strategist import (
    _meal_slot_now, _next_meal_guidance, _gene_nudges, _protein_target_g,
)
from app.orchestrator.intent import classify_intent
from app.twin.schema import (
    BehavioralState, BodyCompositionState, GeneticContext, GoalsContext,
    HealthTwin, LabsContext, SupplementState, TwinMeta,
)


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


def _rich_twin() -> HealthTwin:
    t = _empty_twin()
    t.body_composition = BodyCompositionState(weight_kg=72.0, tdee_kcal=2700, bmr_kcal=1600)
    t.behavioral = BehavioralState(
        diet_calories_today=1800, diet_protein_g_today=110,
        meals_logged_today=3, water_ml_today=1500, water_goal_ml=2000,
        training_load_7d=350,
    )
    return t


# ───────────── _meal_slot_now ─────────────

@pytest.mark.parametrize("hour,expected", [
    (5, "早餐"), (9, "早餐"),
    (10, "午餐"), (13, "午餐"),
    (14, "下午加餐"), (17, "下午加餐"),
    (18, "晚餐"), (20, "晚餐"),
    (21, "夜宵/睡前补充"), (3, "夜宵/睡前补充"),
])
def test_meal_slot_boundaries(hour, expected):
    fake_now = datetime(2026, 5, 9, hour, 30)
    with patch("app.agents.fuel_strategist.strategist.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert _meal_slot_now() == expected


# ───────────── _next_meal_guidance ─────────────

def test_next_meal_guidance_large_remaining():
    findings = [{"type": "energy", "remaining_kcal": 800}]
    g = _next_meal_guidance("晚餐", findings)
    assert "正餐可以安排" in g


def test_next_meal_guidance_medium_remaining():
    findings = [{"type": "energy", "remaining_kcal": 400}]
    g = _next_meal_guidance("下午加餐", findings)
    assert "轻食" in g


def test_next_meal_guidance_low_remaining():
    findings = [{"type": "energy", "remaining_kcal": 100}]
    g = _next_meal_guidance("晚餐", findings)
    assert "低热量" in g or "高纤维" in g


def test_next_meal_guidance_over_budget():
    findings = [{"type": "energy", "remaining_kcal": -300}]
    g = _next_meal_guidance("夜宵/睡前补充", findings)
    assert "已超出" in g or "减少" in g


# ───────────── supplement finding ─────────────

def test_supplement_finding_emits_when_active_count():
    s = FuelStrategistSpecialist()
    t = _rich_twin()
    t.supplement = SupplementState(
        total_active_count=3,
        taken_today_count=1,
        active_supplements=[
            {"name": "鱼油", "taken": True},
            {"name": "维生素D", "taken": False},
            {"name": "镁", "taken": False},
        ],
    )
    f = s.run(t, {})
    sup = next(x for x in f.findings if x.get("type") == "supplement")
    assert sup["taken_today"] == 1
    assert sup["total"] == 3
    assert "维生素D" in sup["pending"]
    assert "镁" in sup["pending"]


def test_supplement_finding_skipped_when_zero_active():
    s = FuelStrategistSpecialist()
    t = _rich_twin()  # 默认 supplement.total_active_count == 0
    f = s.run(t, {})
    assert not any(x.get("type") == "supplement" for x in f.findings)


# ───────────── labs_concern ─────────────

def test_labs_concern_picks_lipid_glucose_liver_only():
    s = FuelStrategistSpecialist()
    t = _rich_twin()
    t.labs = LabsContext(flagged_abnormal=[
        {"item_name": "LDL"},
        {"item_name": "甘油三酯"},
        {"item_name": "白细胞"},  # 不在白名单, 应被过滤
        {"item_name": "HbA1c"},
    ])
    f = s.run(t, {})
    concern = next(x for x in f.findings if x.get("type") == "labs_concern")
    assert "LDL" in concern["items"]
    assert "甘油三酯" in concern["items"]
    assert "HbA1c" in concern["items"]
    assert "白细胞" not in concern["items"]


def test_labs_concern_skipped_when_no_flagged():
    s = FuelStrategistSpecialist()
    t = _rich_twin()  # 默认 labs.flagged_abnormal == []
    f = s.run(t, {})
    assert not any(x.get("type") == "labs_concern" for x in f.findings)


# ───────────── 14 天减重 plan card ─────────────

def test_weight_loss_plan_card_when_above_target():
    s = FuelStrategistSpecialist()
    t = _rich_twin()  # weight=72
    t.goals = GoalsContext()
    object.__setattr__(t.goals, "target_weight_kg", 68.0)  # 想减到 68 (差 4)
    f = s.run(t, {})
    plans = [c for c in f.proposed_cards if c.card_type == "plan"]
    assert len(plans) == 1
    plan = plans[0]
    assert plan.metric_key == "weight"
    assert plan.verification_days == 14
    assert plan.target_value.startswith("<")
    # 期望减 0.7kg → target ~ 71.3
    assert "71.3" in plan.target_value


def test_no_plan_card_when_at_target():
    """target 在 ±0.5kg 内 → 走 forecast, 不发 plan."""
    s = FuelStrategistSpecialist()
    t = _rich_twin()
    t.goals = GoalsContext()
    object.__setattr__(t.goals, "target_weight_kg", 72.2)  # 已在 ±0.5
    f = s.run(t, {})
    plans = [c for c in f.proposed_cards if c.card_type == "plan"]
    forecasts = [c for c in f.proposed_cards if c.card_type == "forecast"]
    assert len(plans) == 0
    assert len(forecasts) == 1


# ───────────── 多 gene nudges ─────────────

def test_gene_nudge_apoe4_fads1_aldh2_fto():
    """覆盖回退路径 — 没 GeneConfig, 用 risk_variants 解析."""
    t = _empty_twin()
    t.genetic = GeneticContext(
        has_profile=True,
        risk_variants=[
            {"gene_name": "APOE", "genotype": "E4/E4", "result_label": "high_risk"},
            {"gene_name": "FADS1", "genotype": "TT", "result_label": "reduced"},
            {"gene_name": "ALDH2", "genotype": "TT", "result_label": "poor"},
            {"gene_name": "FTO", "genotype": "AA", "result_label": "poor"},
        ],
    )
    nudges = _gene_nudges(t)
    genes = {n["gene"] for n in nudges}
    assert "APOE" in genes
    assert "FADS1" in genes
    assert "ALDH2" in genes
    assert "FTO" in genes


def test_gene_nudge_empty_when_no_genetic():
    t = _empty_twin()
    nudges = _gene_nudges(t)
    assert nudges == []


def test_gene_nudge_mthfr_uses_conservative_language():
    t = _empty_twin()
    t.genetic = GeneticContext(
        has_profile=True,
        risk_variants=[
            {"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"},
        ],
    )

    nudges = _gene_nudges(t)
    mthfr = next(n for n in nudges if n["gene"] == "MTHFR")

    assert "必须" not in mthfr["tip"]
    assert "结合同型半胱氨酸" in mthfr["tip"]


def test_gene_nudge_cyp1a2_slow_no_avoid_imperative():
    """CYP1A2 慢代谢: FuelStrategist 的咖啡因提示已与 gene_config 软化对齐 —
    不再硬性'避免咖啡', 改为概率性'可前移, 以睡眠反馈为准'(弱证据,临床结局重复性差)."""
    from app.twin.gene_config import build_gene_config

    t = _empty_twin()
    t.genetic = GeneticContext(
        has_profile=True,
        total_variants=1,
        nutrition_variants=[
            {"gene_name": "CYP1A2", "genotype": "AC", "result_label": "slow metabolizer"},
        ],
    )
    t.gene_config = build_gene_config(t)
    assert t.gene_config is not None and t.gene_config.caffeine_metabolism == "slow"

    nudges = _gene_nudges(t)
    cyp = next(n for n in nudges if n["gene"] == "CYP1A2")

    assert "避免咖啡" not in cyp["tip"]
    assert "避免咖啡/茶" not in cyp["tip"]
    assert "睡眠反馈" in cyp["tip"]


def test_run_includes_knowledge_evidence_from_context():
    s = FuelStrategistSpecialist()
    f = s.run(
        _rich_twin(),
        {
            "knowledge_evidence": {
                "sources": [{"title": "蛋白质与代谢健康", "excerpt": "优先从食物获取蛋白"}],
                "claim_boundary": "wiki 不是诊断",
            }
        },
    )

    evidence = next(x for x in f.findings if x.get("type") == "knowledge_evidence")
    assert evidence["sources"][0]["title"] == "蛋白质与代谢健康"
    assert evidence["claim_boundary"] == "wiki 不是诊断"


# ───────────── 失败兜底 ─────────────

def test_run_catches_internal_exception():
    s = FuelStrategistSpecialist()
    # 用一个会让内部 .behavioral 取属性 raise 的对象, 触发 except 分支
    bad_twin = _rich_twin()
    # 把 behavioral 替换成一个会在被属性访问时抛异常的桩
    class _Bomb:
        def __getattr__(self, name):
            raise RuntimeError(f"boom: {name}")
    bad_twin.__dict__["behavioral"] = _Bomb()
    f = s.run(bad_twin, {})
    assert f.specialist_name == "fuel_strategist"
    assert f.findings == []
    assert "营养评估失败" in f.summary
    assert "error" in f.raw


# ───────────── 空 twin run ─────────────

def test_empty_twin_run_only_hydration_and_next_meal():
    """无热量/蛋白/补剂/基因 数据 → 仍能产出 hydration + next_meal."""
    s = FuelStrategistSpecialist()
    f = s.run(_empty_twin(), {})
    types = [x.get("type") for x in f.findings]
    assert "hydration" in types
    assert "next_meal" in types
    # 无热量数据 → energy/protein 不应出现
    assert "energy" not in types
    assert "protein" not in types
    # summary 应是 "数据暂缺" 兜底
    assert "数据暂缺" in f.summary or "水" in f.summary


def test_does_not_apply_to_pure_safety_intent():
    s = FuelStrategistSpecialist()
    # "心率" 是 safety 关键词, 不含 fuel 关键词
    intent = classify_intent("心率不齐怎么办")
    if "fuel" in intent.categories:
        pytest.skip("intent 已含 fuel, 此测试不适用")
    # 没饮食 / TDEE 数据, 兜底也不应触发
    t = _empty_twin()
    assert s.applies_to(intent, t) is False


# ───────────── summary 字符串 ─────────────

def test_summary_contains_all_three_buckets():
    s = FuelStrategistSpecialist()
    f = s.run(_rich_twin(), {})
    # rich_twin: 1800/2700 kcal, 蛋白 110/130g (training_load=350 → factor 1.8), 水 1500/2000
    assert "热量" in f.summary
    assert "蛋白" in f.summary
    assert "水" in f.summary


# ───────────── 蛋白目标边界 ─────────────

def test_protein_target_at_boundary_200():
    """training_load_7d 正好 200 走低活动 1.4."""
    assert _protein_target_g(70.0, 200) == 70.0 * 1.4


def test_protein_target_just_above_200():
    assert _protein_target_g(70.0, 201) == 70.0 * 1.8
