"""Conservative genetic prediction layer for mobile-facing genetics surfaces."""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.genetic_data import GeneticVariant
from app.models.genetic_data import GeneticProfile
from app.services.genetic_report import _resolve_active_profile


_RISK_WEIGHT = {"high": 0, "medium": 1, "low": 2, "info": 3}


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
        "height": {
            "status": "insufficient_model",
            "message": (
                "当前没有已校准到该用户祖源和检测芯片的身高 polygenic score 权重, "
                "不能输出个人身高数值预测。可先记录父母身高、本人历史身高和青春期数据, "
                "未来接入经过校准的 PRS 模型后再估计。"
            ),
            "required_inputs": [
                "validated_height_prs_weights",
                "ancestry_or_population_calibration",
                "sex",
                "age_or_growth_stage",
                "parental_heights_optional",
            ],
        },
        "education": {
            "status": "unsupported",
            "message": (
                "不会预测个人是否能上大学。教育结果强烈受家庭、学校、经济、地区、政策和个人选择影响, "
                "用基因给个人做教育命运判断不可靠, 也会带来歧视风险。"
            ),
            "allowed_use": "只能用于解释为什么产品不提供该类预测, 不进入用户画像或推荐决策。",
        },
        "disease_risk": {
            "status": "screening" if profile else "no_data",
            "message": "仅按当前命中的疾病相关位点做筛查级排序, 不是诊断或发病概率。",
            "top_risks": [_variant_to_risk(v) for v in disease_variants[:8]],
        },
    }
