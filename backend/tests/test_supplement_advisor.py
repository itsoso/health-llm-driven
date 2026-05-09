"""SupplementAdviecialist 单测.

覆盖:
- applies_to: fuel/labs 意图 + 关键字
- HFE C282Y 纯合 → 硬阻断铁
- MTHFR + APOE + COMT → 3-4 条推荐
- eGFR < 30 → 镁降级 warning
- 华法林 → K2 禁忌, 不进列表
- statin → CoQ10 触发
- >5 条推荐 → 降级保留 top5
- 空 twin → data_gap 提示
- 异常兜底
- ProposedCard 生成 (12 周验证)
"""
from __future__ import annotations

from datetime import datetime

from app.agents.supplement_advisor import SupplementAdvisorSpecialist
from app.orchestrator.intent import classify_intent
from app.twin.schema import (
    GeneticContext,
    HealthTwin,
    LabsContext,
    MedicationState,
    TwinMeta,
)


def _empty_twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))


def _twin_with_genes(variants: list) -> HealthTwin:
    t = _empty_twin()
    t.genetic = GeneticContext(has_profile=True, total_variants=len(variants), nutrition_variants=variants)
    return t


# ─────────── applies_to ───────────

def test_applies_to_by_fuel_intent_with_gene():
    s = SupplementAdvisorSpecialist()
    intent = classify_intent("我应该吃什么补剂")  # fuel keyword
    t = _twin_with_genes([{"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"}])
    assert s.applies_to(intent, t) is True


def test_applies_to_by_keyword_supplement():
    s = SupplementAdvisorSpecialist()
    intent = classify_intent("要不要补维生素D")
    t = _empty_twin()  # 没有基因也 ok, 关键字匹配
    assert s.applies_to(intent, t) is True


def test_not_applies_to_pure_safety_no_data():
    s = SupplementAdvisorSpecialist()
    intent = classify_intent("心率不齐怎么办")
    t = _empty_twin()
    assert s.applies_to(intent, t) is False


# ─────────── HFE 硬阻断 ───────────

def test_hfe_homozygous_hard_blocks_iron():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "HFE", "genotype": "C282Y/C282Y", "result_label": "high_risk"},
    ])
    f = s.run(t, {})
    blocks = [x for x in f.findings if x.get("type") == "hard_block"]
    assert len(blocks) == 1
    assert "铁" in blocks[0]["supplement"]
    assert "血色病" in blocks[0]["reason"]
    warnings = [x for x in f.findings if x.get("type") == "warning"]
    assert any("血色病" in w["message"] for w in warnings)


def test_hfe_heterozygous_not_blocking():
    """C282Y/H63D 杂合不应硬阻断 (当前实现只阻断纯合)."""
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "HFE", "genotype": "C282Y/H63D", "result_label": "high_risk"},
    ])
    f = s.run(t, {})
    blocks = [x for x in f.findings if x.get("type") == "hard_block"]
    assert len(blocks) == 0


# ─────────── MTHFR + APOE + COMT 组合 ───────────

def test_mthfr_triggers_methylfolate_and_b12():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"},
    ])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "mthfr_methylfolate" in ids
    assert "mthfr_b12" in ids


def test_apoe_e4_triggers_omega3():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "APOE", "genotype": "E4/E4", "result_label": "high_risk"},
    ])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "apoe_omega3" in ids


def test_comt_slow_triggers_magnesium():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "COMT", "genotype": "GG", "result_label": "慢型"},
    ])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "comt_magnesium" in ids


# ─────────── eGFR 低 → 镁降级 ───────────

def test_low_egfr_downgrades_magnesium():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "COMT", "genotype": "GG", "result_label": "慢型"},
    ])
    t.labs = LabsContext(egfr=25)
    f = s.run(t, {})
    mg_rec = next(x for x in f.findings if x.get("id") == "comt_magnesium")
    assert "warning" in mg_rec
    assert "肾" in mg_rec["warning"]


# ─────────── 华法林 → K2 禁忌 ───────────

