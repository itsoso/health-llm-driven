"""Durable decision routing control, restricted to the designated administrator."""
import logging
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.auth import get_current_user_required
from app.config import settings
from app.database import get_db
from app.models.agent_audit_log import AgentAuditLog
from app.models.decision_control import DecisionControl
from app.models.user import User
from app.services.decisions.config import DecisionError, configured_decision
from app.services.decisions.control import read_control

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/decisions", tags=["admin-decisions"])


class DecisionControlUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    revision: int = Field(ge=0)


class DecisionControlResponse(BaseModel):
    enabled: bool
    revision: int
    effective_mode: Literal["off", "shadow", "on"]
    configured: bool
    provider: Literal["jev", "laya", "systemone"]
    updated_at: datetime


def require_decision_admin(user: User = Depends(get_current_user_required)) -> User:
    if user.id != 3 or not user.is_admin or not user.is_active:
        raise HTTPException(403, detail="仅指定管理员可管理决策服务")
    return user


def _response(db: Session) -> DecisionControlResponse:
    state = read_control(db)
    configured = settings.decision_admin_control_enabled and settings.decision_mode != "off"
    try:
        configured_decision()  # never expose the destination or key
    except DecisionError:
        logger.warning("decision_control configuration_invalid")
        configured = False  # the administrator must still be able to turn it off
    return DecisionControlResponse(
        enabled=state.enabled, revision=state.revision,
        effective_mode=settings.decision_mode if configured and state.enabled else "off",
        configured=configured, provider=settings.decision_provider, updated_at=state.updated_at,
    )


@router.get("", response_model=DecisionControlResponse)
def get_decision_control(
    admin: User = Depends(require_decision_admin), db: Session = Depends(get_db),
):
    try:
        return _response(db)
    except (DecisionError, SQLAlchemyError) as exc:
        logger.warning("decision_control read_failed error_type=%s", type(exc).__name__)
        raise HTTPException(503, detail="决策服务配置暂不可用") from None


@router.put("", response_model=DecisionControlResponse)
def update_decision_control(
    request: DecisionControlUpdate,
    admin: User = Depends(require_decision_admin), db: Session = Depends(get_db),
):
    try:
        current = _response(db)
        if current.revision != request.revision:
            raise HTTPException(409, detail="开关已被更新，请刷新后重试")
        if request.enabled and not current.configured:
            raise HTTPException(409, detail="决策服务尚未配置，请先完成部署")
        changed = db.execute(
            update(DecisionControl)
            .where(DecisionControl.id == 1, DecisionControl.revision == request.revision)
            .values(enabled=request.enabled, revision=request.revision + 1,
                    updated_by=admin.id, updated_at=datetime.now(UTC))
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:
            db.rollback()
            raise HTTPException(409, detail="开关已被更新，请刷新后重试")
        db.add(AgentAuditLog(
            user_id=admin.id, agent_type="security_audit", action="decision_control_changed",
            result_summary="决策服务全站开关已更新",
            result_detail={"enabled": request.enabled, "previous_enabled": current.enabled,
                           "revision": request.revision + 1},
        ))
        response = _response(db)
        db.commit()
        return response
    except (DecisionError, SQLAlchemyError) as exc:
        db.rollback()
        logger.warning("decision_control write_failed error_type=%s", type(exc).__name__)
        raise HTTPException(503, detail="开关保存失败，请稍后重试") from None
