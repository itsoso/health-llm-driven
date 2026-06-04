"""Biomarker API — 标准化观测 + 代谢画像 (Personal Health OS P2).

- GET /biomarkers/me            最新一组标准化观测
- GET /biomarkers/me/{code}/series  单指标趋势
- GET /biomarkers/me/profile    代谢健康画像 (慢病风险 + 异常指标) — 交互稿①
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.biomarkers import get_definition
from app.services import biomarker_service
from app.services.chronic_risk_service import chronic_risk_service

router = APIRouter(prefix="/biomarkers", tags=["biomarkers"])


def _obs_dict(o) -> dict:
    defn = get_definition(o.code)
    return {
        "code": o.code,
        "display": defn.display if defn else o.code,
        "domain": o.domain,
        "value": o.value,
        "unit": o.unit,
        "normalized_value": o.normalized_value,
        "normalized_unit": o.normalized_unit,
        "ref_low": o.ref_low,
        "ref_high": o.ref_high,
        "flag": o.flag,
        "abnormal": o.abnormal,
        "is_risk": o.is_risk,
        "confidence": o.confidence,
        "observed_at": o.observed_at.isoformat() if o.observed_at else None,
    }


@router.get("/me")
def my_biomarkers(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户每个指标的最新标准化观测。"""
    latest = biomarker_service.latest_observations(db, current_user.id)
    obs = sorted(latest.values(), key=lambda o: (not o.is_risk, o.domain or "", o.code))
    return {
        "observations": [_obs_dict(o) for o in obs],
        "abnormal_count": sum(1 for o in obs if o.abnormal),
    }


@router.get("/me/{code}/series")
def my_biomarker_series(
    code: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """单指标按时间升序的观测序列 (趋势)。"""
    series = biomarker_service.observation_series(db, current_user.id, code)
    defn = get_definition(code)
    return {
        "code": code,
        "display": defn.display if defn else code,
        "unit": defn.canonical_unit if defn else None,
        "points": [
            {"observed_at": o.observed_at.isoformat() if o.observed_at else None,
             "value": o.normalized_value, "flag": o.flag}
            for o in series
        ],
    }


@router.get("/me/profile")
def my_metabolic_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """代谢健康画像 (交互稿①): 慢病风险分层 + 异常生物标志物。"""
    risk = chronic_risk_service.assess_comprehensive_risk(db=db, user_id=current_user.id)
    latest = biomarker_service.latest_observations(db, current_user.id)
    obs = sorted(latest.values(), key=lambda o: (not o.is_risk, o.domain or "", o.code))
    abnormal = [_obs_dict(o) for o in obs if o.abnormal]
    return {
        "risk": risk,
        "biomarkers": [_obs_dict(o) for o in obs],
        "abnormal": abnormal,
        "abnormal_count": len(abnormal),
    }
