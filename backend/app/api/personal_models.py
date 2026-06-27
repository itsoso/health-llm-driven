"""个人化预测器 API。

GET /personal-models/treatment-effect?cycle_id=<可选> — 返回某干预周期内每个
OutcomeMetric 的个人化效应估计 (人群先验 + 个人贝叶斯收缩)。
GET /personal-models/predictions — 返回可供 Trajectory/Agenda/Review 消费的
PersonalPrediction 合同。
user_id 隔离: service 层恒带 user_id filter; 跨用户 cycle_id 返回空。

安全: 处方/激素指标降级 clinician_review; 前端渲染 display_label (强制 hedge) 而非裸 verdict。
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.personal_models.personal_prediction import (
    MODEL_VERSION as PERSONAL_PREDICTION_MODEL_VERSION,
)
from app.services.personal_models.personal_prediction import build_personal_predictions
from app.services.personal_models.treatment_effect import estimate_cycle_effects

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/personal-models", tags=["personal-models"])


class TreatmentEffectItem(BaseModel):
    # model_version 字段名与 Pydantic 保护命名空间 model_ 撞, 显式放开 (这不是 ML 模型字段)
    model_config = ConfigDict(protected_namespaces=())

    metric_code: str
    unit: Optional[str] = None
    observed_delta: Optional[float] = None
    posterior_effect: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    ci_level: float
    confidence: str
    verdict: str
    # S1: 前端应渲染 display_label (强制 hedge), verdict 仅供内部逻辑。
    display_label: str
    evidence_tier: str
    requires_clinician: bool
    message: str
    model_version: str


class TreatmentEffectResponse(BaseModel):
    estimates: List[TreatmentEffectItem]


class PersonalPredictionItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    prediction_type: str
    metric: str
    domain: str
    horizon_days: int
    baseline: Optional[float] = None
    unit: Optional[str] = None
    expected_signal: Dict[str, Any]
    confidence: str
    uncertainty: Dict[str, Any]
    evidence_tier: str
    source_model: str
    model_version: str
    claim_boundary: str
    requires_clinician: bool = False
    review_hint: Optional[str] = None


class PersonalPredictionResponse(BaseModel):
    generated_by: str
    predictions: List[PersonalPredictionItem]


@router.get("/treatment-effect", response_model=TreatmentEffectResponse)
async def get_treatment_effect(
    cycle_id: Optional[int] = Query(None, description="指定干预周期 id; 省略取最近 active 周期"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> TreatmentEffectResponse:
    """某干预周期内每个指标的个人化效应估计 (相关非因果, 带 80% 不确定区间)。"""
    logger.info(
        "[PersonalModels] 用户 %s 请求干预效应估计 cycle_id=%s",
        current_user.id, cycle_id,
    )
    estimates = estimate_cycle_effects(db, current_user.id, cycle_id=cycle_id)
    return TreatmentEffectResponse(estimates=estimates)


@router.get("/predictions", response_model=PersonalPredictionResponse)
async def get_personal_predictions(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> PersonalPredictionResponse:
    """返回稳定 PersonalPrediction 合同; 仅用于行动排序、轨迹解释和后续复盘。"""
    logger.info("[PersonalModels] 用户 %s 请求 PersonalPrediction", current_user.id)
    predictions = build_personal_predictions(db, current_user.id)
    return PersonalPredictionResponse(
        generated_by=PERSONAL_PREDICTION_MODEL_VERSION,
        predictions=predictions,
    )
