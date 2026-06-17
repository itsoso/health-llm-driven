"""Versioned access layer for the static genetic knowledge registry.

The current registry still reuses the historical 52-SNP dictionary while adding
metadata needed by import, report, and prediction code. New code should import
from this module instead of reaching into the API router.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional


REGISTRY_VERSION = "genetic-known-snps-v2-2026-05-16"


def _load_legacy_known_snps() -> Dict[str, Dict[str, Any]]:
    from app.api.genetic_data import KNOWN_SNPS as legacy_known_snps

    return legacy_known_snps


KNOWN_SNPS = _load_legacy_known_snps()


_VARIANT_TYPES = {
    "rs5030655": "indel_proxy",
    "rs4646994": "structural_indel",
    "rs1265181": "hla_proxy_marker",  # HLA-B*58:01 — allopurinol SJS/TEN
    # rs1061235 is the consumer-chip tag SNP for HLA-A*31:01 (carbamazepine
    # SCAR) — a tier0/pharmgkb_1a lethal allele, just like rs1265181. It is a
    # genotyping proxy, NOT the allele itself, so a "negative" cannot be read as
    # "no risk". Tag it so the formatter keeps the proxy caveat (is_proxy_variant)
    # after the tier0-HLA grade promotion — otherwise only one of the two tier0
    # HLA tag SNPs would surface the "阴性不代表无风险" guardrail.
    "rs1061235": "hla_proxy_marker",  # HLA-A*31:01 — carbamazepine SCAR
    "rs429358": "haplotype_component",
}

# Consumer-chip (genotyping, not sequencing) proxy variant types: any "negative"
# on these cannot be read as "no risk". Surface as proxy_uncertain regardless of tier.
_PROXY_VARIANT_TYPES = frozenset({"indel_proxy", "structural_indel", "hla_proxy_marker"})


# ─────────────────────────── Two-dimensional classification ─────────────────
#
# Phase 1 (design-genetic-interpretation-first-principles.md §3): overlay a new,
# *orthogonal* "actionability" axis on top of the existing
# gene_knowledge_audit.TIER_DEFINITIONS tiers — DO NOT invent a third naming
# system. Tier→gene membership is owned by the audit; we read it as the single
# source of truth and statically map each tier to (actionability, evidence_grade).
# Nothing here is decided by an LLM.
#
#   actionability ∈ {act, risk_stratify, de_emphasize}
#   evidence_grade ∈ {cpic_a, pharmgkb_1a, clinvar_path_confirm, clinvar_likely,
#                     gwas_association, proxy_uncertain}
#
# Note on HFE: the doc §3 ACT table lists HFE under high-penetrance monogenic,
# but the authoritative code (gene_knowledge_audit.TIER_DEFINITIONS) places HFE
# in tier1_lab_anchored. Per the "以代码为准 / 别另造第三套命名" directive we honor
# the audit tier membership → HFE classifies as risk_stratify. If product later
# wants HFE in ACT, move it in TIER_DEFINITIONS and this mapping follows for free.

Actionability = str  # "act" | "risk_stratify" | "de_emphasize"
EvidenceGrade = str  # see set above

# HLA star-alleles carry FDA-label / PharmGKB 1A pharmacogenomic weight rather
# than a single CPIC dosing guideline; grade them pharmgkb_1a within tier0.
_TIER0_PHARMGKB_GENES = frozenset({"HLA-A*31:01", "HLA-B*15:02", "HLA-B*58:01"})

# tier1 split: ALDH2 is a Mendelian-randomization-grade exposure marker with
# strong epidemiology, the rest are likely/association-grade risk stratifiers.
_TIER1_CLINVAR_LIKELY_GENES = frozenset({"APOE", "MTHFR", "HFE", "ALDH2"})

_TIER_ACTIONABILITY: dict[str, Actionability] = {
    "tier0_pharmacogenomics": "act",
    "tierx_confirmation_only": "act",
    "tier1_lab_anchored": "risk_stratify",
    "tier2_lifestyle": "de_emphasize",
}

_DEFAULT_CLASSIFICATION: tuple[Actionability, EvidenceGrade] = (
    "de_emphasize",
    "gwas_association",
)


def _gene_to_tier() -> Dict[str, str]:
    """Build a normalized gene→tier_key lookup from the audit's TIER_DEFINITIONS."""
    from app.services.gene_knowledge_audit import TIER_DEFINITIONS

    mapping: Dict[str, str] = {}
    for tier_key, tier_def in TIER_DEFINITIONS.items():
        for gene in tier_def.get("genes", []):
            mapping[_norm_gene(gene)] = tier_key
    return mapping


