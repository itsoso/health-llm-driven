"""Episodes API — Agent-Native v3 Increment 1.

3 个端点:
  GET  /episodes/me                  当前用户最近 Episode 列表 (默认最近 30 天, limit 20)
  GET  /episodes/{id}                单个 Episode 详情 + Actions
  POST /episodes/{id}/feedback       提交 EpisodeFeedback (action_done / skipped / pain / answer)

Protocol 内容不入库 — 走 backend/protocols/ YAML registry, 通过 protocol_slug + protocol_version 引用.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.episode import (
    EpisodeAction,
    EpisodeFeedback,
    HealthEpisode,
)
from app.models.user import User
from app.services.episode.lifecycle import maybe_close_episode

router = APIRouter()


# ─────────────────────────────────────────────────────────
# Pydantic
# ─────────────────────────────────────────────────────────

class EpisodeActionOut(BaseModel):
    id: int
    sequence: int
    title: str
    body: Optional[str] = None
    icon: Optional[str] = None
    action_type: str
    template_id: Optional[str] = None
    evidence_id: Optional[str] = None
    time_window_start: Optional[datetime] = None
    time_window_end: Optional[datetime] = None
    status: str
    completed_at: Optional[datetime] = None
    skipped_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class EpisodeListItem(BaseModel):
    id: int
    episode_type: str
    occurred_at: datetime
    status: str
    risk_level: str
    risk_flags: Optional[List[str]] = None
    protocol_slug: Optional[str] = None
    protocol_version: Optional[str] = None
    headline: Optional[str] = None
    actions_total: int
    actions_done: int

    model_config = {"from_attributes": True}


class EpisodeOutcomeOut(BaseModel):
    actions_total: int
    actions_done: int
    actions_skipped: int
    completion_rate: Optional[float] = None
    metrics_delta: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None

    model_config = {"from_attributes": True}


class EpisodeDetail(EpisodeListItem):
    source_type: Optional[str] = None
    source_id: Optional[int] = None
    context_snapshot: Optional[Dict[str, Any]] = None
    baseline_snapshot: Optional[Dict[str, Any]] = None
    actions: List[EpisodeActionOut] = []
    outcome: Optional[EpisodeOutcomeOut] = None


class FeedbackCreate(BaseModel):
    kind: str = Field(..., description="action_done / action_skipped / pain_report / rpe / inline_answer / replan_request")
    action_id: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    source: str = Field(default="mobile")


class FeedbackOut(BaseModel):
    id: int
    episode_id: int
    action_id: Optional[int] = None
    kind: str
    payload: Optional[Dict[str, Any]] = None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

_ALLOWED_FEEDBACK_KINDS = {
    "action_done", "action_skipped", "pain_report", "rpe",
    "sleep_quality", "inline_answer", "replan_request",
}


def _to_list_item(ep: HealthEpisode) -> EpisodeListItem:
    actions = ep.actions or []
    return EpisodeListItem(
        id=ep.id,
        episode_type=ep.episode_type,
        occurred_at=ep.occurred_at,
        status=ep.status,
        risk_level=ep.risk_level,
        risk_flags=ep.risk_flags,
        protocol_slug=ep.protocol_slug,
        protocol_version=ep.protocol_version,
        headline=ep.headline,
        actions_total=len(actions),
        actions_done=sum(1 for a in actions if a.status == "done"),
    )


# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────

@router.get("/me", response_model=List[EpisodeListItem])
def list_my_episodes(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=20, ge=1, le=100),
    episode_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当前用户最近 Episode 列表."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = db.query(HealthEpisode).filter(
        HealthEpisode.user_id == current_user.id,
        HealthEpisode.occurred_at >= since,
    )
    if episode_type:
        q = q.filter(HealthEpisode.episode_type == episode_type)
    if status:
        q = q.filter(HealthEpisode.status == status)
    rows = q.order_by(HealthEpisode.occurred_at.desc()).limit(limit).all()
    return [_to_list_item(r) for r in rows]


@router.get("/{episode_id}", response_model=EpisodeDetail)
def get_episode(
    episode_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取 Episode 详情 + Actions (按 sequence 排序)."""
    ep = db.query(HealthEpisode).filter(HealthEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode 不存在")
    if ep.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    actions = sorted(ep.actions or [], key=lambda a: a.sequence)
    base = _to_list_item(ep)
    outcome_out = (
        EpisodeOutcomeOut.model_validate(ep.outcome) if ep.outcome else None
    )
    return EpisodeDetail(
        **base.model_dump(),
        source_type=ep.source_type,
        source_id=ep.source_id,
        context_snapshot=ep.context_snapshot,
        baseline_snapshot=ep.baseline_snapshot,
        actions=[EpisodeActionOut.model_validate(a) for a in actions],
        outcome=outcome_out,
    )


@router.post("/{episode_id}/feedback", response_model=FeedbackOut)
def submit_feedback(
    episode_id: int,
    body: FeedbackCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """提交 EpisodeFeedback. action_done / action_skipped 会同步更新 EpisodeAction.status."""
    if body.kind not in _ALLOWED_FEEDBACK_KINDS:
        raise HTTPException(status_code=400, detail=f"不支持的 kind: {body.kind}")

    ep = db.query(HealthEpisode).filter(HealthEpisode.id == episode_id).first()
    if not ep:
        raise HTTPException(status_code=404, detail="Episode 不存在")
    if ep.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作")

    action: Optional[EpisodeAction] = None
    if body.action_id is not None:
        action = db.query(EpisodeAction).filter(
            EpisodeAction.id == body.action_id,
            EpisodeAction.episode_id == episode_id,
        ).first()
        if not action:
            raise HTTPException(status_code=404, detail="Action 不存在")

    fb = EpisodeFeedback(
        episode_id=episode_id,
        action_id=action.id if action else None,
        kind=body.kind,
        payload=body.payload,
        source=body.source or "mobile",
    )
    db.add(fb)

    # done / skipped 同步翻 action 状态 (如果带了 action_id)
    if action and body.kind in ("action_done", "action_skipped"):
        now = datetime.now(timezone.utc)
        if body.kind == "action_done":
            action.status = "done"
            action.completed_at = now
        else:
            action.status = "skipped"
            action.skipped_at = now
            if body.payload and isinstance(body.payload.get("reason"), str):
                action.skip_reason = body.payload["reason"][:40]

    # Increment 3 §1: 所有 action 终态 → close Episode + 写 Outcome 雏形.
    # 必须 flush 让 action 的 status 翻新可见, 然后 lifecycle 才能正确判定.
    db.flush()
    db.refresh(ep)
    maybe_close_episode(db, ep)

    db.commit()
    db.refresh(fb)
    return FeedbackOut.model_validate(fb)


# ──────────────── 生活事件(情景记忆账本,2026-07-12) ────────────────
# 对话里的行程/生活事件(出发/落地/送达/发现症状)落成 HealthEpisode 行,
# 让时间线总结读结构化 occurred_at 而不是从聊天上下文猜时间。
# 复用既有表(episode_type="life_event"),不建新表;时间解析唯一真源
# 在 services/occurred_time.py(R4:LLM 只传原话,折算在确定性代码)。

class LifeEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=80)
    # 原话时间表达:"下午" / "刚才" / "21:07" / ISO;空 = 此刻
    occurred_at: Optional[str] = Field(None, max_length=64)
    notes: Optional[str] = Field(None, max_length=500)


class LifeEventOut(BaseModel):
    id: int
    title: str
    occurred_at: datetime
    occurred_precision: str
    occurred_display: str
    notes: Optional[str] = None


def _life_event_out(ep: HealthEpisode) -> LifeEventOut:
    from app.services.occurred_time import precision_display

    snap = ep.context_snapshot or {}
    precision = str(snap.get("occurred_precision") or "exact")
    raw = snap.get("occurred_raw")
    return LifeEventOut(
        id=ep.id,
        title=ep.headline or "",
        occurred_at=ep.occurred_at,
        occurred_precision=precision,
        occurred_display=precision_display(ep.occurred_at, precision, raw),
        notes=snap.get("notes"),
    )


@router.post("/life-event", response_model=LifeEventOut, summary="记录生活事件(带发生时间)")
def create_life_event(
    payload: LifeEventCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    from app.services.occurred_time import resolve_occurred_at

    try:
        occurred, precision = resolve_occurred_at(payload.occurred_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ep = HealthEpisode(
        user_id=current_user.id,
        episode_type="life_event",
        source_type="chat",
        occurred_at=occurred,
        # 生活事件不是开环闭环流程,落地即闭合
        status="closed",
        closed_at=datetime.now(timezone.utc),
        risk_level="L0",
        headline=payload.title.strip(),
        context_snapshot={
            "occurred_raw": (payload.occurred_at or "").strip() or None,
            "occurred_precision": precision,
            "notes": (payload.notes or "").strip() or None,
        },
    )
    db.add(ep)
    db.commit()
    db.refresh(ep)
    return _life_event_out(ep)


@router.get("/me/life-events", response_model=List[LifeEventOut], summary="我的生活事件时间线")
def list_life_events(
    days: int = Query(1, ge=1, le=30),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(HealthEpisode)
        .filter(
            HealthEpisode.user_id == current_user.id,
            HealthEpisode.episode_type == "life_event",
            HealthEpisode.occurred_at >= since,
        )
        .order_by(HealthEpisode.occurred_at.asc())
        .limit(200)
        .all()
    )
    return [_life_event_out(ep) for ep in rows]