def test_warfarin_blocks_k2_but_keeps_d3():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"},
    ])
    t.medication = MedicationState(
        active_meds=[{"name": "华法林", "dose": "2.5mg"}], has_any=True,
    )
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "vdr_vitamin_d" in ids
    assert "vdr_vitamin_k2" not in ids
    d_rec = next(x for x in f.findings if x.get("id") == "vdr_vitamin_d")
    assert "K2" in d_rec.get("warning", "")


# ─────────── statin → CoQ10 ───────────

def test_statin_triggers_coq10():
    s = SupplementAdvisorSpecialist()
    t = _empty_twin()
    t.medication = MedicationState(
        active_meds=[{"name": "阿托伐他汀", "dose": "10mg"}], has_any=True,
    )
    # 需要 trigger applies_to — 给 labs 异常
    t.labs = LabsContext(flagged_abnormal=[{"item_name": "LDL", "value": 180}])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "sod2_coq10" in ids
    rec = next(x for x in f.findings if x.get("id") == "sod2_coq10")
    assert "他汀" in rec["reason"]


# ─────────── >5 推荐降级 ───────────

def test_over_5_recommendations_trimmed_to_top5():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"},
        {"gene_name": "APOE", "genotype": "E4/E4", "result_label": "high_risk"},
        {"gene_name": "COMT", "genotype": "GG", "result_label": "慢型"},
        {"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"},
        {"gene_name": "SOD2", "genotype": "CC", "result_label": "reduced"},
        {"gene_name": "FADS1", "genotype": "TT", "result_label": "reduced"},
    ])
    f = s.run(t, {})
    recs = [x for x in f.findings if x.get("type") == "supplement_rec"]
    assert len(recs) <= 5
    warnings = [x for x in f.findings if x.get("type") == "warning"]
    assert any("依从性" in w["message"] for w in warnings)


# ─────────── 空 twin → data_gap ───────────

def test_empty_twin_returns_data_gap():
    s = SupplementAdvisorSpecialist()
    f = s.run(_empty_twin(), {})
    gaps = [x for x in f.findings if x.get("type") == "data_gap"]
    assert len(gaps) == 1
    assert "上传" in gaps[0]["message"]
    assert "健康参考信息" in gaps[0]["disclaimer"]


# ─────────── 异常兜底 ───────────

def test_run_catches_internal_exception():
    s = SupplementAdvisorSpecialist()
    bad = _empty_twin()

    class _Bomb:
        def __getattr__(self, name):
            raise RuntimeError(f"boom: {name}")

    bad.__dict__["genetic"] = _Bomb()
    f = s.run(bad, {})
    assert f.specialist_name == "supplement_advisor"
    assert "补剂建议失败" in f.summary
    assert f.raw.get("disclaimer")


# ─────────── ProposedCard (12 周) ───────────

def test_proposed_card_12_weeks_with_mthfr():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"},
    ])
    f = s.run(t, {})
    assert len(f.proposed_cards) == 1
    card = f.proposed_cards[0]
    assert card.verification_days == 84
    assert card.card_type == "plan"
    assert card.metric_key == "hcy"
    assert "免责" in card.content or "参考" in card.content


def test_no_proposed_card_if_hard_block_present():
    """HFE 硬阻断时不应给 N-of-1 建议 (先解决铁过载)."""
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "HFE", "genotype": "C282Y/C282Y", "result_label": "high_risk"},
        {"gene_name": "MTHFR", "genotype": "TT", "result_label": "reduced"},
    ])
    f = s.run(t, {})
    # 硬阻断下仍可有 MTHFR 推荐, 但不出 plan card
    assert len(f.proposed_cards) == 0


# ─────────── Summary 文案 ───────────

def test_summary_contains_disclaimer_when_no_rec():
    s = SupplementAdvisorSpecialist()
    f = s.run(_empty_twin(), {})
    # 空 twin 时 summary 带免责
    assert "健康参考" in f.summary or "参考信息" in f.summary


def test_summary_flags_blocks():
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "HFE", "genotype": "C282Y/C282Y", "result_label": "high_risk"},
    ])
    f = s.run(t, {})
    assert "⛔" in f.summary
