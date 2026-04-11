"""健康咨询 API

一等公民的"多层级症状咨询追踪"能力.
提供 CRUD + 状态机变更 + 自动回测 predictions 能力.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.health_consultation import (
    ConsultationItemOut,
    ConsultationItemUpdate,
    ConsultationListItem,
    HealthConsultationCreate,
    HealthConsultationDetail,
)
from app.services.health_consultation_service import health_consultation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health-consultations", tags=["health-consultations"])


@router.get("/me", response_model=List[ConsultationListItem])
def list_my_consultations(
    limit: int = Query(20, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """我的咨询历史列表 (含分类统计, 不含完整 markdown)"""
    return health_consultation_service.list_consultations(db, current_user.id, limit)


@router.get("/me/active", response_model=HealthConsultationDetail)
def get_my_active(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前 active 咨询 (最新版本)"""
    c = health_consultation_service.get_active(db, current_user.id)
    if not c:
        raise HTTPException(status_code=404, detail="暂无 active 咨询")
    return c


@router.get("/me/{consultation_id}", response_model=HealthConsultationDetail)
def get_consultation(
    consultation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """单次咨询详情 (含全部 items)"""
    return health_consultation_service.get_by_id(db, current_user.id, consultation_id)


@router.post("/me", response_model=HealthConsultationDetail)
def create_consultation(
    payload: HealthConsultationCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建一次新咨询 (批量包含所有 hypotheses/actions/predictions/red_flags)"""
    return health_consultation_service.create(db, current_user.id, payload)


@router.patch("/me/items/{item_id}", response_model=ConsultationItemOut)
def update_item(
    item_id: int,
    payload: ConsultationItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """变更单个 consultation item 的状态 / 备注 / 实际值"""
    return health_consultation_service.update_item(db, current_user.id, item_id, payload)


@router.post("/me/{consultation_id}/verify")
def verify_predictions(
    consultation_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """自动回测所有 pending predictions - 对比 garmin_data / medical_indicators 的实际值

    返回每条 prediction 的验证建议 (不自动落库, 用户/AI 确认后再 PATCH 条目)
    """
    return health_consultation_service.verify_predictions(db, current_user.id, consultation_id)
