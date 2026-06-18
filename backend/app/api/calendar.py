"""CalDAV 日历:保存凭据 / 触发同步 / 状态。供时点日程避开会议(只读外部日历)。

安全:凭据由用户在 App 自填(后端绝不代填),加密存;只读外部日历;user_id 取自 token。
见 docs/specs/active/2026-06-17-day-timing-schedule.md(CalDAV 事件驱动)。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import caldav_sync as svc

router = APIRouter(prefix="/calendar", tags=["calendar"])
logger = logging.getLogger(__name__)


class CalDAVCredentialIn(BaseModel):
    url: str = Field(..., max_length=500, description="CalDAV 服务地址(必须 https)")
    username: str = Field(..., max_length=200)
    password: str = Field(..., max_length=500, description="应用专用密码(非主密码)")

    @field_validator("url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not (v or "").startswith("https://"):
            raise ValueError("CalDAV 地址必须是 https://")
        return v


@router.put("/credentials", status_code=200, summary="保存 CalDAV 凭据(加密)")
def put_credentials(
    body: CalDAVCredentialIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    svc.save_credentials(db, current_user.id, url=body.url, username=body.username, password=body.password)
    return {"ok": True}


@router.post("/sync", summary="立即同步今日忙碌块")
def post_sync(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    try:
        result = svc.sync_today(db, current_user.id)
    except Exception as e:  # 连接/解析失败 → 422 让客户端感知(不假装成功)
        raise HTTPException(status_code=422, detail=f"日历同步失败:{str(e)[:200]}")
    return result


@router.get("/status", summary="日历连接状态")
def get_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.models.calendar_sync import CalendarCredential

    cred = db.query(CalendarCredential).filter(CalendarCredential.user_id == current_user.id).first()
    if cred is None:
        return {"connected": False}
    return {
        "connected": True,
        "sync_enabled": cred.sync_enabled,
        "last_sync_at": cred.last_sync_at.isoformat() if cred.last_sync_at else None,
        "last_error": cred.last_error,
        "busy_today": len(svc.today_busy_blocks(db, current_user.id)),
    }
