"""对话分享 API"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.chat import ChatConversation, ChatMessage
from app.models.openclaw import OpenClawConversation, OpenClawMessage
from app.models.shared_conversation import SharedConversation
from app.api.deps import get_current_user_required

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/shared", tags=["shared-conversation"])


class ShareRequest(BaseModel):
    conversation_id: int
    source_type: str = "health"  # health / openclaw


class TextShareRequest(BaseModel):
    title: Optional[str] = None
    message: str


class ShareResponse(BaseModel):
    share_token: str
    share_url: str


class SharedMessageOut(BaseModel):
    role: str
    content: str
    created_at: Optional[str] = None


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
    if req.source_type == "openclaw":
        conv = db.query(OpenClawConversation).filter(
            OpenClawConversation.id == req.conversation_id,
            OpenClawConversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="对话不存在")
        msgs = db.query(OpenClawMessage).filter(
            OpenClawMessage.conversation_id == conv.id,
        ).order_by(OpenClawMessage.created_at).all()
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
        db.commit()
        share_token = existing.share_token
    else:
        shared = SharedConversation(
            user_id=current_user.id,
            source_type=req.source_type,
            source_conversation_id=req.conversation_id,
            title=conv.title or "分享的对话",
            messages_snapshot=messages_snapshot,
            sharer_name=_masked_display_name(current_user),
        )
        db.add(shared)
        db.commit()
        db.refresh(shared)
        share_token = shared.share_token

    share_url = _share_url(share_token)
    logger.info(f"[分享] 用户 {current_user.id} 分享对话 {req.source_type}:{req.conversation_id} -> {share_token}")
    return ShareResponse(share_token=share_token, share_url=share_url)


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
    )
    db.add(shared)
    db.commit()
    db.refresh(shared)

    logger.info(f"[分享] 用户 {current_user.id} 创建文本分享 -> {shared.share_token}")
    return ShareResponse(share_token=shared.share_token, share_url=_share_url(shared.share_token))


@router.get("/{share_token}", response_model=SharedConversationOut)
def get_shared_conversation(
    share_token: str,
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
    if shared.expires_at:
        from datetime import UTC, datetime
        if datetime.now(UTC) > shared.expires_at:
            raise HTTPException(status_code=410, detail="分享链接已过期")

    # 更新浏览计数
    shared.view_count = (shared.view_count or 0) + 1
    db.commit()

    messages = [
        SharedMessageOut(
            role=m["role"],
            content=m["content"],
            created_at=m.get("created_at"),
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
