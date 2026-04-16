"""单词本 API"""
from datetime import UTC, date, datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import get_current_user_required
from app.models.user import User
from app.models.vocabulary import VocabularyWord
from app.schemas.vocabulary import (
    VocabularyWordResponse,
    VocabularyListResponse,
    VocabularyReviewRequest,
)

router = APIRouter(prefix="/vocabulary", tags=["vocabulary"])


@router.get("/words", response_model=VocabularyListResponse, summary="单词本列表")
async def list_words(
    mastered: Optional[bool] = Query(None, description="筛选已掌握/未掌握"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    query = db.query(VocabularyWord).filter(VocabularyWord.user_id == current_user.id)
    if mastered is not None:
        query = query.filter(VocabularyWord.is_mastered == mastered)
    total = query.count()
    words = (
        query.order_by(VocabularyWord.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return VocabularyListResponse(total=total, words=words)


@router.get("/words/{word_id}", response_model=VocabularyWordResponse, summary="单词详情")
async def get_word(
    word_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    word = db.query(VocabularyWord).filter(
        VocabularyWord.id == word_id,
        VocabularyWord.user_id == current_user.id,
    ).first()
    if not word:
        raise HTTPException(status_code=404, detail="单词不存在")
    return word


@router.get("/review", response_model=VocabularyListResponse, summary="今日待复习单词")
async def get_review_words(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    today = date.today()
    words = (
        db.query(VocabularyWord)
        .filter(
            VocabularyWord.user_id == current_user.id,
            VocabularyWord.is_mastered == False,
            (VocabularyWord.next_review_date <= today) | (VocabularyWord.next_review_date == None),
        )
        .order_by(VocabularyWord.next_review_date.asc().nullsfirst())
        .limit(limit)
        .all()
    )
    return VocabularyListResponse(total=len(words), words=words)


@router.post("/review", summary="提交复习结果")
async def submit_review(
    req: VocabularyReviewRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    word = db.query(VocabularyWord).filter(
        VocabularyWord.id == req.word_id,
        VocabularyWord.user_id == current_user.id,
    ).first()
    if not word:
        raise HTTPException(status_code=404, detail="单词不存在")

    word.review_count = (word.review_count or 0) + 1
    word.last_reviewed_at = datetime.now(UTC)

    if req.is_correct:
        word.correct_count = (word.correct_count or 0) + 1
        word.mastery_level = min(5, (word.mastery_level or 0) + 1)
        intervals = {1: 1, 2: 2, 3: 4, 4: 7, 5: 15}
        days = intervals.get(word.mastery_level, 1)
        word.next_review_date = date.today() + timedelta(days=days)
        if word.mastery_level >= 5:
            word.is_mastered = True
    else:
        word.mastery_level = max(0, (word.mastery_level or 0) - 1)
        word.next_review_date = date.today()

    db.commit()
    return {
        "ok": True,
        "mastery_level": word.mastery_level,
        "next_review_date": str(word.next_review_date),
    }


@router.delete("/words/{word_id}", summary="删除单词")
async def delete_word(
    word_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    word = db.query(VocabularyWord).filter(
        VocabularyWord.id == word_id,
        VocabularyWord.user_id == current_user.id,
    ).first()
    if not word:
        raise HTTPException(status_code=404, detail="单词不存在")
    db.delete(word)
    db.commit()
    return {"ok": True}
