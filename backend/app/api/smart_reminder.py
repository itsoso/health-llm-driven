"""智能提醒 API"""
import logging
from datetime import timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from dateutil.parser import parse as parse_datetime

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


class ReminderCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="提醒标题")
    message: Optional[str] = Field(default=None, max_length=500, description="提醒详情")
    remind_at: str = Field(..., description="提醒时间 (ISO 8601)")
    priority: str = Field(default="normal", description="优先级: low/normal/high/urgent")
    recurrence: Optional[str] = Field(default=None, description="重复: daily/weekdays/weekly:1,3,5")


class ReminderUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    message: Optional[str] = Field(default=None, max_length=500)
    remind_at: Optional[str] = Field(default=None, description="提醒时间 (ISO 8601)")
    priority: Optional[str] = Field(default=None, description="优先级: low/normal/high/urgent")
    recurrence: Optional[str] = Field(default=None, description="重复: daily/weekdays/weekly:1,3,5")
    status: Optional[str] = Field(default=None, description="状态: pending/cancelled")


@router.post("/me", summary="创建提醒", status_code=201)
async def create_reminder(
    request: ReminderCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建一个智能提醒"""
    if request.priority not in ("low", "normal", "high", "urgent"):
        raise HTTPException(status_code=400, detail="priority 必须是 low/normal/high/urgent")

    try:
        remind_at = parse_datetime(request.remind_at)
    except Exception:
        raise HTTPException(status_code=400, detail=f"无法解析提醒时间: {request.remind_at}")

    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone(timedelta(hours=8)))

    now = get_china_now()
    if not request.recurrence and remind_at < now:
        raise HTTPException(status_code=400, detail="提醒时间已过，请设置一个未来的时间")

    reminder = SmartReminder(
        user_id=current_user.id,
        title=request.title,
        message=request.message or request.title,
        remind_at=remind_at,
        priority=request.priority,
        recurrence=request.recurrence,
        source="agent_skill",
        status="pending",
    )
    db.add(reminder)
    db.commit()

    return {
        "id": reminder.id,
        "title": reminder.title,
        "message": reminder.message,
        "remind_at": remind_at.isoformat(),
        "priority": reminder.priority,
        "recurrence": reminder.recurrence,
        "status": "pending",
        "created_at": reminder.created_at.isoformat() if reminder.created_at else None,
    }


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


@router.put("/{reminder_id}", summary="更新提醒")
async def update_reminder(
    reminder_id: int,
    request: ReminderUpdateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新一个提醒（本人）"""
    reminder = db.query(SmartReminder).filter(
        SmartReminder.id == reminder_id,
        SmartReminder.user_id == current_user.id,
    ).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="提醒不存在")

    data = request.model_dump(exclude_unset=True)
    if "priority" in data and data["priority"] not in ("low", "normal", "high", "urgent"):
        raise HTTPException(status_code=400, detail="priority 必须是 low/normal/high/urgent")
    if "status" in data and data["status"] not in ("pending", "cancelled"):
        raise HTTPException(status_code=400, detail="status 只能是 pending/cancelled")

    remind_at = None
    if "remind_at" in data:
        try:
            remind_at = parse_datetime(data.pop("remind_at"))
        except Exception:
            raise HTTPException(status_code=400, detail=f"无法解析提醒时间: {request.remind_at}")
        if remind_at.tzinfo is None:
            remind_at = remind_at.replace(tzinfo=timezone(timedelta(hours=8)))
        recurrence = data.get("recurrence", reminder.recurrence)
        if not recurrence and remind_at < get_china_now():
            raise HTTPException(status_code=400, detail="提醒时间已过，请设置一个未来的时间")

    for key, value in data.items():
        setattr(reminder, key, value)
    if remind_at is not None:
        reminder.remind_at = remind_at
    db.commit()
    db.refresh(reminder)

    return {
        "id": reminder.id,
        "title": reminder.title,
        "message": reminder.message,
        "remind_at": reminder.remind_at.isoformat() if reminder.remind_at else None,
        "priority": reminder.priority,
        "recurrence": reminder.recurrence,
        "status": reminder.status,
        "source": reminder.source,
        "created_at": reminder.created_at.isoformat() if reminder.created_at else None,
    }


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
