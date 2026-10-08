"""HFE C282Y (rs1800562) 核苷酸基因型识别 — 铁补剂硬阻断不得漏判.

rs1800562 正链 G>A (风险等位 A; 反链 C>T)。消费级芯片/化验单常以核苷酸
写基因型 ("AA" / "A/A" / "aa" / "A A"),旧实现只认 "C282Y/C282Y" 或
"TT"/"YY",导致纯合用户的铁补剂硬阻断静默不触发。

不变量:
- 核苷酸纯合 (AA, 及反链 TT) + rsid=rs1800562 → 硬阻断
- 杂合 (GA/AG/G/A) → 与 "C282Y/wt" 路径一致 (不硬阻断)
- GG / 未知字符串 / 无 rsid 的核苷酸 → 保持旧行为, 不扩大误阻断
- 旧实现会阻断的基因型继续阻断

全部为合成数据,无 PHI。
"""
from __future__ import annotations

from datetime import datetime

import pytest

from app.agents.supplement_advisor import SupplementAdvisorSpecialist
from app.services.system_knowledge_service import _system_kb_genetics_from_health_twin
from app.twin.schema import GeneticContext, HealthTwin, TwinMeta

C282Y = "rs1800562"
H63D = "rs1799945"
S65C = "rs1800730"


def _twin(variants: list, bucket: str = "nutrition_variants") -> HealthTwin:
    t = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    t.genetic = GeneticContext(has_profile=True, total_variants=len(variants), **{bucket: variants})
    return t


def _blocks(t: HealthTwin) -> list:
    f = SupplementAdvisorSpecialist().run(t, {})
    return [x for x in f.findings if x.get("type") == "hard_block"]


def _hfe(genotype, rsid=C282Y, **extra) -> dict:
    v = {"gene_name": "HFE", "genotype": genotype}
    if rsid is not None:
        v["rsid"] = rsid
    v.update(extra)
    return v


# ── 纯合 → 硬阻断 ──

@pytest.mark.parametrize("genotype", ["AA", "A/A", "aa", "A A", "a/a", " A|A ", "TT", "T/T", "A;A", "(A;A)", "A,A", "A-A"])
def test_nucleotide_homozygous_c282y_blocks_iron(genotype):
    blocks = _blocks(_twin([_hfe(genotype)]))
    assert len(blocks) == 1
    assert "铁" in blocks[0]["supplement"]


@pytest.mark.parametrize("bucket", ["risk_variants", "drug_sensitivity", "recovery_variants"])
def test_homozygous_blocks_regardless_of_bucket(bucket):
    assert len(_blocks(_twin([_hfe("A/A")], bucket=bucket))) == 1


def test_homozygous_blocks_without_risk_label():
    """即便上游没标 risk_level/result_label,纯合核苷酸也必须阻断."""
    assert len(_blocks(_twin([_hfe("AA", risk_level="info", result_label="")]))) == 1


def test_rsid_case_insensitive():
    assert len(_blocks(_twin([_hfe("AA", rsid="RS1800562")]))) == 1


def test_homozygous_c282y_not_shadowed_by_earlier_h63d_variant():
    """H63D 杂合排在前面时,不能因"只看第一条 HFE 命中"而漏掉 C282Y 纯合."""
    t = _twin([
        _hfe("CG", rsid=H63D, risk_level="中风险", result_label="铁蓄积风险轻度增高"),
        _hfe("A/A"),
    ])
    assert len(_blocks(t)) == 1


# ── 杂合 → 与 "C282Y/wt" 路径一致 (不硬阻断) ──

@pytest.mark.parametrize("genotype", ["GA", "AG", "G/A", "a/g", "CT", "TC", "(G;A)"])
def test_nucleotide_heterozygous_matches_c282y_wt_path(genotype):
    reference = _blocks(_twin([_hfe("C282Y/wt", rsid=None, result_label="high_risk")]))
    assert reference == []
    assert _blocks(_twin([_hfe(genotype, risk_level="medium")])) == reference


# ── 野生型 / 未知 → 不阻断 (不扩大误阻断) ──

@pytest.mark.parametrize("genotype", ["GG", "G/G", "gg", "CC"])
def test_wildtype_no_block(genotype):
    assert _blocks(_twin([_hfe(genotype)])) == []


@pytest.mark.parametrize("genotype", ["", "--", "A", "AAA", "NN", "A/A/G", "未检出", None])
def test_unknown_strings_no_block(genotype):
    assert _blocks(_twin([_hfe(genotype)])) == []


def test_nucleotide_aa_without_rsid_keeps_legacy_behaviour():
    """无 rsid 时无法确认是 C282Y 位点 (如 S65C rs1800730 的 AA 为野生型) → 不新增阻断."""
    assert _blocks(_twin([_hfe("AA", rsid=None)])) == []


def test_other_hfe_locus_aa_not_blocked():
    """S65C (rs1800730, A>T) 的 AA 是野生型, 不得误判为 C282Y 纯合."""
    assert _blocks(_twin([_hfe("AA", rsid=S65C)])) == []


# ── 旧阻断不丢 ──

@pytest.mark.parametrize("variant", [
    {"gene_name": "HFE", "genotype": "C282Y/C282Y", "result_label": "high_risk"},
    {"gene_name": "HFE", "genotype": "c282y/c282y"},
    {"gene_name": "HFE", "genotype": "TT", "result_label": "high_risk"},
    {"gene_name": "HFE", "genotype": "YY", "risk_level": "高风险"},
])
def test_legacy_blocking_genotypes_still_block(variant):
    assert len(_blocks(_twin([variant]))) == 1


def test_legacy_c282y_string_not_shadowed_by_earlier_h63d_variant():
    t = _twin([
        _hfe("CG", rsid=H63D, risk_level="中风险"),
        {"gene_name": "HFE", "genotype": "C282Y/C282Y", "result_label": "high_risk"},
    ])
    assert len(_blocks(t)) == 1


# ── System KB 基因事实: twin.genetics.HFE_rs1800562 == 'AA' ──

@pytest.mark.parametrize("genotype,expected", [
    ("AA", "AA"), ("A/A", "AA"), ("a a", "AA"), ("TT", "AA"),
    ("G/A", "GA"), ("AG", "GA"), ("GG", "GG"),
])
def test_kb_fact_canonicalises_c282y_genotype(genotype, expected):
    facts = _system_kb_genetics_from_health_twin(_twin([_hfe(genotype)]))
    assert facts["HFE_rs1800562"] == expected


def test_kb_fact_not_overwritten_by_other_hfe_locus():
    facts = _system_kb_genetics_from_health_twin(_twin([_hfe("A/A"), _hfe("CG", rsid=H63D)]))
    assert facts["HFE_rs1800562"] == "AA"


def test_kb_fact_unknown_genotype_kept_as_before():
    facts = _system_kb_genetics_from_health_twin(_twin([_hfe("C282Y/C282Y", rsid=None)]))
    assert facts["HFE_rs1800562"] == "C282Y/C282Y"
