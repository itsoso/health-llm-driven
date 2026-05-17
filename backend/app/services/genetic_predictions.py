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


LEARNING_RULES: tuple[Dict[str, Any], ...] = (
    {
        "rsids": ("rs6265",),
        "title": "用有氧运动打开学习可塑性窗口",
        "rationale": "BDNF Val66Met 与神经可塑性和记忆相关；命中时更应该用运动、睡眠和重复练习去放大可改变部分。",
        "actions": [
            "每周安排 3-4 次 25-45 分钟 Zone 2 或快走/骑行。",
            "重要学习日前避免熬夜；把新知识输入放在睡眠更稳定的时段。",
            "高难内容先做 20-30 分钟预习, 再用短测验主动回忆。",
        ],
    },
    {
        "rsids": ("rs17070145",),
        "title": "用间隔复习和主动回忆支撑记忆",
        "rationale": "KIBRA/WWC1 与情景记忆相关；策略重点不是多看几遍, 而是拉开间隔并强迫自己提取。",
        "actions": [
            "同一知识点按 1 天、3 天、7 天、14 天做间隔复习。",
            "每次复习先合上资料写出要点, 再对照补漏。",
            "把长材料拆成 5-7 个问题卡, 用问题驱动复盘。",
        ],
    },
    {
        "rsids": ("rs363050",),
        "title": "降低单次认知负荷",
        "rationale": "SNAP25 与突触传递和认知灵活性相关；命中时更适合小步快反馈, 不适合长时间硬扛。",
        "actions": [
            "把学习块切成 25-40 分钟, 每块只处理一个明确问题。",
            "每块结束写 3 行总结: 学到了什么、哪里卡住、下一步做什么。",
            "新领域先建立术语表和概念图, 再进入细节。",
        ],
    },
    {
        "rsids": ("rs1800544", "rs1044396"),
        "title": "建立低干扰学习环境",
        "rationale": "ADRA2A/CHRNA4 与注意力调控相关；建议优先控制环境变量, 而不是靠意志力硬抗分心。",
        "actions": [
            "深度学习时关闭通知, 手机放到视线外, 只保留一个主任务窗口。",
            "使用 25/5 或 40/10 番茄钟, 每轮结束记录完成证据。",
            "咖啡因放在上午或学习前半段；睡眠受影响时优先降咖啡因。",
        ],
    },
    {
        "rsids": ("rs4570625", "rs4680"),
        "title": "先稳压力和睡眠, 再堆学习时长",
        "rationale": "TPH2/COMT 与情绪、压力和前额叶多巴胺调控相关；压力过高时学习效率比时长更先崩。",
        "actions": [
            "考试或高压项目前 7 天固定睡眠窗口, 不临时大幅延长学习时长。",
            "高压学习块前做 3-5 分钟呼吸或散步, 降低启动阻力。",
            "把任务拆到当天可完成的最小动作, 用完成率而不是焦虑感评估进展。",
        ],
    },
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


def _variant_snapshot(v: GeneticVariant) -> Dict[str, Any]:
    return {
        "rsid": v.rsid,
        "gene": v.gene_name,
        "variant_name": v.variant_name,
        "genotype": v.genotype,
        "result_label": v.result_label,
        "risk_level": v.risk_level or "info",
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


def _learning_recommendations(variants: list[GeneticVariant]) -> Dict[str, Any]:
    by_rsid = _variants_by_rsid(variants)
    learning_rsids = {
        rsid
        for rule in LEARNING_RULES
        for rsid in rule["rsids"]
    }
    matched = [
        by_rsid[rsid]
        for rsid in sorted(learning_rsids)
        if rsid in by_rsid
    ]
    if not matched:
        return {
            "status": "no_supported_marker",
            "message": "当前没有命中已支持的学习/注意力相关 SNP；不输出学习能力判断。",
            "marker_count": 0,
            "recommendations": [],
            "confidence": "low",
            "does_not_score_ability": True,
        }

    recommendations: list[Dict[str, Any]] = []
    for rule in LEARNING_RULES:
        related = [by_rsid[rsid] for rsid in rule["rsids"] if rsid in by_rsid]
        if not related:
            continue
        recommendations.append({
            "title": rule["title"],
            "rationale": rule["rationale"],
            "actions": rule["actions"],
            "related_rsids": [v.rsid for v in related if v.rsid],
            "related_genes": sorted({v.gene_name for v in related if v.gene_name}),
            "evidence_level": "screening",
            "confidence": "low",
        })

    return {
        "status": "actionable_markers",
        "message": (
            f"已命中 {len(matched)} 个学习/注意力相关 SNP。以下只作为学习策略个性化提示, "
            "不评价智力、能力或教育结果。"
        ),
        "marker_count": len(matched),
        "markers": [_variant_snapshot(v) for v in matched],
        "recommendations": recommendations,
        "confidence": "low",
        "does_not_score_ability": True,
        "boundary": "低置信度相关性 + 行为策略建议；不得用于能力评价、教育筛选或任何自动化决策。",
    }


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
        "learning": _learning_recommendations(variants),
        "disease_risk": {
            "status": "screening" if profile else "no_data",
            "message": "仅按当前命中的疾病相关位点做筛查级排序, 不是诊断或发病概率。",
            "top_risks": [_variant_to_risk(v) for v in disease_variants[:8]],
        },
    }
