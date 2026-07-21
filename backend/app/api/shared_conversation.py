"""对话分享 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import UTC, datetime, timedelta

from app.database import get_db
from app.models.user import User
from app.models.chat import ChatConversation, ChatMessage
from app.models.agent_conversation import AgentConversation, AgentMessage
from app.models.shared_conversation import SharedConversation
from app.api.deps import get_current_user_required
from app.services.chat_utils import refresh_chat_image_url_value

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/shared", tags=["shared-conversation"])


class ShareRequest(BaseModel):
    conversation_id: int
    source_type: str = "health"  # health / agent


class TextShareRequest(BaseModel):
    title: Optional[str] = None
    message: str


class ShareResponse(BaseModel):
    share_token: str
    share_url: str
    expires_at: Optional[str] = None


class SharedMessageOut(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None
    image_url: Optional[str] = None


class SharedConversationOut(BaseModel):
    title: str
    sharer_name: Optional[str] = None
    messages: List[SharedMessageOut]
    created_at: str
    source_type: str


def _public_site_base_url() -> str:
    from app.config import settings as _cfg
    return (_cfg.site_base_url or "https://health.executor.life").rstrip("/")


def _share_url(share_token: str) -> str:
    return f"{_public_site_base_url()}/shared/{share_token}"


def _default_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=30)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _effective_expires_at(shared: SharedConversation) -> datetime | None:
    if shared.expires_at:
        return _as_utc(shared.expires_at)
    if shared.created_at:
        return _as_utc(shared.created_at) + timedelta(days=30)
    return None


def _masked_display_name(user: User) -> Optional[str]:
    raw_name = user.name or user.username
    if not raw_name:
        return None
    if len(raw_name) > 1:
        return raw_name[0] + "*" * (len(raw_name) - 1)
    return raw_name


@router.post("/create", response_model=ShareResponse)
def create_share(
    req: ShareRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建对话分享链接"""
    # 查询对话和消息
    if req.source_type == "agent":
        conv = db.query(AgentConversation).filter(
            AgentConversation.id == req.conversation_id,
            AgentConversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        msgs = db.query(AgentMessage).filter(
            AgentMessage.conversation_id == conv.id,
        ).order_by(AgentMessage.created_at).all()
    else:
        conv = db.query(ChatConversation).filter(
            ChatConversation.id == req.conversation_id,
            ChatConversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        msgs = db.query(ChatMessage).filter(
            ChatMessage.conversation_id == conv.id,
        ).order_by(ChatMessage.created_at).all()

    if not msgs:
        raise HTTPException(status_code=400, detail="对话为空，无法分享")

    # 构建消息快照
    messages_snapshot = []
    for m in msgs:
        messages_snapshot.append({
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "image_url": getattr(m, "image_url", None),
        })

    # 检查是否已分享过（复用已有分享）
    existing = db.query(SharedConversation).filter(
        SharedConversation.user_id == current_user.id,
        SharedConversation.source_type == req.source_type,
        SharedConversation.source_conversation_id == req.conversation_id,
        SharedConversation.is_active == True,
    ).first()

    if existing:
        # 更新快照（对话可能有新消息）
        existing.messages_snapshot = messages_snapshot
        existing.title = conv.title or "分享的对话"
        existing.expires_at = _default_expires_at()
        db.commit()
        share_token = existing.share_token
        expires_at = existing.expires_at
    else:
        shared = SharedConversation(
            user_id=current_user.id,
            source_type=req.source_type,
            source_conversation_id=req.conversation_id,
            title=conv.title or "分享的对话",
            messages_snapshot=messages_snapshot,
            sharer_name=_masked_display_name(current_user),
            expires_at=_default_expires_at(),
        )
        db.add(shared)
        db.commit()
        db.refresh(shared)
        share_token = shared.share_token
        expires_at = shared.expires_at

    share_url = _share_url(share_token)
    logger.info(
        "[分享] user=%s source_type=%s source_id=%s share_id=%s",
        current_user.id,
        req.source_type,
        req.conversation_id,
        existing.id if existing else shared.id,
    )
    return ShareResponse(
        share_token=share_token,
        share_url=share_url,
        expires_at=expires_at.isoformat() if expires_at else None,
    )


@router.post("/create-text", response_model=ShareResponse)
def create_text_share(
    req: TextShareRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建普通文本分享网页, 供 mobile 系统分享/微信链接卡片使用."""
    message = (req.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="分享内容为空")

    title = (req.title or "健康分享").strip()[:200] or "健康分享"
    shared = SharedConversation(
        user_id=current_user.id,
        source_type="plain_text",
        source_conversation_id=0,
        title=title,
        messages_snapshot=[
            {"role": "assistant", "content": message, "created_at": None}
        ],
        sharer_name=_masked_display_name(current_user),
        expires_at=_default_expires_at(),
    )
    db.add(shared)
    db.commit()
    db.refresh(shared)

    logger.info("[分享] user=%s 创建文本分享 share_id=%s", current_user.id, shared.id)
    return ShareResponse(
        share_token=shared.share_token,
        share_url=_share_url(shared.share_token),
        expires_at=shared.expires_at.isoformat() if shared.expires_at else None,
    )


@router.get("/{share_token}", response_model=SharedConversationOut)
def get_shared_conversation(
    share_token: str,
    count_view: bool = True,
    db: Session = Depends(get_db),
):
    """公开访问分享的对话（无需登录）"""
    shared = db.query(SharedConversation).filter(
        SharedConversation.share_token == share_token,
        SharedConversation.is_active == True,
    ).first()
    if not shared:
        raise HTTPException(status_code=404, detail="分享链接不存在或已失效")

    # 检查过期
    expires_at = _effective_expires_at(shared)
    if expires_at:
        if datetime.now(UTC) > expires_at:
            raise HTTPException(status_code=410, detail="分享链接已过期")

    # 更新浏览计数
    if count_view:
        shared.view_count = (shared.view_count or 0) + 1
        db.commit()

    messages = [
        SharedMessageOut(
            role=m["role"],
            content=m["content"],
            created_at=m.get("created_at"),
            image_url=refresh_chat_image_url_value(m.get("image_url"), shared.user_id)
            if m.get("image_url") else None,
        )
        for m in shared.messages_snapshot
    ]

    return SharedConversationOut(
        title=shared.title,
        sharer_name=shared.sharer_name,
        messages=messages,
        created_at=shared.created_at.isoformat() if shared.created_at else "",
        source_type=shared.source_type,
    )


@router.delete("/{share_token}")
def revoke_share(
    share_token: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """撤销分享"""
    shared = db.query(SharedConversation).filter(
        SharedConversation.share_token == share_token,
        SharedConversation.user_id == current_user.id,
    ).first()
    if not shared:
        raise HTTPException(status_code=404, detail="分享不存在")
    shared.is_active = False
    db.commit()
    return {"message": "已撤销分享"}
