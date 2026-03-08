"""智能提醒 API"""
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.smart_reminder import SmartReminder
from app.utils.timezone import get_china_now

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reminders", tags=["reminders"])


class ReminderResponse(BaseModel):
    id: int
    title: str
    message: Optional[str]
    remind_at: str
    priority: str
    recurrence: Optional[str]
    status: str
    source: Optional[str]
    created_at: Optional[str]


@router.get("/me", summary="获取我的提醒列表")
async def get_my_reminders(
    status: Optional[str] = Query(default="pending", description="状态过滤: pending/fired/cancelled/all"),
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户的提醒列表"""
    query = db.query(SmartReminder).filter(SmartReminder.user_id == current_user.id)

    if status and status != "all":
        query = query.filter(SmartReminder.status == status)

    reminders = query.order_by(SmartReminder.remind_at.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "title": r.title,
            "message": r.message,
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "priority": r.priority,
            "recurrence": r.recurrence,
            "status": r.status,
            "source": r.source,
            "fired_at": r.fired_at.isoformat() if r.fired_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reminders
    ]


@router.delete("/{reminder_id}", summary="取消提醒")
async def cancel_reminder(
    reminder_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """取消一个提醒"""
    reminder = db.query(SmartReminder).filter(
        SmartReminder.id == reminder_id,
        SmartReminder.user_id == current_user.id,
    ).first()

    if not reminder:
        raise HTTPException(status_code=404, detail="提醒不存在")

    if reminder.status != "pending":
        raise HTTPException(status_code=400, detail=f"提醒已{reminder.status}，无法取消")

    reminder.status = "cancelled"
    db.commit()

    return {"success": True, "message": f"已取消提醒: {reminder.title}"}
