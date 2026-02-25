"""私信聊天 API"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc, case

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.friendship import Friendship
from app.models.direct_message import DirectMessage
from app.schemas.direct_message import (
    DMSendRequest, DMResponse, DMConversationItem,
    DMHistoryResponse, DMUnreadCountResponse,
)

router = APIRouter(prefix="/dm", tags=["私信"])


def _check_friendship(db: Session, user_id: int, friend_id: int):
    """检查两人是否是好友"""
    friendship = db.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == user_id, Friendship.friend_id == friend_id),
            and_(Friendship.user_id == friend_id, Friendship.friend_id == user_id),
        ),
        Friendship.status == "accepted",
    ).first()
    if not friendship:
        raise HTTPException(status_code=403, detail="只能给好友发消息")
    return friendship


@router.get("/conversations", response_model=List[DMConversationItem], summary="获取对话列表")
async def get_conversations(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    uid = current_user.id

    # 找出所有跟当前用户有消息往来的对方用户
    # 子查询：每个对话的最新消息
    friend_id_col = case(
        (DirectMessage.sender_id == uid, DirectMessage.receiver_id),
        else_=DirectMessage.sender_id,
    ).label("friend_id")

    sub = (
        db.query(
            friend_id_col,
            func.max(DirectMessage.id).label("last_msg_id"),
        )
        .filter(or_(DirectMessage.sender_id == uid, DirectMessage.receiver_id == uid))
        .group_by(friend_id_col)
        .subquery()
    )

    # 连接获取最新消息详情
    rows = (
        db.query(
            sub.c.friend_id,
            DirectMessage.content,
            DirectMessage.created_at,
            DirectMessage.id,
        )
        .join(DirectMessage, DirectMessage.id == sub.c.last_msg_id)
        .order_by(desc(DirectMessage.created_at))
        .all()
    )

    if not rows:
        return []

    # 获取好友信息和未读数
    friend_ids = [r.friend_id for r in rows]
    friends = {u.id: u for u in db.query(User).filter(User.id.in_(friend_ids)).all()}

    # 未读数：对方发给我的、未读的
    unread_counts = dict(
        db.query(DirectMessage.sender_id, func.count(DirectMessage.id))
        .filter(
            DirectMessage.receiver_id == uid,
            DirectMessage.is_read == False,
            DirectMessage.sender_id.in_(friend_ids),
        )
        .group_by(DirectMessage.sender_id)
        .all()
    )

    result = []
    for r in rows:
        friend = friends.get(r.friend_id)
        if not friend:
            continue
        result.append(DMConversationItem(
            friend_id=r.friend_id,
            friend_name=friend.name or friend.username or f"用户{friend.id}",
            friend_avatar=friend.avatar_url if hasattr(friend, 'avatar_url') else None,
            last_message=r.content[:50] if r.content else "",
            last_message_time=r.created_at,
            unread_count=unread_counts.get(r.friend_id, 0),
        ))

    return result


@router.get("/messages/{friend_id}", response_model=DMHistoryResponse, summary="获取消息历史")
async def get_messages(
    friend_id: int,
    before_id: int = Query(0, description="分页: 获取此ID之前的消息"),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    uid = current_user.id
    _check_friendship(db, uid, friend_id)

    query = db.query(DirectMessage).filter(
        or_(
            and_(DirectMessage.sender_id == uid, DirectMessage.receiver_id == friend_id),
            and_(DirectMessage.sender_id == friend_id, DirectMessage.receiver_id == uid),
        )
    )
    if before_id > 0:
        query = query.filter(DirectMessage.id < before_id)

    messages = query.order_by(desc(DirectMessage.id)).limit(limit + 1).all()
    has_more = len(messages) > limit
    messages = messages[:limit]
    messages.reverse()  # 按时间正序返回

    # 获取发送者信息
    friend = db.query(User).filter(User.id == friend_id).first()
    sender_map = {
        uid: (current_user.name or current_user.username or f"用户{uid}", None),
        friend_id: (
            (friend.name or friend.username or f"用户{friend_id}") if friend else f"用户{friend_id}",
            friend.avatar_url if friend and hasattr(friend, 'avatar_url') else None,
        ),
    }

    result = []
    for m in messages:
        name, avatar = sender_map.get(m.sender_id, (f"用户{m.sender_id}", None))
        result.append(DMResponse(
            id=m.id,
            sender_id=m.sender_id,
            receiver_id=m.receiver_id,
            content=m.content,
            is_read=m.is_read,
            created_at=m.created_at,
            sender_name=name,
            sender_avatar=avatar,
        ))

    return DMHistoryResponse(messages=result, has_more=has_more)


@router.post("/send", response_model=DMResponse, summary="发送消息")
async def send_message(
    payload: DMSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    _check_friendship(db, current_user.id, payload.receiver_id)

    msg = DirectMessage(
        sender_id=current_user.id,
        receiver_id=payload.receiver_id,
        content=payload.content,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    return DMResponse(
        id=msg.id,
        sender_id=msg.sender_id,
        receiver_id=msg.receiver_id,
        content=msg.content,
        is_read=msg.is_read,
        created_at=msg.created_at,
        sender_name=current_user.name or current_user.username or f"用户{current_user.id}",
        sender_avatar=None,
    )


@router.put("/read/{friend_id}", summary="标记与某好友的消息已读")
async def mark_read(
    friend_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    count = db.query(DirectMessage).filter(
        DirectMessage.sender_id == friend_id,
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.is_read == False,
    ).update({"is_read": True})
    db.commit()
    return {"marked_read": count}


@router.get("/unread-count", response_model=DMUnreadCountResponse, summary="获取总未读消息数")
async def get_unread_count(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    count = db.query(func.count(DirectMessage.id)).filter(
        DirectMessage.receiver_id == current_user.id,
        DirectMessage.is_read == False,
    ).scalar() or 0
    return DMUnreadCountResponse(total_unread=count)
