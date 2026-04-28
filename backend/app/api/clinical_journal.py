"""Clinical Journal API — case timeline + SOAP entries."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.clinical_journal import CaseThread, ClinicalJournalEntry
from app.models.user import User

router = APIRouter(prefix="/clinical-journal", tags=["clinical-journal"])


@router.get("/cases", summary="用户所有 case_threads (按最近活跃排序)")
def list_cases(
    status: Optional[str] = Query(None, description="active / monitoring / resolved"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    q = db.query(CaseThread).filter(CaseThread.user_id == current_user.id)
    if status:
        q = q.filter(CaseThread.status == status)
    rows = q.order_by(CaseThread.last_updated_at.desc()).all()

    return [{
        "id": r.id,
        "theme": r.theme,
        "metric_key": r.metric_key,
        "title": r.title,
        "summary": r.summary,
        "status": r.status,
        "severity": r.severity,
        "opened_at": r.opened_at.isoformat() if r.opened_at else None,
        "last_updated_at": r.last_updated_at.isoformat() if r.last_updated_at else None,
        "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
        "entry_count": len(r.entries),
    } for r in rows]


@router.get("/cases/{case_id}", summary="单个 case 详情 + 所有 entries")
def case_detail(
    case_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    case = db.query(CaseThread).filter(
        CaseThread.id == case_id,
        CaseThread.user_id == current_user.id,
    ).first()
    if not case:
        raise HTTPException(404, "case 不存在")

    entries = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.case_thread_id == case_id,
    ).order_by(ClinicalJournalEntry.generated_at.desc()).all()

    return {
        "id": case.id,
        "theme": case.theme,
        "metric_key": case.metric_key,
        "title": case.title,
        "summary": case.summary,
        "status": case.status,
        "severity": case.severity,
        "opened_at": case.opened_at.isoformat() if case.opened_at else None,
        "last_updated_at": case.last_updated_at.isoformat() if case.last_updated_at else None,
        "entries": [{
            "id": e.id,
            "subjective": e.subjective,
            "objective": e.objective,
            "assessment": e.assessment,
            "plan": e.plan,
            "used_specialists": (e.used_specialists or "").split(",") if e.used_specialists else [],
            "related_action_card_ids": (
                [int(x) for x in e.related_action_card_ids.split(",") if x]
                if e.related_action_card_ids else []
            ),
            "generated_at": e.generated_at.isoformat() if e.generated_at else None,
            "created_by": e.created_by,
        } for e in entries],
    }


@router.get("/entries/recent", summary="最近 N 天的 SOAP entry (跨 case)")
def recent_entries(
    days: int = Query(14, ge=1, le=180),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    entries = db.query(ClinicalJournalEntry).filter(
        ClinicalJournalEntry.user_id == current_user.id,
        ClinicalJournalEntry.generated_at >= since,
    ).order_by(ClinicalJournalEntry.generated_at.desc()).limit(50).all()

    return [{
        "id": e.id,
        "case_thread_id": e.case_thread_id,
        "subjective": e.subjective,
        "assessment_first_line": (e.assessment or "").split("\n")[0],
        "plan_first_line": (e.plan or "").split("\n")[0],
        "generated_at": e.generated_at.isoformat() if e.generated_at else None,
    } for e in entries]
