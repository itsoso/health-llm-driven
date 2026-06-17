"""SupplementAdviecialist 单测.

覆盖:
- applies_to: fuel/labs 意图 + 关键字
- HFE C282Y 纯合 → 硬阻断铁
- MTHFR + APOE → 2-3 条推荐
- 镁: 主观睡眠/焦虑主诉 或 低镁化验触发 (非 COMT 基因门控)
- COMT 基因型单独不再触发镁 (纠正:无 COMT×镁→HRV/睡眠 交互证据)
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
    AcuteHealthState,
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


# ─────────── 镁: 症状/化验触发, 非 COMT 基因门控 ───────────

def test_sleep_complaint_triggers_magnesium():
    """主观睡眠/焦虑主诉 → 镁 (genotype-independent 群体主效应)."""
    s = SupplementAdvisorSpecialist()
    t = _empty_twin()
    t.acute = AcuteHealthState(recent_symptoms=["最近失眠,入睡困难"])
    f = s.run(t, {})
    rec = next(x for x in f.findings if x.get("id") == "magnesium_sleep")
    # reason 是 genotype-independent 生理依据, 不再归因 COMT 慢代谢
    assert "COMT" not in rec["reason"]
    assert "GABA" in rec["reason"] or "副交感" in rec["reason"]
    assert rec.get("gene") is None


def test_low_magnesium_lab_triggers_magnesium():
    """低镁化验 → 镁 (沿用 VDR/低-VD 的 lab 触发模式)."""
    s = SupplementAdvisorSpecialist()
    t = _empty_twin()
    t.labs = LabsContext(flagged_abnormal=[{"item_name": "血清镁", "value": 0.6}])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "magnesium_sleep" in ids


def test_comt_genotype_alone_does_not_trigger_magnesium():
    """纠正后的核心行为:COMT 慢型基因型单独不再推荐镁.

    无 COMT×镁→HRV/睡眠 的基因-环境交互证据; COMT 单 SNP 属 DE-EMPHASIZE 层,
    不驱动补剂结论 (见 gene_config.py:224)。
    """
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "COMT", "genotype": "GG", "result_label": "慢型"},
    ])
    f = s.run(t, {})
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "magnesium_sleep" not in ids
    assert "comt_magnesium" not in ids  # 旧 id 也不应残留


# ─────────── eGFR 低 → 镁降级 ───────────

def test_low_egfr_downgrades_magnesium():
    s = SupplementAdvisorSpecialist()
    t = _empty_twin()
    t.acute = AcuteHealthState(recent_symptoms=["失眠"])
    t.labs = LabsContext(egfr=25)
    f = s.run(t, {})
    mg_rec = next(x for x in f.findings if x.get("id") == "magnesium_sleep")
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
        {"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"},
        {"gene_name": "SOD2", "genotype": "CC", "result_label": "reduced"},
        {"gene_name": "FADS1", "genotype": "TT", "result_label": "reduced"},
    ])
    # 镁现由症状触发 (非基因), 加一条睡眠主诉让它进入候选池
    t.acute = AcuteHealthState(recent_symptoms=["失眠"])
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


# ─────────── 肾结石 + VDR → 自动降 VD 剂量 (memory bug 修复 2026-05-12) ───────────

def test_kidney_stone_history_downscales_vitamin_d():
    """memory feedback: itsoso 肾结石 3mm 史 + VDR + 5000IU 长期有钙沉积风险.
    应自动降 dose 到 1000 IU + warning."""
    from app.twin.schema import ChronicConditionState
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"},
    ])
    t.chronic = ChronicConditionState(active_conditions=["左肾结石", "过敏性鼻炎"])
    f = s.run(t, {})
    d_rec = next((x for x in f.findings if x.get("id") == "vdr_vitamin_d"), None)
    assert d_rec is not None
    assert "1000 IU" in d_rec["dose"]
    assert "肾结石" in d_rec.get("warning", "")
    # 肾结石史也不加 K2
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "vdr_vitamin_k2" not in ids


def test_no_kidney_stone_keeps_normal_vitamin_d_dose():
    """不带肾结石史 → dose 维持 2000-4000 IU + 加 K2."""
    s = SupplementAdvisorSpecialist()
    t = _twin_with_genes([
        {"gene_name": "VDR", "genotype": "TT", "result_label": "reduced"},
    ])
    f = s.run(t, {})
    d_rec = next((x for x in f.findings if x.get("id") == "vdr_vitamin_d"), None)
    assert d_rec is not None
    assert "2000-4000 IU" in d_rec["dose"]
    assert "肾结石" not in d_rec.get("warning", "")
    ids = {x.get("id") for x in f.findings if x.get("type") == "supplement_rec"}
    assert "vdr_vitamin_k2" in ids