# HLA star-allele forms drift between sources: KNOWN_SNPS stores `HLA-B*5801`
# (no colon) while TIER_DEFINITIONS / PharmGKB use `HLA-B*58:01` (colon-delimited
# field:allele). Without canonicalization the gene→tier lookup misses and a
# lethal pharmacogenomic allele (HLA-B*58:01 → allopurinol SJS/TEN) silently
# falls through to the de_emphasize default. Normalize ALL HLA star-alleles, not
# just one hard-coded id, so every chip vendor spelling maps to one tier key.
#
# Canonical form: 4 trailing digits after `*` become `NN:NN` (e.g. *5801→*58:01,
# *1502→*15:02, *3101→*31:01, *5701→*57:01). Already-colon'd or non-4-digit
# allele strings (e.g. HLA-DQ8, HLA-DRB1*04) are left untouched.
_HLA_NO_COLON_RE = re.compile(r"^(HLA-[A-Z0-9]+)\*(\d{2})(\d{2})$")


def _normalize_hla_allele(gene: str) -> str:
    m = _HLA_NO_COLON_RE.match(gene)
    if m:
        return f"{m.group(1)}*{m.group(2)}:{m.group(3)}"
    return gene


def _norm_gene(value: Any) -> str:
    return _normalize_hla_allele(str(value or "").strip().upper())


def _looks_like_rsid(value: str) -> bool:
    return value[:2].lower() == "rs" and value[2:].isdigit()


def _resolve_gene(rsid_or_gene: str, gene_name: Optional[str] = None) -> str:
    """Resolve an rsid to its gene symbol, or pass through a gene name.

    When the primary key is an rsid that is NOT in KNOWN_SNPS (e.g. a
    sequencing-confirmed BRCA/HFE variant whose rsid never appears on the
    consumer chip), fall back to the explicit gene_name rather than treating the
    raw rsid string as a gene symbol — otherwise a confirmed BRCA1 variant would
    silently classify as the de_emphasize default.
    """
    key = str(rsid_or_gene or "").strip()
    if not key:
        return _norm_gene(gene_name) if gene_name else ""
    # rsid path
    snp = KNOWN_SNPS.get(key) or KNOWN_SNPS.get(key.lower())
    if snp:
        return _norm_gene(snp.get("gene"))
    # Unknown rsid → do not mistake it for a gene symbol; use gene_name fallback.
    if _looks_like_rsid(key):
        if gene_name:
            return _norm_gene(gene_name)
        return ""
    return _norm_gene(key)


def _variant_type_for(rsid_or_gene: str) -> Optional[str]:
    key = str(rsid_or_gene or "").strip().lower()
    return _VARIANT_TYPES.get(key)


def is_proxy_variant(rsid_or_gene: str) -> bool:
    """True if this locus is a consumer-chip proxy (indel / structural / HLA tag).

    The formatter uses this to keep the "negative ≠ no risk" caveat on proxy
    loci even when the (actionability, evidence_grade) was promoted above
    proxy_uncertain — e.g. tier0 HLA pharmgkb_1a alleles.
    """
    return _variant_type_for(rsid_or_gene) in _PROXY_VARIANT_TYPES


