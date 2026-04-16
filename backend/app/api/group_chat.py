"""群聊 API"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.friendship import Friendship
from app.models.group_chat import GroupChat, GroupMember, GroupMessage
from sqlalchemy import or_, and_

logger = logging.getLogger(__name__)

# 仅允许访问群聊功能的用户白名单
_GROUP_CHAT_ALLOWED_EMAILS = {"itsoso@126.com"}


async def _require_group_chat_access(
    current_user: User = Depends(get_current_user_required),
):
    """群聊功能访问控制：仅白名单用户可访问"""
    if current_user.email not in _GROUP_CHAT_ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="群聊功能暂未开放")


router = APIRouter(
    prefix="/groups",
    tags=["群聊"],
    dependencies=[Depends(_require_group_chat_access)],
)


# ─── Schemas ─────────────────────────────────────────────────────────────────

class GroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    member_ids: List[int] = Field(..., min_length=1)  # 被邀请的好友 id 列表


class GroupUpdateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)


class GroupAddMemberRequest(BaseModel):
    user_id: int


class GroupMsgSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class MemberInfo(BaseModel):
    user_id: int
    name: str
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupMsgResponse(BaseModel):
    id: int
    group_id: int
    sender_id: int
    sender_name: str
    sender_avatar: Optional[str] = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupListItem(BaseModel):
    id: int
    name: str
    avatar_url: Optional[str] = None
    member_count: int
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime


class GroupDetail(BaseModel):
    id: int
    name: str
    avatar_url: Optional[str] = None
    creator_id: int
    members: List[MemberInfo]
    created_at: datetime


# ─── 工具函数 ──────────────────────────────────────────────────────────────────

def _is_friend(db: Session, user_id: int, other_id: int) -> bool:
    return db.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == user_id, Friendship.friend_id == other_id),
            and_(Friendship.user_id == other_id, Friendship.friend_id == user_id),
        ),
        Friendship.status == "accepted",
    ).first() is not None


def _get_member(db: Session, group_id: int, user_id: int) -> Optional[GroupMember]:
    return db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == user_id,
    ).first()


# ─── 创建群聊 ──────────────────────────────────────────────────────────────────

@router.post("", response_model=GroupDetail, summary="创建群聊")
async def create_group(
    req: GroupCreateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    # 验证所有被邀请的人都是好友
    for uid in req.member_ids:
        if uid == current_user.id:
            continue
        if not _is_friend(db, current_user.id, uid):
            raise HTTPException(status_code=400, detail=f"用户 {uid} 不是你的好友")

    group = GroupChat(name=req.name, creator_id=current_user.id)
    db.add(group)
    db.flush()

    # 创建者为 owner
    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role="owner"))
    # 其他成员
    added = {current_user.id}
    for uid in req.member_ids:
        if uid not in added:
            db.add(GroupMember(group_id=group.id, user_id=uid, role="member"))
            added.add(uid)

    db.commit()
    db.refresh(group)
    return _build_detail(group, db)


# ─── 我的群聊列表 ───────────────────────────────────────────────────────────────

@router.get("", response_model=List[GroupListItem], summary="我的群聊列表")
async def list_groups(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    my_group_ids = db.query(GroupMember.group_id).filter(
        GroupMember.user_id == current_user.id
    ).scalar_subquery()

    groups = db.query(GroupChat).filter(
        GroupChat.id.in_(my_group_ids)
    ).order_by(GroupChat.updated_at.desc().nulls_last(), desc(GroupChat.created_at)).all()

    result = []
    for g in groups:
        member_count = len(g.members)
        last_msg = db.query(GroupMessage).filter(
            GroupMessage.group_id == g.id
        ).order_by(desc(GroupMessage.created_at)).first()
        result.append(GroupListItem(
            id=g.id,
            name=g.name,
            avatar_url=g.avatar_url,
            member_count=member_count,
            last_message=last_msg.content[:50] if last_msg else None,
            last_message_at=last_msg.created_at if last_msg else None,
            created_at=g.created_at,
        ))
    return result


# ─── 群聊详情 ──────────────────────────────────────────────────────────────────

@router.get("/{group_id}", response_model=GroupDetail, summary="群聊详情")
async def get_group(
    group_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    group = _get_group_or_404(db, group_id, current_user.id)
    return _build_detail(group, db)


# ─── 修改群名称（仅 owner）────────────────────────────────────────────────────

@router.put("/{group_id}", response_model=GroupDetail, summary="修改群名称")
async def update_group(
    group_id: int,
    req: GroupUpdateRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    group = _get_group_or_404(db, group_id, current_user.id)
    member = _get_member(db, group_id, current_user.id)
    if not member or member.role != "owner":
        raise HTTPException(status_code=403, detail="只有群主才能修改群名称")
    group.name = req.name
    db.commit()
    db.refresh(group)
    return _build_detail(group, db)


# ─── 发消息 ────────────────────────────────────────────────────────────────────

@router.post("/{group_id}/messages", response_model=GroupMsgResponse, summary="发送群消息")
async def send_message(
    group_id: int,
    req: GroupMsgSendRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    _get_group_or_404(db, group_id, current_user.id)
    msg = GroupMessage(
        group_id=group_id,
        sender_id=current_user.id,
        content=req.content,
    )
    db.add(msg)
    # 更新群 updated_at（用于列表排序）
    db.query(GroupChat).filter(GroupChat.id == group_id).update(
        {"updated_at": datetime.now(timezone.utc)}
    )
    db.commit()
    db.refresh(msg)
    return _build_msg_response(msg)


# ─── 消息历史 ──────────────────────────────────────────────────────────────────

@router.get("/{group_id}/messages", summary="群消息历史")
async def get_messages(
    group_id: int,
    before_id: Optional[int] = Query(None, description="分页游标，返回此 ID 之前的消息"),
    limit: int = Query(50, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    _get_group_or_404(db, group_id, current_user.id)

    query = db.query(GroupMessage).filter(GroupMessage.group_id == group_id)
    if before_id:
        query = query.filter(GroupMessage.id < before_id)
    msgs = query.order_by(desc(GroupMessage.id)).limit(limit).all()
    msgs = list(reversed(msgs))

    return {
        "messages": [_build_msg_response(m).__dict__ for m in msgs],
        "has_more": len(msgs) == limit,
    }


# ─── 添加成员（仅 owner）──────────────────────────────────────────────────────

@router.post("/{group_id}/members", summary="添加群成员")
async def add_member(
    group_id: int,
    req: GroupAddMemberRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    group = _get_group_or_404(db, group_id, current_user.id)
    me = _get_member(db, group_id, current_user.id)
    if not me or me.role != "owner":
        raise HTTPException(status_code=403, detail="只有群主才能添加成员")
    if not _is_friend(db, current_user.id, req.user_id):
        raise HTTPException(status_code=400, detail="只能邀请好友入群")
    existing = _get_member(db, group_id, req.user_id)
    if existing:
        raise HTTPException(status_code=400, detail="该用户已在群内")
    db.add(GroupMember(group_id=group_id, user_id=req.user_id, role="member"))
    db.commit()
    return {"message": "已添加成员"}


# ─── 移除成员（仅 owner）──────────────────────────────────────────────────────

@router.delete("/{group_id}/members/{user_id}", summary="移除群成员")
async def remove_member(
    group_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    _get_group_or_404(db, group_id, current_user.id)
    me = _get_member(db, group_id, current_user.id)
    if not me or me.role != "owner":
        raise HTTPException(status_code=403, detail="只有群主才能移除成员")
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能移除自己，请使用解散群功能")
    target = _get_member(db, group_id, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="该成员不在群内")
    db.delete(target)
    db.commit()
    return {"message": "已移除成员"}


# ─── 退群 ──────────────────────────────────────────────────────────────────────

@router.post("/{group_id}/leave", summary="退出群聊")
async def leave_group(
    group_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    _get_group_or_404(db, group_id, current_user.id)
    me = _get_member(db, group_id, current_user.id)
    if not me:
        raise HTTPException(status_code=404, detail="你不在该群中")
    if me.role == "owner":
        raise HTTPException(status_code=400, detail="群主不能直接退群，请先转让群主或解散群")
    db.delete(me)
    db.commit()
    return {"message": "已退出群聊"}


# ─── 解散群（仅 owner）────────────────────────────────────────────────────────

@router.delete("/{group_id}", summary="解散群聊（仅群主）")
async def dissolve_group(
    group_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    group = _get_group_or_404(db, group_id, current_user.id)
    me = _get_member(db, group_id, current_user.id)
    if not me or me.role != "owner":
        raise HTTPException(status_code=403, detail="只有群主才能解散群聊")
    db.delete(group)
    db.commit()
    return {"message": "群聊已解散"}


# ─── 内部工具 ──────────────────────────────────────────────────────────────────

def _get_group_or_404(db: Session, group_id: int, user_id: int) -> GroupChat:
    group = db.query(GroupChat).filter(GroupChat.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="群聊不存在")
    member = _get_member(db, group_id, user_id)
    if not member:
        raise HTTPException(status_code=403, detail="你不在该群聊中")
    return group


def _build_detail(group: GroupChat, db: Session) -> GroupDetail:
    members = []
    for m in group.members:
        u = db.query(User).filter(User.id == m.user_id).first()
        members.append(MemberInfo(
            user_id=m.user_id,
            name=u.name if u else "未知",
            avatar_url=u.avatar_url if u else None,
            role=m.role,
            joined_at=m.joined_at,
        ))
    return GroupDetail(
        id=group.id,
        name=group.name,
        avatar_url=group.avatar_url,
        creator_id=group.creator_id,
        members=members,
        created_at=group.created_at,
    )


def _build_msg_response(msg: GroupMessage) -> GroupMsgResponse:
    sender = msg.sender
    return GroupMsgResponse(
        id=msg.id,
        group_id=msg.group_id,
        sender_id=msg.sender_id,
        sender_name=sender.name if sender else "未知",
        sender_avatar=sender.avatar_url if sender else None,
        content=msg.content,
        created_at=msg.created_at,
    )
