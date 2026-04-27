"""
ActionCard API —— 对话固化到首页。

- GET    /action-cards/me              获取当前用户的活跃卡片
- POST   /action-cards                 创建卡片
- POST   /action-cards/from-message    从 AI 消息一键固化（自动提取标题）
- PATCH  /action-cards/{id}            更新状态/标题
- DELETE /action-cards/{id}            归档
"""

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.action_card import ActionCard
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action-cards", tags=["action-cards"])


# ─────────────────────── Schemas ────────────────────────


ActionMetricKey = Literal["sleep_score", "hrv", "rhr", "weight", "bp", "spo2_odi", "custom"]


class ChecklistItem(BaseModel):
    item: str = Field(..., min_length=1, max_length=200)
    done: bool = False


class ActionCardCreate(BaseModel):
    title: str = Field(..., max_length=200)
    content: str
    card_type: str = "note"
    color: Optional[str] = None
    source_type: str = "manual"
    source_id: Optional[str] = None
    priority: int = 0
    expires_at: Optional[datetime] = None
    metric_key: Optional[ActionMetricKey] = None
    baseline_value: Optional[str] = Field(None, max_length=100)
    target_value: Optional[str] = Field(None, max_length=100)
    verification_days: Optional[int] = Field(None, ge=1, le=90)
    checklist: list[ChecklistItem] = Field(default_factory=list)


class ActionCardFromMessage(BaseModel):
    content: str = Field(..., description="AI 消息的完整内容（markdown）")
    source_id: Optional[str] = None
    card_type: str = "plan"


class ActionCardUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None  # active / completed / archived
    priority: Optional[int] = None
    is_visible: Optional[bool] = None
    color: Optional[str] = None


class LatestAssessmentInput(BaseModel):
    score: Optional[int] = Field(None, ge=0, le=10)
    summary: str = Field(..., max_length=1000)
    evidence: list[str] = Field(default_factory=list)


class ActionCardReview(BaseModel):
    status: Literal["active", "completed", "archived"] = "completed"
    outcome_status: Literal["met", "not_met", "inconclusive", "pending"]
    actual_value: Optional[str] = Field(None, max_length=100)
    latest_assessment: LatestAssessmentInput


# ─────────────────────── 工具 ────────────────────────


def _extract_title(content: str, max_len: int = 60) -> str:
    """从 markdown 内容自动提取标题。"""
    # 尝试取第一个 # 标题
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("#"):
            title = re.sub(r"^#+\s*", "", line).strip()
            if title:
                return title[:max_len]

    # 尝试取第一个加粗文本
    bold = re.search(r"\*\*(.+?)\*\*", content)
    if bold:
        return bold.group(1)[:max_len]

    # 取第一行非空文本
    for line in content.split("\n"):
        line = line.strip()
        if line and not line.startswith("```") and not line.startswith("---"):
            return line[:max_len]

    return "行动卡片"


# ─────────────────────── 端点 ────────────────────────


@router.get("/me")
def get_my_cards(
    status: str = Query("active", description="active / completed / archived / all"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """获取当前用户的行动卡片。"""
    q = db.query(ActionCard).filter(
        ActionCard.user_id == current_user.id,
        ActionCard.is_visible == True,  # noqa: E712
    )
    if status != "all":
        q = q.filter(ActionCard.status == status)
    cards = q.order_by(desc(ActionCard.priority), desc(ActionCard.created_at)).limit(limit).all()

    return [_card_to_dict(c) for c in cards]


@router.post("")
def create_card(
    body: ActionCardCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """手动创建卡片。"""
    expires_at = body.expires_at
    if expires_at is None and body.verification_days is not None:
        expires_at = datetime.now(UTC) + timedelta(days=body.verification_days)

    card = ActionCard(
        user_id=current_user.id,
        title=body.title,
        content=body.content,
        card_type=body.card_type,
        color=body.color,
        source_type=body.source_type,
        source_id=body.source_id,
        priority=body.priority,
        expires_at=expires_at,
        metric_key=body.metric_key,
        baseline_value=body.baseline_value,
        target_value=body.target_value,
        verification_days=body.verification_days,
        checklist=[item.model_dump() for item in body.checklist],
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    return _card_to_dict(card)


@router.post("/from-message")
def create_from_message(
    body: ActionCardFromMessage,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """
    从 AI 消息一键固化。自动提取标题。

    前端传 AI 回答的完整 markdown 内容，后端自动：
    1. 提取标题（第一个 # 标题 / 加粗文本 / 首行）
    2. 创建卡片
    """
    title = _extract_title(body.content)
    card = ActionCard(
        user_id=current_user.id,
        title=title,
        content=body.content,
        card_type=body.card_type,
        source_type="conversation",
        source_id=body.source_id,
        priority=10,  # 从对话固化的默认优先级高
    )
    db.add(card)
    db.commit()
    db.refresh(card)
    logger.info(f"[ActionCard] 用户 {current_user.id} 从对话固化: {title}")
    return _card_to_dict(card)


@router.patch("/{card_id}")
def update_card(
    card_id: int,
    body: ActionCardUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """更新卡片状态/标题/优先级。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    if body.title is not None:
        card.title = body.title
    if body.status is not None:
        card.status = body.status
        if body.status == "completed":
            card.completed_at = datetime.now(UTC)
    if body.priority is not None:
        card.priority = body.priority
    if body.is_visible is not None:
        card.is_visible = body.is_visible
    if body.color is not None:
        card.color = body.color

    db.commit()
    db.refresh(card)
    return _card_to_dict(card)


@router.post("/{card_id}/review")
def review_card(
    card_id: int,
    body: ActionCardReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """写入行动卡片复盘结果。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")

    card.status = body.status
    if body.status == "completed":
        card.completed_at = datetime.now(UTC)
    card.latest_assessment = {
        **body.latest_assessment.model_dump(),
        "outcome_status": body.outcome_status,
        "actual_value": body.actual_value,
    }
    card.last_assessed_at = datetime.now(UTC)
    card.assessment_count = (card.assessment_count or 0) + 1

    db.commit()
    db.refresh(card)
    logger.info(f"[ActionCard] 用户 {current_user.id} 复盘行动卡片: card_id={card_id}, outcome={body.outcome_status}")
    return _card_to_dict(card)


@router.delete("/{card_id}")
def archive_card(
    card_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """归档卡片（软删除）。"""
    card = db.query(ActionCard).filter(
        ActionCard.id == card_id,
        ActionCard.user_id == current_user.id,
    ).first()
    if not card:
        raise HTTPException(status_code=404, detail="卡片不存在")
    card.status = "archived"
    card.is_visible = False
    db.commit()
    return {"message": "已归档", "id": card_id}


# ─────────────────────── 序列化 ────────────────────────


def _card_to_dict(card: ActionCard) -> dict:
    return {
        "id": card.id,
        "title": card.title,
        "content": card.content,
        "card_type": card.card_type,
        "color": card.color,
        "source_type": card.source_type,
        "source_id": card.source_id,
        "status": card.status,
        "priority": card.priority,
        "expires_at": card.expires_at.isoformat() if card.expires_at else None,
        "completed_at": card.completed_at.isoformat() if card.completed_at else None,
        "created_at": card.created_at.isoformat() if card.created_at else None,
        "checklist": card.checklist or [],
        "latest_assessment": card.latest_assessment,
        "metric_key": card.metric_key,
        "baseline_value": card.baseline_value,
        "target_value": card.target_value,
        "verification_days": card.verification_days,
    }