def classify_variant(
    rsid_or_gene: str, gene_name: Optional[str] = None
) -> tuple[Actionability, EvidenceGrade]:
    """Statically map an rsid OR gene symbol to (actionability, evidence_grade).

    Pure, deterministic, table-driven — never asks an LLM. Tier membership comes
    from gene_knowledge_audit.TIER_DEFINITIONS so the two systems can't drift.

    `gene_name` is an optional fallback used when the primary key is an rsid that
    is not on the consumer chip (KNOWN_SNPS) — e.g. a sequencing-confirmed
    BRCA/HFE variant — so it still resolves to the right tier instead of the
    de_emphasize default.

    Consumer-chip proxy loci (indel/structural/HLA-proxy in _VARIANT_TYPES) are
    forced to evidence_grade=proxy_uncertain regardless of tier — a "negative" on
    a genotyping proxy never means "no risk". The sole exception is tier0 HLA
    pharmacogenomic alleles, which keep their pharmgkb_1a grade (a lethal allele
    must not be softened); their proxy caveat is surfaced via is_proxy_variant.
    """
    gene = _resolve_gene(rsid_or_gene, gene_name)
    tier = _gene_to_tier().get(gene)
    actionability = _TIER_ACTIONABILITY.get(tier or "", _DEFAULT_CLASSIFICATION[0])
    is_proxy = _variant_type_for(rsid_or_gene) in _PROXY_VARIANT_TYPES

    # Tier0 HLA pharmacogenomic alleles (HLA-B*58:01 / HLA-B*15:02 / HLA-A*31:01)
    # are FDA-label / PharmGKB-1A drug-safety red lines. Even though the chip
    # carries them as proxy tag SNPs, the grade must NOT be softened to
    # proxy_uncertain — that is exactly what masked a lethal allele as noise.
    # The proxy "negative ≠ no risk" caveat for these is surfaced by the
    # formatter (is_proxy_variant) instead, so it isn't lost.
    if tier == "tier0_pharmacogenomics" and gene in _TIER0_PHARMGKB_GENES:
        return "act", "pharmgkb_1a"

    # Consumer-chip hard guardrail: proxy genotyping cannot confirm/exclude.
    if is_proxy:
        return actionability, "proxy_uncertain"

    if tier == "tier0_pharmacogenomics":
        return "act", "cpic_a"
    if tier == "tierx_confirmation_only":
        return "act", "clinvar_path_confirm"
    if tier == "tier1_lab_anchored":
        if gene in _TIER1_CLINVAR_LIKELY_GENES:
            return "risk_stratify", "clinvar_likely"
        return "risk_stratify", "gwas_association"
    if tier == "tier2_lifestyle":
        return "de_emphasize", "gwas_association"
    # Unknown / unmapped locus → safest bucket: de-emphasize, weak association.
    return _DEFAULT_CLASSIFICATION


# Forced disclaimer prefix for de_emphasize-grade variants so weak LLMs cannot
# render a population OR≈1.1 association as an individual deterministic verdict.
DE_EMPHASIZE_PREFIX = "群体弱关联,个体无预测力,非诊断"

PROXY_UNCERTAIN_SUFFIX = "(消费级芯片 proxy 位点,阴性不代表无风险)"


_CLAIM_BOUNDARIES = {
    "drug_sensitivity": {
        "claim_boundary": "pharmacogenetic_screening",
        "message": "药物相关基因只能作为用药前讨论材料，不得建议停药、换药或调整剂量。",
        "requires_clinician": True,
    },
    "disease_risk": {
        "claim_boundary": "screening_association",
        "message": "疾病相关基因不是诊断，必须结合体检、家族史、症状和医生判断。",
        "requires_clinician": False,
    },
    "cognition": {
        "claim_boundary": "weak_association",
        "message": "认知相关位点只能作为低置信度相关性解释，不能预测个人能力或教育结果。",
        "requires_clinician": False,
    },
    "personality": {
        "claim_boundary": "weak_association",
        "message": "人格/情绪相关位点只能作为低置信度相关性解释，不能给个人贴标签。",
        "requires_clinician": False,
    },
    "height_trait": {
        "claim_boundary": "exploratory_polygenic_marker",
        "message": "身高相关位点只能作为低置信度 marker 计数，不能换算成厘米数或替代全量 PRS。",
        "requires_clinician": False,
    },
    "education_trait": {
        "claim_boundary": "exploratory_social_trait_association",
        "message": "教育相关位点只能展示群体弱相关，不能预测个人是否能上大学或用于任何评价决策。",
        "requires_clinician": False,
    },
}


def get_known_snps() -> Dict[str, Dict[str, Any]]:
    return KNOWN_SNPS


def get_snp_metadata(rsid: str) -> Dict[str, Any]:
    snp = KNOWN_SNPS[rsid]
    boundary = _CLAIM_BOUNDARIES.get(snp["category"], {
        "claim_boundary": "wellness_screening",
        "message": "该结果是消费级基因筛查提示，不代表确定结论。",
        "requires_clinician": False,
    })
    return {
        "rsid": rsid,
        "registry_version": REGISTRY_VERSION,
        "variant_type": _VARIANT_TYPES.get(rsid, "snp"),
        "evidence_level": "screening",
        **boundary,
    }


def iter_known_rsids() -> Iterable[str]:
    return KNOWN_SNPS.keys()


def missing_reason_for_rsid(rsid: str, raw_seen: Optional[set[str]] = None) -> str:
    meta = get_snp_metadata(rsid)
    if meta["variant_type"] in {"structural_indel", "indel_proxy", "hla_proxy_marker"}:
        return "unsupported_or_requires_confirmation"
    if raw_seen is not None and rsid not in raw_seen:
        return "not_present_in_raw_file"
    return "not_mapped"
