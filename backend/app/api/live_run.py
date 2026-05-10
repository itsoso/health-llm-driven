"""跑步动态指导 (Live Run Coach) API.

V1 端点 (skeleton):
  POST   /live-run/start         开始一次跑步, 返回 session_id + target 配置
  POST   /live-run/{id}/end      结束跑步, 落盘最终统计
  GET    /live-run/{id}          获取一次跑步详情 (含 narrative)
  GET    /live-run/me            列出我的跑步历史
  DELETE /live-run/{id}          删除一次跑步

设计:
  - 跑步过程中不需要后端 (规则引擎全在 mobile 本地)
  - end 时把 mobile 累计的 events / gps_samples 一次性提交到后端
  - narrative LLM 复盘异步生成 (V1 同步生成简化, V2 切 Celery)
"""
from datetime import datetime, timedelta, date
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.live_run import LiveRunSession
from app.models.user import User

router = APIRouter()

# 三档预设目标配速 (秒/公里)
PACE_PRESETS = {
    "easy": 360,    # 6:00
    "tempo": 330,   # 5:30
    "fast": 270,    # 4:30
}


class LiveRunStartRequest(BaseModel):
    target_label: Literal["easy", "tempo", "fast", "custom"] = "easy"
    target_pace_seconds: Optional[int] = Field(None, ge=180, le=900)  # 3:00 ~ 15:00
    notes: Optional[str] = None


class LiveRunEvent(BaseModel):
    ts: datetime
    rule_id: str            # pace_drift / hr_zone_overload / total_load_exceeded
    message: str
    metric_snapshot: Optional[dict] = None


class LiveRunGpsSample(BaseModel):
    ts: datetime
    lat: float
    lon: float
    pace: Optional[int] = None    # 当前瞬时配速 (秒/公里)
    hr: Optional[int] = None


class LiveRunEndRequest(BaseModel):
    total_distance_m: float = Field(..., ge=0)
    total_duration_s: int = Field(..., ge=0)
    avg_pace_seconds: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    z4_plus_minutes: float = 0.0
    calories: Optional[int] = None
    events: List[LiveRunEvent] = []
    gps_samples: List[LiveRunGpsSample] = []
    aborted: bool = False


class LiveRunResponse(BaseModel):
    id: int
    user_id: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    target_pace_seconds: Optional[int] = None
    target_label: Optional[str] = None
    max_z4_minutes: Optional[int] = None
    readiness_score: Optional[int] = None
    total_distance_m: float
    total_duration_s: int
    avg_pace_seconds: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    z4_plus_minutes: float
    calories: Optional[int] = None
    events: List[dict] = []
    gps_samples: List[dict] = []
    narrative: Optional[str] = None
    narrative_status: str
    aborted: bool
    notes: Optional[str] = None

    class Config:
        from_attributes = True


def _to_response(s: LiveRunSession) -> LiveRunResponse:
    return LiveRunResponse(
        id=s.id, user_id=s.user_id,
        started_at=s.started_at, ended_at=s.ended_at,
        target_pace_seconds=s.target_pace_seconds,
        target_label=s.target_label,
        max_z4_minutes=s.max_z4_minutes,
        readiness_score=s.readiness_score,
        total_distance_m=s.total_distance_m or 0.0,
        total_duration_s=s.total_duration_s or 0,
        avg_pace_seconds=s.avg_pace_seconds,
        avg_hr=s.avg_hr, max_hr=s.max_hr,
        z4_plus_minutes=s.z4_plus_minutes or 0.0,
        calories=s.calories,
        events=s.events or [],
        gps_samples=s.gps_samples or [],
        narrative=s.narrative,
        narrative_status=s.narrative_status or "pending",
        aborted=bool(s.aborted),
        notes=s.notes,
    )


def _resolve_target_pace(req: LiveRunStartRequest) -> int:
    if req.target_label == "custom":
        if not req.target_pace_seconds:
            raise HTTPException(status_code=400, detail="custom 模式必须提供 target_pace_seconds")
        return req.target_pace_seconds
    return PACE_PRESETS.get(req.target_label, PACE_PRESETS["easy"])


def _fetch_readiness_snapshot(db: Session, user_id: int) -> tuple[Optional[int], Optional[int]]:
    """跑前快照 readiness + max_z4_minutes.

    V1 简化: readiness 没接 recovery_coach 实时输出时返回 None,
    max_z4_minutes 默认 30min (基础门槛).
    """
    # TODO: 接 recovery_coach.readiness_score 真实输出
    return None, 30


@router.post("/start", response_model=LiveRunResponse, status_code=status.HTTP_201_CREATED)
def start_run(
    req: LiveRunStartRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """开始一次跑步."""
    target_pace = _resolve_target_pace(req)
    readiness, max_z4 = _fetch_readiness_snapshot(db, current_user.id)

    s = LiveRunSession(
        user_id=current_user.id,
        target_pace_seconds=target_pace,
        target_label=req.target_label,
        max_z4_minutes=max_z4,
        readiness_score=readiness,
        notes=req.notes,
        narrative_status="pending",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _to_response(s)


@router.post("/{run_id}/end", response_model=LiveRunResponse)
def end_run(
    run_id: int,
    req: LiveRunEndRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """结束跑步, 落盘统计 + 触发跑后复盘."""
    s = db.query(LiveRunSession).filter(LiveRunSession.id == run_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="跑步记录不存在")
    if s.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    s.ended_at = datetime.utcnow()
    s.total_distance_m = req.total_distance_m
    s.total_duration_s = req.total_duration_s
    s.avg_pace_seconds = req.avg_pace_seconds
    s.avg_hr = req.avg_hr
    s.max_hr = req.max_hr
    s.z4_plus_minutes = req.z4_plus_minutes
    s.calories = req.calories
    s.events = [e.model_dump(mode="json") for e in req.events]
    s.gps_samples = [g.model_dump(mode="json") for g in req.gps_samples]
    s.aborted = req.aborted

    # narrative 跑后异步生成 — 入 Celery 队列
    s.narrative_status = "pending"

    db.commit()
    db.refresh(s)

    try:
        from app.tasks.live_run_narrative import generate_narrative
        generate_narrative.delay(s.id)
    except Exception as e:
        # Celery 不可用不应阻塞 end 调用
        import logging
        logging.getLogger(__name__).warning(f"[live-run] enqueue narrative failed: {e}")

    return _to_response(s)


@router.get("/me", response_model=List[LiveRunResponse])
def list_my_runs(
    start_date: Optional[date] = None,
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """跑步历史 (默认最近 30 天)."""
    if start_date is None:
        start_date = date.today() - timedelta(days=30)

    rows = (
        db.query(LiveRunSession)
        .filter(LiveRunSession.user_id == current_user.id)
        .filter(LiveRunSession.started_at >= datetime.combine(start_date, datetime.min.time()))
        .order_by(desc(LiveRunSession.started_at))
        .limit(limit)
        .all()
    )
    return [_to_response(r) for r in rows]


@router.get("/{run_id}", response_model=LiveRunResponse)
def get_run(
    run_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    s = db.query(LiveRunSession).filter(LiveRunSession.id == run_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="跑步记录不存在")
    if s.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")
    return _to_response(s)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(
    run_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    s = db.query(LiveRunSession).filter(LiveRunSession.id == run_id).first()
    if s is None:
        raise HTTPException(status_code=404, detail="跑步记录不存在")
    if s.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除")
    db.delete(s)
    db.commit()
