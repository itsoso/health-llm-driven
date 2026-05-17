"""Conservative genetic prediction layer for mobile-facing genetics surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable

from sqlalchemy.orm import Session

from app.models.genetic_data import GeneticVariant
from app.models.genetic_data import GeneticProfile
from app.services.genetic_report import _resolve_active_profile


_RISK_WEIGHT = {"high": 0, "medium": 1, "low": 2, "info": 3}


@dataclass(frozen=True)
class TraitMarker:
    rsid: str
    gene: str
    label: str
    favorable_allele: str
    source: str
    note: str


HEIGHT_MARKERS: tuple[TraitMarker, ...] = (
    TraitMarker(
        rsid="rs1042725",
        gene="HMGA2",
        label="成人身高相关位点",
        favorable_allele="C",
        source="GIANT/GWAS Catalog height association",
        note="单个位点效应很小；只能作为身高 polygenic signal 的一个碎片。",
    ),
    TraitMarker(
        rsid="rs143383",
        gene="GDF5",
        label="骨骼发育/身高相关位点",
        favorable_allele="C",
        source="GWAS height and skeletal-growth association",
        note="GDF5 与骨骼发育相关；单个位点不能推算厘米数。",
    ),
    TraitMarker(
        rsid="rs6440003",
        gene="ZBTB38",
        label="成人身高相关位点",
        favorable_allele="A",
        source="GIANT/GWAS Catalog height association",
        note="身高是高度多基因性状，需全量 PRS 和祖源校准。",
    ),
)


EDUCATION_MARKERS: tuple[TraitMarker, ...] = (
    TraitMarker(
        rsid="rs9320913",
        gene="LOC100129158",
        label="教育年限相关位点",
        favorable_allele="A",
        source="SSGAC educational-attainment GWAS",
        note="只代表群体统计相关，不能判断个人学习能力或教育结果。",
    ),
    TraitMarker(
        rsid="rs11584700",
        gene="LRRN2",
        label="大学完成/教育年限相关位点",
        favorable_allele="A",
        source="SSGAC educational-attainment GWAS",
        note="教育结果强烈受家庭、学校、地区、经济和个人选择影响。",
    ),
    TraitMarker(
        rsid="rs4851266",
        gene="LOC150577",
        label="教育年限相关位点",
        favorable_allele="T",
        source="SSGAC educational-attainment GWAS",
        note="该类 marker 只能做个人好奇层面的相关性展示。",
    ),
)


def _variant_to_risk(v: GeneticVariant) -> Dict[str, Any]:
    return {
        "rsid": v.rsid,
        "gene": v.gene_name,
        "variant_name": v.variant_name,
        "genotype": v.genotype,
        "result_label": v.result_label,
        "risk_level": v.risk_level or "info",
        "evidence_level": v.evidence_level or "screening",
        "message": "筛查级遗传相关性提示；请结合体检、家族史、症状和医生判断。",
    }


def _normalized_genotype(genotype: str | None) -> str:
    if not genotype:
        return ""
    return "".join(ch for ch in str(genotype).upper() if ch in {"A", "C", "G", "T"})


def _allele_count(genotype: str | None, allele: str) -> int:
    normalized = _normalized_genotype(genotype)
    if len(normalized) != 2:
        return 0
    return normalized.count(allele.upper())


def _variants_by_rsid(variants: Iterable[GeneticVariant]) -> Dict[str, GeneticVariant]:
    return {
        str(v.rsid).lower(): v
        for v in variants
        if v.rsid
    }


def _trait_marker_hits(
    variants: Iterable[GeneticVariant],
    markers: tuple[TraitMarker, ...],
) -> tuple[list[Dict[str, Any]], int]:
    by_rsid = _variants_by_rsid(variants)
    hits: list[Dict[str, Any]] = []
    favorable_count = 0
    for marker in markers:
        variant = by_rsid.get(marker.rsid.lower())
        if variant is None:
            continue
        count = _allele_count(variant.genotype, marker.favorable_allele)
        favorable_count += count
        hits.append({
            "rsid": marker.rsid,
            "gene": marker.gene,
            "label": marker.label,
            "genotype": variant.genotype,
            "favorable_allele": marker.favorable_allele,
            "favorable_allele_count": count,
            "max_alleles": 2,
            "source": marker.source,
            "note": marker.note,
        })
    return hits, favorable_count


def _height_prediction(variants: list[GeneticVariant]) -> Dict[str, Any]:
    hits, favorable_count = _trait_marker_hits(variants, HEIGHT_MARKERS)
    if not hits:
        return {
            "status": "insufficient_model",
            "message": (
                "当前没有已校准到该用户祖源和检测芯片的身高 polygenic score 权重, "
                "也没有命中已支持的探索性身高 marker, 不能输出个人身高数值预测。"
            ),
            "required_inputs": [
                "validated_height_prs_weights",
                "ancestry_or_population_calibration",
                "sex",
                "age_or_growth_stage",
                "parental_heights_optional",
            ],
        }

    max_alleles = len(hits) * 2
    return {
        "status": "exploratory_marker_score",
        "message": (
            f"已命中 {len(hits)} 个身高 GWAS marker, 身高增加相关等位基因 "
            f"{favorable_count}/{max_alleles}。这只能说明方向性 polygenic signal 的一小部分, "
            "不能换算成厘米数；真实身高还需要全量 PRS、祖源校准、性别、父母身高、营养和生长阶段信息。"
        ),
        "marker_count": len(hits),
        "favorable_allele_count": favorable_count,
        "max_alleles": max_alleles,
        "confidence": "low",
        "markers": hits,
        "required_inputs": [
            "validated_height_prs_weights",
            "ancestry_or_population_calibration",
            "sex",
            "age_or_growth_stage",
            "parental_heights_optional",
        ],
    }


def _education_association(variants: list[GeneticVariant]) -> Dict[str, Any]:
    hits, favorable_count = _trait_marker_hits(variants, EDUCATION_MARKERS)
    if not hits:
        return {
            "status": "unsupported",
            "message": (
                "不会预测个人是否能上大学。教育结果强烈受家庭、学校、经济、地区、政策和个人选择影响, "
                "用基因给个人做教育命运判断不可靠。"
            ),
            "allowed_use": "只能用于解释为什么产品不提供该类预测, 不进入用户画像或推荐决策。",
            "does_not_predict_college": True,
        }

    max_alleles = len(hits) * 2
    return {
        "status": "exploratory_association",
        "message": (
            f"已命中 {len(hits)} 个教育年限 GWAS marker, 相关等位基因 "
            f"{favorable_count}/{max_alleles}。这不能判定你是否能上大学, "
            "也不能用于评价能力；它只是在群体研究中与教育年限/教育完成度有弱统计相关。"
        ),
        "marker_count": len(hits),
        "favorable_allele_count": favorable_count,
        "max_alleles": max_alleles,
        "confidence": "very_low",
        "markers": hits,
        "allowed_use": "个人好奇和知识解释；不得进入推荐、录取、评价或任何自动化决策。",
        "does_not_predict_college": True,
    }


def build_genetic_predictions(db: Session, user_id: int) -> Dict[str, Any]:
    profile: GeneticProfile | None = _resolve_active_profile(db, user_id)
    variants = []
    if profile is not None:
        variants = (
            db.query(GeneticVariant)
            .filter(GeneticVariant.user_id == user_id, GeneticVariant.profile_id == profile.id)
            .all()
        )
    disease_variants = [
        v for v in variants
        if v.category == "disease_risk" and (v.risk_level or "info") in {"high", "medium"}
    ]
    disease_variants.sort(key=lambda v: (_RISK_WEIGHT.get(v.risk_level or "info", 3), v.gene_name, v.rsid or ""))

    return {
        "profile": {
            "id": profile.id,
            "test_provider": profile.test_provider,
            "test_date": profile.test_date.isoformat() if profile.test_date else None,
        } if profile else None,
        "height": _height_prediction(variants),
        "education": _education_association(variants),
        "disease_risk": {
            "status": "screening" if profile else "no_data",
            "message": "仅按当前命中的疾病相关位点做筛查级排序, 不是诊断或发病概率。",
            "top_risks": [_variant_to_risk(v) for v in disease_variants[:8]],
        },
    }
