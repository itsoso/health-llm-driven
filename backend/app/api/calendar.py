"""日历(Calendar v2 / C1):凭据 / 多源管理 / 同步 / 详细事件读取 / 状态。

安全:凭据由用户在 App 自填(后端绝不代填),加密存;事件 PII 加密存;只读外部日历;
user_id 一律取自 token,每个源/事件按 user_id 过滤(越权返 404)。
详细事件(GET /events)是用户自己客户端的明细读;LLM/agent 路径只能走
caldav_sync.calendar_event_for_llm(隐私接缝),绝不在此暴露原始标题给 agent。
见 docs/specs/active/2026-06-18-calendar-v2.md。
"""
import logging
from datetime import date as _date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.calendar_sync import CalendarEvent, CalendarSource
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


class SourceIn(BaseModel):
    provider: str = Field("caldav", description="caldav | ics")
    name: str = Field(..., max_length=200)
    color: Optional[str] = Field(None, max_length=20)
    url: str = Field(..., max_length=500, description="必须 https")
    username: Optional[str] = Field(None, max_length=200)
    password: Optional[str] = Field(None, max_length=500)

    @field_validator("provider")
    @classmethod
    def _provider(cls, v: str) -> str:
        if v not in ("caldav", "ics"):
            raise ValueError("provider 只能是 caldav 或 ics")
        return v

    @field_validator("url")
    @classmethod
    def _https_only(cls, v: str) -> str:
        if not (v or "").startswith("https://"):
            raise ValueError("日历地址必须是 https://")
        return v


class SourceUpdateIn(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    color: Optional[str] = Field(None, max_length=20)
    sync_enabled: Optional[bool] = None


def _source_safe(s: CalendarSource) -> dict:
    """安全出参:绝不含 encrypted_credentials / url / password。"""
    return {
        "id": s.id,
        "provider": s.provider,
        "name": s.name,
        "color": s.color,
        "writable": bool(s.writable),
        "sync_enabled": bool(s.sync_enabled),
        "last_sync_at": s.last_sync_at.isoformat() if s.last_sync_at else None,
        "last_error": s.last_error,
    }


def _owned_source(db: Session, user_id: int, source_id: int) -> CalendarSource:
    src = (
        db.query(CalendarSource)
        .filter(CalendarSource.id == source_id, CalendarSource.user_id == user_id)
        .first()
    )
    if src is None:
        raise HTTPException(status_code=404, detail="日历源不存在")
    return src


@router.put("/credentials", status_code=200, summary="保存 CalDAV 凭据(加密)")
def put_credentials(
    body: CalDAVCredentialIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    svc.save_credentials(db, current_user.id, url=body.url, username=body.username, password=body.password)
    return {"ok": True}


@router.post("/sync", summary="立即同步所有源(窗口明细)")
def post_sync(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # v2:同步所有 sync_enabled 源(每源 fail-soft,坏源不阻断其它)。
    return svc.sync_all_sources(db, current_user.id)


@router.get("/sources", summary="列出用户的日历源(不含凭据)")
def list_sources(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CalendarSource)
        .filter(CalendarSource.user_id == current_user.id)
        .order_by(CalendarSource.id)
        .all()
    )
    return [_source_safe(s) for s in rows]


@router.post("/sources", summary="新增日历源(加密凭据)")
def create_source(
    body: SourceIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    creds = {"url": body.url}
    if body.provider == "caldav":
        creds["username"] = body.username or ""
        creds["password"] = body.password or ""
    src = CalendarSource(
        user_id=current_user.id, provider=body.provider, name=body.name,
        color=body.color, writable=False, sync_enabled=True,  # ics/caldav 当前均只读
    )
    src.set_credentials(creds)
    db.add(src)
    db.commit()
    db.refresh(src)
    return _source_safe(src)


@router.put("/sources/{source_id}", summary="改名/启停日历源")
def update_source(
    source_id: int,
    body: SourceUpdateIn,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    src = _owned_source(db, current_user.id, source_id)
    if body.name is not None:
        src.name = body.name
    if body.color is not None:
        src.color = body.color
    if body.sync_enabled is not None:
        src.sync_enabled = body.sync_enabled
    db.commit()
    db.refresh(src)
    return _source_safe(src)


@router.delete("/sources/{source_id}", summary="删除日历源及其事件")
def delete_source(
    source_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    src = _owned_source(db, current_user.id, source_id)
    db.query(CalendarEvent).filter(CalendarEvent.source_id == src.id).delete(synchronize_session=False)
    db.delete(src)
    db.commit()
    return {"ok": True}


@router.get("/events", summary="读取本人日历事件明细(解密)")
def get_events(
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 用户自己的客户端读全量明细(标题/地点等解密)。LLM 路径绝不走这里。
    today = datetime.now(svc._BEIJING).date()
    try:
        d_from = _date.fromisoformat(from_) if from_ else (today - timedelta(days=7))
        d_to = _date.fromisoformat(to) if to else (today + timedelta(days=30))
    except ValueError:
        raise HTTPException(status_code=422, detail="from/to 需为 YYYY-MM-DD")
    start = datetime(d_from.year, d_from.month, d_from.day, tzinfo=svc._BEIJING)
    end = datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59, tzinfo=svc._BEIJING)
    rows = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == current_user.id,
            CalendarEvent.start_time >= start,
            CalendarEvent.start_time <= end,
        )
        .order_by(CalendarEvent.start_time)
        .all()
    )
    return [
        {
            "id": r.id,
            "source_id": r.source_id,
            "uid": r.uid,
            "title": r.get_title(),
            "start": r.start_time.isoformat() if r.start_time else None,
            "end": r.end_time.isoformat() if r.end_time else None,
            "all_day": bool(r.all_day),
            "location": r.get_location(),
            "description": r.get_description(),
            "attendees": r.get_attendees(),
            "status": r.status,
        }
        for r in rows
    ]


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
