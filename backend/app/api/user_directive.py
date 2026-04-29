"""User Directive API — 列表 / 创建 / revoke / 解析自由文本."""
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.user_directive import UserDirective

router = APIRouter(prefix="/user-directives", tags=["user-directives"])


DirectiveKind = Literal[
    "medication_change", "target_override", "lifestyle",
    "watch_metric", "skip_recommendation",
]
Severity = Literal["advisory", "strong", "mandatory"]


class DirectiveCreate(BaseModel):
    kind: DirectiveKind
    instruction: str = Field(..., max_length=1000)
    metric_key: Optional[str] = Field(None, max_length=50)
    target_value: Optional[str] = Field(None, max_length=100)
    medication_name: Optional[str] = Field(None, max_length=100)
    severity: Severity = "strong"
    expires_days: Optional[int] = Field(None, ge=1, le=365)


class FreeTextParseRequest(BaseModel):
    text: str = Field(..., min_length=4, max_length=2000)
    source: str = Field("manual", max_length=40)


@router.get("/me", summary="我的 active directives")
def list_mine(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = db.query(UserDirective).filter(
        UserDirective.user_id == current_user.id,
        UserDirective.status == "active",
    ).order_by(UserDirective.created_at.desc()).all()
    return [{
        "id": r.id,
        "kind": r.kind,
        "instruction": r.instruction,
        "metric_key": r.metric_key,
        "target_value": r.target_value,
        "medication_name": r.medication_name,
        "severity": r.severity,
        "source": r.source,
        "effective_from": r.effective_from.isoformat() if r.effective_from else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.post("", summary="手动创建 directive (用户自己设)")
def create(
    body: DirectiveCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    expires_at = None
    if body.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_days)

    row = UserDirective(
        user_id=current_user.id,
        kind=body.kind,
        instruction=body.instruction,
        metric_key=body.metric_key,
        target_value=body.target_value,
        medication_name=body.medication_name,
        severity=body.severity,
        source="user_self",
        expires_at=expires_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    # Memory: directive → semantic fact (旁路)
    try:
        from app.services.memory_extractor import extract_from_directive
        extract_from_directive(db, row)
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()

    return {"id": row.id, "kind": row.kind}


@router.post("/parse", summary="自由文本解析为 directives (LLM)")
def parse_text(
    body: FreeTextParseRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """通常给医生 Telegram bot 用. 用户也能用 (source='manual')."""
    from app.services.directive_parser import parse_and_store
    ids = parse_and_store(db, current_user.id, body.text, source=body.source)
    return {"created": ids, "count": len(ids)}


@router.delete("/{directive_id}", summary="撤销 directive (status → revoked)")
def revoke(
    directive_id: int,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    row = db.query(UserDirective).filter(
        UserDirective.id == directive_id,
        UserDirective.user_id == current_user.id,
    ).first()
    if not row:
        raise HTTPException(404, "directive 不存在")
    row.status = "revoked"
    row.revoked_at = datetime.now(timezone.utc)
    row.revoked_reason = (reason or "")[:200]
    db.commit()
    return {"id": row.id, "status": row.status}
