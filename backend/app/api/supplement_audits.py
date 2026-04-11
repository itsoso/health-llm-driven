"""补剂审计 API

提供只读 + 状态变更能力。生成新审计走 create API（手动），
未来会由事件触发和 LLM 自动生成接入。
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.schemas.supplement_audit import (
    SupplementAuditCreate,
    SupplementAuditDetail,
    SupplementAuditItemOut,
    SupplementAuditItemUpdate,
    SupplementAuditListItem,
)
from app.services.supplement_audit_service import supplement_audit_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supplement-audits", tags=["supplement-audits"])


@router.get("/me", response_model=List[SupplementAuditListItem])
def list_my_audits(
    limit: int = Query(20, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """我的审计历史列表（含统计，不含完整 markdown）"""
    return supplement_audit_service.list_audits(db, current_user.id, limit)


@router.get("/me/active", response_model=SupplementAuditDetail)
def get_my_active_audit(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """我当前 active 的审计（最新版本）"""
    audit = supplement_audit_service.get_active_audit(db, current_user.id)
    if not audit:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="暂无 active 审计")
    return audit


@router.get("/me/{audit_id}", response_model=SupplementAuditDetail)
def get_audit_detail(
    audit_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """单个审计详情（含完整 markdown 和全部 items）"""
    return supplement_audit_service.get_audit_by_id(db, current_user.id, audit_id)


@router.post("/me", response_model=SupplementAuditDetail)
def create_audit(
    payload: SupplementAuditCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """手动创建新审计（会把旧 active 置为 superseded）"""
    return supplement_audit_service.create_audit(db, current_user.id, payload)


@router.patch("/me/items/{item_id}", response_model=SupplementAuditItemOut)
def update_audit_item(
    item_id: int,
    payload: SupplementAuditItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """变更单条 action item 状态: accept/reject/complete + 可选 user_note"""
    return supplement_audit_service.update_item(db, current_user.id, item_id, payload)
