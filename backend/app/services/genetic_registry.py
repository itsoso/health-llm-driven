"""Versioned access layer for the static genetic knowledge registry.

The current registry still reuses the historical 52-SNP dictionary while adding
metadata needed by import, report, and prediction code. New code should import
from this module instead of reaching into the API router.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional


REGISTRY_VERSION = "genetic-known-snps-v2-2026-05-16"


def _load_legacy_known_snps() -> Dict[str, Dict[str, Any]]:
    from app.api.genetic_data import KNOWN_SNPS as legacy_known_snps

    return legacy_known_snps


KNOWN_SNPS = _load_legacy_known_snps()


_VARIANT_TYPES = {
    "rs5030655": "indel_proxy",
    "rs4646994": "structural_indel",
    "rs1265181": "hla_proxy_marker",
    "rs429358": "haplotype_component",
}


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
