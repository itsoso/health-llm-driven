"""好友关系 API"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.friendship import Friendship
from app.schemas.friendship import (
    FriendRequestCreate, FriendRequestResponse,
    FriendInfo, UserSearchResult,
)

router = APIRouter(prefix="/friends", tags=["好友"])


@router.post("/request", response_model=FriendRequestResponse, summary="发送好友请求")
async def send_friend_request(
    data: FriendRequestCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    if data.friend_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能添加自己为好友")

    # 检查对方是否存在
    friend = db.query(User).filter(User.id == data.friend_id, User.is_active == True).first()
    if not friend:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 检查是否已有关系
    existing = db.query(Friendship).filter(
        or_(
            and_(Friendship.user_id == current_user.id, Friendship.friend_id == data.friend_id),
            and_(Friendship.user_id == data.friend_id, Friendship.friend_id == current_user.id),
        )
    ).first()

    if existing:
        if existing.status == "accepted":
            raise HTTPException(status_code=400, detail="你们已经是好友了")
        if existing.status == "pending":
            # 如果对方之前向我发的请求还在pending，直接同意
            if existing.user_id == data.friend_id:
                existing.status = "accepted"
                db.commit()
                db.refresh(existing)
                return _build_request_response(existing, db)
            raise HTTPException(status_code=400, detail="已发送过好友请求，等待对方确认")
        if existing.status == "rejected":
            # 重新发送
            existing.user_id = current_user.id
            existing.friend_id = data.friend_id
            existing.status = "pending"
            existing.message = data.message
            db.commit()
            db.refresh(existing)
            return _build_request_response(existing, db)

    record = Friendship(
        user_id=current_user.id,
        friend_id=data.friend_id,
        status="pending",
        message=data.message,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _build_request_response(record, db)


@router.put("/request/{request_id}/accept", response_model=FriendRequestResponse, summary="接受好友请求")
async def accept_request(
    request_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(Friendship).filter(
        Friendship.id == request_id,
        Friendship.friend_id == current_user.id,
        Friendship.status == "pending",
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="好友请求不存在")

    record.status = "accepted"
    db.commit()
    db.refresh(record)
    return _build_request_response(record, db)


@router.put("/request/{request_id}/reject", response_model=FriendRequestResponse, summary="拒绝好友请求")
async def reject_request(
    request_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(Friendship).filter(
        Friendship.id == request_id,
        Friendship.friend_id == current_user.id,
        Friendship.status == "pending",
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="好友请求不存在")

    record.status = "rejected"
    db.commit()
    db.refresh(record)
    return _build_request_response(record, db)


@router.get("/list", response_model=List[FriendInfo], summary="我的好友列表")
async def list_friends(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    friendships = db.query(Friendship).filter(
        or_(
            Friendship.user_id == current_user.id,
            Friendship.friend_id == current_user.id,
        ),
        Friendship.status == "accepted",
    ).all()

    result = []
    for f in friendships:
        other_id = f.friend_id if f.user_id == current_user.id else f.user_id
        other = db.query(User).filter(User.id == other_id).first()
        if other:
            result.append(FriendInfo(
                user_id=other.id,
                name=other.name,
                avatar_url=other.avatar_url,
                friendship_id=f.id,
                since=f.updated_at or f.created_at,
            ))
    return result


@router.get("/requests/pending", response_model=List[FriendRequestResponse], summary="待处理的好友请求")
async def pending_requests(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    records = db.query(Friendship).filter(
        Friendship.friend_id == current_user.id,
        Friendship.status == "pending",
    ).all()
    return [_build_request_response(r, db) for r in records]


@router.delete("/{friendship_id}", summary="删除好友")
async def remove_friend(
    friendship_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    record = db.query(Friendship).filter(
        Friendship.id == friendship_id,
        or_(
            Friendship.user_id == current_user.id,
            Friendship.friend_id == current_user.id,
        ),
        Friendship.status == "accepted",
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="好友关系不存在")

    db.delete(record)
    db.commit()
    return {"message": "好友已删除"}


@router.get("/search", response_model=List[UserSearchResult], summary="搜索用户")
async def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(
        User.is_active == True,
        User.id != current_user.id,
        or_(
            User.name.ilike(f"%{q}%"),
            User.username.ilike(f"%{q}%"),
        ),
    ).limit(20).all()

    # 检查好友状态
    my_friendships = db.query(Friendship).filter(
        or_(
            Friendship.user_id == current_user.id,
            Friendship.friend_id == current_user.id,
        ),
    ).all()

    friend_map = {}  # user_id -> status
    for f in my_friendships:
        other_id = f.friend_id if f.user_id == current_user.id else f.user_id
        friend_map[other_id] = f.status

    result = []
    for u in users:
        status = friend_map.get(u.id)
        result.append(UserSearchResult(
            id=u.id,
            name=u.name,
            avatar_url=u.avatar_url,
            is_friend=status == "accepted",
            request_pending=status == "pending",
        ))
    return result


def _build_request_response(record: Friendship, db: Session) -> FriendRequestResponse:
    user = db.query(User).filter(User.id == record.user_id).first()
    friend = db.query(User).filter(User.id == record.friend_id).first()
    return FriendRequestResponse(
        id=record.id,
        user_id=record.user_id,
        friend_id=record.friend_id,
        status=record.status,
        message=record.message,
        created_at=record.created_at,
        user_name=user.name if user else None,
        user_avatar=user.avatar_url if user else None,
        friend_name=friend.name if friend else None,
        friend_avatar=friend.avatar_url if friend else None,
    )
