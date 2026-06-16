"""相关位点计数 + 方向 (Phase 0: 伪 PRS 降级 + 子串匹配修复)。

旧 genetic_prs 把手写序数权重伪装成"多基因风险评分 + 人群百分位",
且用 `pattern in geno` 子串匹配 (ε2 命中 ε2/ε4)。本测试锁定:
1. 对外输出不含 percentile / risk_level / 任何分数字段
2. 输出含 loci_matched / overall_direction + 降级 disclaimer
3. 精确等位匹配:ε2/ε2 不会被 ε4/ε4 的"4"或其他基因型误配
"""

from app.services.genetic_prs import (
    DISCLAIMER,
    compute_all_locus_summaries,
    compute_locus_summary,
)


# ─────────────────────── 输出 shape:不再是 PRS ──────────────────


def test_no_percentile_or_score_fields():
    """降级后绝不输出伪人群百分位 / 风险等级 / 分数。"""
    variants = [{"gene_name": "APOE", "genotype": "ε4/ε4"}]
    out = compute_locus_summary(variants, "cardiovascular")
    assert out is not None
    for forbidden in ("percentile", "risk_level", "raw_score", "max_possible", "prs_score"):
        assert forbidden not in out, f"降级后不应再输出 {forbidden}"


def test_outputs_count_and_direction_with_disclaimer():
    variants = [{"gene_name": "APOE", "genotype": "ε4/ε4"}]
    out = compute_locus_summary(variants, "cardiovascular")
    assert out["domain"] == "cardiovascular"
    assert out["loci_matched"] == 1
    assert out["overall_direction"] == "raise"
    assert out["raise_count"] == 1
    assert out["lower_count"] == 0
    assert out["disclaimer"] == DISCLAIMER
    assert "非人群校准" in out["disclaimer"]
    assert "非诊断" in out["disclaimer"]
    # 每条位点带方向标签
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    assert apoe["direction"] == "raise"


def test_protective_direction_is_lower():
    """保护性等位 (ε2/ε2 方向为负) → lower,且不应被 ε4 误配成 raise。"""
    variants = [{"gene_name": "APOE", "genotype": "ε2/ε2"}]
    out = compute_locus_summary(variants, "cardiovascular")
    assert out["overall_direction"] == "lower"
    assert out["lower_count"] == 1
    assert out["raise_count"] == 0
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    assert apoe["direction"] == "lower"


# ─────────────────────── 子串匹配 bug 修复 ──────────────────


def test_exact_match_e2_not_confused_with_e4():
    """ε2/ε3 不能命中 ε3/ε4 (旧子串匹配 'ε3' in 'ε3/ε4' 会误配)。"""
    variants = [{"gene_name": "APOE", "genotype": "ε2/ε3"}]
    out = compute_locus_summary(variants, "cardiovascular")
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    # ε2/ε3 在方向表里为 -0.5 → lower,绝不应被当成 ε3/ε4 (raise)
    assert apoe["direction"] == "lower"


def test_unknown_genotype_marked_unmatched_not_matched():
    """方向表里没有的基因型 → unmatched,不计入命中/方向。"""
    variants = [{"gene_name": "APOE", "genotype": "ε99/ε99"}]
    out = compute_locus_summary(variants, "cardiovascular")
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    assert apoe["direction"] == "unknown"
    assert apoe.get("note") == "unmatched"
    assert out["loci_matched"] == 0
    assert out["loci_tested"] == 0


def test_neutral_genotype_does_not_count_as_matched():
    """中性等位 (方向 0,如 ε3/ε3) 计入 tested 但不计入 matched/方向。"""
    variants = [{"gene_name": "APOE", "genotype": "ε3/ε3"}]
    out = compute_locus_summary(variants, "cardiovascular")
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    assert apoe["direction"] == "neutral"
    assert out["loci_matched"] == 0
    assert out["loci_tested"] == 1
    assert out["overall_direction"] == "neutral"


def test_genotype_whitespace_normalized():
    """'ε3 / ε4' 这类带空格的格式应仍精确匹配 ε3/ε4。"""
    variants = [{"gene_name": "APOE", "genotype": "ε3 / ε4"}]
    out = compute_locus_summary(variants, "cardiovascular")
    apoe = next(l for l in out["loci"] if l["gene"] == "APOE")
    assert apoe["direction"] == "raise"


# ─────────────────────── 聚合 + 边界 ──────────────────


def test_unknown_domain_returns_none():
    assert compute_locus_summary([{"gene_name": "APOE", "genotype": "ε4/ε4"}], "nonexistent") is None


def test_no_matching_variants_returns_none():
    assert compute_locus_summary([{"gene_name": "ZZZ", "genotype": "AA"}], "cardiovascular") is None


def test_compute_all_aggregates_multiple_domains():
    variants = [
        {"gene_name": "APOE", "genotype": "ε4/ε4"},
        {"gene_name": "FTO", "genotype": "AA"},
        {"gene_name": "TCF7L2", "genotype": "TT"},
    ]
    out = compute_all_locus_summaries(variants)
    assert "cardiovascular" in out
    assert "diabetes" in out
    assert "obesity" in out
    # 每个领域都带降级 disclaimer
    assert all("disclaimer" in v for v in out.values())
