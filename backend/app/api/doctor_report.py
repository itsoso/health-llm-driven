"""医生回路 (H3-7) API.

两个职责:
- 导出: 生成给医生看的 markdown 摘要
- 反馈: 把医生意见写回 Clinical Journal (created_by='doctor')
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.models.agent_audit_log import AgentAuditLog
from app.services.doctor_report_service import (
    build_doctor_export, list_doctor_feedback, record_doctor_feedback,
)

router = APIRouter(prefix="/doctor-report", tags=["doctor-report"])


@router.get("/export", summary="导出医生摘要 (markdown + 结构化)")
def export_doctor_report(
    days: int = Query(30, ge=7, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    report = build_doctor_export(db, current_user.id, days=days)
    db.add(AgentAuditLog(
        user_id=current_user.id,
        agent_type="security_audit",
        action="doctor_report_exported",
        result_summary="用户导出医生摘要",
        result_detail={"days": days},
    ))
    db.commit()
    return report


class DoctorFeedbackIn(BaseModel):
    summary: Optional[str] = Field(None, description="医生说的话 / 主诉上下文")
    assessment: Optional[str] = Field(None, description="医生的评估")
    plan: Optional[str] = Field(None, description="医生的下一步安排")
    visit_date: Optional[date] = Field(None, description="就诊日期")


@router.post("/feedback", summary="录入医生反馈 → Clinical Journal")
def post_doctor_feedback(
    data: DoctorFeedbackIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    entry = record_doctor_feedback(
        db, current_user.id,
        summary=data.summary,
        assessment=data.assessment,
        plan=data.plan,
        visit_date=data.visit_date,
    )
    return {
        "id": entry.id,
        "generated_at": entry.generated_at.isoformat() if entry.generated_at else None,
        "created_by": entry.created_by,
    }


@router.get("/feedback/me", summary="历史医生反馈列表")
def get_my_feedback(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = list_doctor_feedback(db, current_user.id, limit=limit)
    return {
        "feedback": [
            {
                "id": r.id,
                "generated_at": r.generated_at.isoformat() if r.generated_at else None,
                "subjective": r.subjective,
                "objective": r.objective,
                "assessment": r.assessment,
                "plan": r.plan,
            }
            for r in rows
        ],
    }
