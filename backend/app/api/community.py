"""Opt-in anonymous peer support for verified health execution events."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.community import CommunityPost, CommunityReaction, CommunityReport
from app.models.daily_health import DietRecord
from app.models.user import User
from app.schemas.community import (
    CommunityFeedResponse,
    CommunityPostCreate,
    CommunityPostResponse,
    CommunityReactionUpdate,
    CommunityReportCreate,
    CommunityReportResponse,
)
from app.utils.number_format import format_card_numbers

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/community", tags=["community"])

REACTIONS = ("support", "same_path", "learned")
REPORT_REVIEW_THRESHOLD = 3


def _diet_snapshot(record: DietRecord) -> dict[str, Any]:
    """Strict public allowlist. Never add fields by serializing the ORM object."""
    return format_card_numbers(
        {
            "meal_type": record.meal_type,
            "record_date": record.record_date.isoformat(),
            "food_items": record.food_items or record.food_name or "",
            "calories": record.calories,
            "protein": record.protein,
            "carbs": record.carbs,
            "fat": record.fat,
            "fiber": record.fiber,
        }
    )


def _serialize_posts(
    db: Session,
    posts: list[CommunityPost],
    viewer_id: int,
) -> list[dict[str, Any]]:
    """Serialize a feed in two bounded lookups, independent of page size."""
    if not posts:
        return []
    post_ids = [post.id for post in posts]
    counts_by_post = {
        post_id: {name: 0 for name in REACTIONS}
        for post_id in post_ids
    }
    count_rows = (
        db.query(
            CommunityReaction.post_id,
            CommunityReaction.reaction,
            func.count(CommunityReaction.id),
        )
        .filter(CommunityReaction.post_id.in_(post_ids))
        .group_by(CommunityReaction.post_id, CommunityReaction.reaction)
        .all()
    )
    for post_id, reaction, count in count_rows:
        if reaction in counts_by_post[post_id]:
            counts_by_post[post_id][reaction] = int(count)

    mine_by_post = {
        reaction.post_id: reaction.reaction
        for reaction in (
            db.query(CommunityReaction)
            .filter(
                CommunityReaction.post_id.in_(post_ids),
                CommunityReaction.user_id == viewer_id,
            )
            .all()
        )
    }
    return [
        {
            "id": post.id,
            "anonymous_name": "同行者",
            "source_type": post.source_type,
            "snapshot": post.snapshot,
            "caption": post.caption,
            "status": post.status,
            "reaction_counts": counts_by_post[post.id],
            "my_reaction": mine_by_post.get(post.id),
            "is_owner": post.user_id == viewer_id,
            "created_at": post.created_at,
        }
        for post in posts
    ]


def _serialize_post(db: Session, post: CommunityPost, viewer_id: int) -> dict[str, Any]:
    return _serialize_posts(db, [post], viewer_id)[0]


def _active_post_or_404(db: Session, post_id: int) -> CommunityPost:
    post = (
        db.query(CommunityPost)
        .filter(CommunityPost.id == post_id, CommunityPost.status == "active")
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    return post


def _owned_source_post(
    db: Session,
    *,
    user_id: int,
    source_type: str,
    source_id: int,
) -> CommunityPost | None:
    return (
        db.query(CommunityPost)
        .filter(
            CommunityPost.user_id == user_id,
            CommunityPost.source_type == source_type,
            CommunityPost.source_id == source_id,
            CommunityPost.status != "deleted",
        )
        .order_by(CommunityPost.id.desc())
        .first()
    )


@router.post("/posts", response_model=CommunityPostResponse)
async def create_post(
    data: CommunityPostCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    existing = (
        db.query(CommunityPost)
        .filter(
            CommunityPost.user_id == current_user.id,
            CommunityPost.idempotency_key == data.idempotency_key,
        )
        .first()
    )
    if existing is not None:
        return _serialize_post(db, existing, current_user.id)

    existing_source = _owned_source_post(
        db,
        user_id=current_user.id,
        source_type=data.source_type,
        source_id=data.source_id,
    )
    if existing_source is not None:
        if existing_source.status == "under_review":
            raise HTTPException(status_code=409, detail="这条分享正在审核，暂时不能重复发布")
        return _serialize_post(db, existing_source, current_user.id)

    record = (
        db.query(DietRecord)
        .filter(DietRecord.id == data.source_id, DietRecord.user_id == current_user.id)
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="饮食记录不存在")

    post = CommunityPost(
        user_id=current_user.id,
        source_type=data.source_type,
        source_id=record.id,
        snapshot=_diet_snapshot(record),
        caption=(data.caption or "").strip() or None,
        idempotency_key=data.idempotency_key,
        status="active",
    )
    db.add(post)
    try:
        db.commit()
        db.refresh(post)
    except IntegrityError:
        db.rollback()
        post = (
            db.query(CommunityPost)
            .filter(
                CommunityPost.user_id == current_user.id,
                CommunityPost.idempotency_key == data.idempotency_key,
            )
            .first()
        )
        if post is None:
            post = _owned_source_post(
                db,
                user_id=current_user.id,
                source_type=data.source_type,
                source_id=data.source_id,
            )
        if post is None:
            raise
        if post.status == "under_review":
            raise HTTPException(status_code=409, detail="这条分享正在审核，暂时不能重复发布")
        return _serialize_post(db, post, current_user.id)
    logger.info(
        "[community] post created post_id=%s user_id=%s source_id=%s",
        post.id,
        current_user.id,
        record.id,
    )
    return JSONResponse(
        status_code=201,
        content=jsonable_encoder(_serialize_post(db, post, current_user.id)),
    )


@router.get(
    "/posts/source/diet_record/{source_id}",
    response_model=CommunityPostResponse,
)
async def get_diet_post_by_source(
    source_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    post = _owned_source_post(
        db,
        user_id=current_user.id,
        source_type="diet_record",
        source_id=source_id,
    )
    if post is None:
        raise HTTPException(status_code=404, detail="分享不存在")
    return _serialize_post(db, post, current_user.id)


@router.get("/posts", response_model=CommunityFeedResponse)
async def list_posts(
    limit: int = Query(default=20, ge=1, le=50),
    before_id: int | None = Query(default=None, gt=0),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(CommunityPost).filter(CommunityPost.status == "active")
    if before_id is not None:
        query = query.filter(CommunityPost.id < before_id)
    posts = query.order_by(CommunityPost.id.desc()).limit(limit).all()
    return {"items": _serialize_posts(db, posts, current_user.id)}


@router.put("/posts/{post_id}/reaction", response_model=CommunityPostResponse)
async def set_reaction(
    post_id: int,
    data: CommunityReactionUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    post = _active_post_or_404(db, post_id)
    reaction = (
        db.query(CommunityReaction)
        .filter(
            CommunityReaction.post_id == post_id,
            CommunityReaction.user_id == current_user.id,
        )
        .first()
    )
    if reaction is None:
        reaction = CommunityReaction(
            post_id=post_id,
            user_id=current_user.id,
            reaction=data.reaction,
        )
        db.add(reaction)
    else:
        reaction.reaction = data.reaction
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        reaction = (
            db.query(CommunityReaction)
            .filter(
                CommunityReaction.post_id == post_id,
                CommunityReaction.user_id == current_user.id,
            )
            .first()
        )
        if reaction is None:
            raise
        reaction.reaction = data.reaction
        db.commit()
    return _serialize_post(db, post, current_user.id)


@router.delete("/posts/{post_id}/reaction", response_model=CommunityPostResponse)
async def delete_reaction(
    post_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    post = _active_post_or_404(db, post_id)
    reaction = (
        db.query(CommunityReaction)
        .filter(
            CommunityReaction.post_id == post_id,
            CommunityReaction.user_id == current_user.id,
        )
        .first()
    )
    if reaction is not None:
        db.delete(reaction)
        db.commit()
    return _serialize_post(db, post, current_user.id)


@router.delete("/posts/{post_id}", status_code=204)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    post = (
        db.query(CommunityPost)
        .filter(
            CommunityPost.id == post_id,
            CommunityPost.user_id == current_user.id,
            CommunityPost.status == "active",
        )
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    post.status = "deleted"
    db.commit()
    logger.info("[community] post deleted post_id=%s user_id=%s", post.id, current_user.id)
    return Response(status_code=204)


@router.post("/posts/{post_id}/report", response_model=CommunityReportResponse)
async def report_post(
    post_id: int,
    data: CommunityReportCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    post = _active_post_or_404(db, post_id)
    if post.user_id == current_user.id:
        raise HTTPException(status_code=400, detail="请直接删除自己的分享")
    report = (
        db.query(CommunityReport)
        .filter(
            CommunityReport.post_id == post_id,
            CommunityReport.user_id == current_user.id,
        )
        .first()
    )
    if report is None:
        report = CommunityReport(
            post_id=post_id,
            user_id=current_user.id,
            reason=data.reason.strip(),
        )
        db.add(report)
        db.flush()
    count = db.query(CommunityReport).filter(CommunityReport.post_id == post_id).count()
    if count >= REPORT_REVIEW_THRESHOLD:
        post.status = "under_review"
    db.commit()
    logger.info(
        "[community] post reported post_id=%s reporter_id=%s report_count=%s",
        post_id,
        current_user.id,
        count,
    )
    return {"report_count": count, "status": post.status}
