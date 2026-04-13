"""
运动动作指导笔记 API。

- GET    /exercise-coaching/me                   我的所有笔记
- GET    /exercise-coaching/me/{exercise_type}    某运动类型的最新笔记
- POST   /exercise-coaching                       创建笔记
- DELETE /exercise-coaching/{id}                   删除
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.exercise_coaching import ExerciseCoachingNote
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exercise-coaching", tags=["exercise-coaching"])


class CoachingNoteCreate(BaseModel):
    exercise_type: str = Field(..., max_length=50)
    title: Optional[str] = None
    good_points: Optional[str] = None
    issues: Optional[str] = None
    checklist: Optional[str] = None
    source_type: str = "ai_video"
    video_url: Optional[str] = None


@router.get("/me")
def get_my_notes(
    exercise_type: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """获取我的运动指导笔记。"""
    q = db.query(ExerciseCoachingNote).filter(ExerciseCoachingNote.user_id == current_user.id)
    if exercise_type:
        q = q.filter(ExerciseCoachingNote.exercise_type == exercise_type)
    if active_only:
        q = q.filter(ExerciseCoachingNote.is_active == True)  # noqa
    notes = q.order_by(desc(ExerciseCoachingNote.created_at)).limit(20).all()
    return [_note_to_dict(n) for n in notes]


@router.get("/me/{exercise_type}")
def get_latest_note(
    exercise_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """获取某运动类型的最新指导笔记。"""
    note = (
        db.query(ExerciseCoachingNote)
        .filter(
            ExerciseCoachingNote.user_id == current_user.id,
            ExerciseCoachingNote.exercise_type == exercise_type,
            ExerciseCoachingNote.is_active == True,  # noqa
        )
        .order_by(desc(ExerciseCoachingNote.created_at))
        .first()
    )
    if not note:
        return None
    return _note_to_dict(note)


@router.post("")
def create_note(
    body: CoachingNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    """创建运动指导笔记。自动归档同类型旧笔记。"""
    # 归档旧的同类型笔记
    old = (
        db.query(ExerciseCoachingNote)
        .filter(
            ExerciseCoachingNote.user_id == current_user.id,
            ExerciseCoachingNote.exercise_type == body.exercise_type,
            ExerciseCoachingNote.is_active == True,  # noqa
        )
        .all()
    )
    for o in old:
        o.is_active = False

    note = ExerciseCoachingNote(
        user_id=current_user.id,
        exercise_type=body.exercise_type,
        title=body.title or f"{body.exercise_type}动作指导",
        good_points=body.good_points,
        issues=body.issues,
        checklist=body.checklist,
        source_type=body.source_type,
        video_url=body.video_url,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    logger.info(f"[coaching] 用户 {current_user.id} 创建 {body.exercise_type} 指导笔记 #{note.id}")
    return _note_to_dict(note)


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
):
    note = db.query(ExerciseCoachingNote).filter(
        ExerciseCoachingNote.id == note_id,
        ExerciseCoachingNote.user_id == current_user.id,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    db.delete(note)
    db.commit()
    return {"message": "已删除", "id": note_id}


def _note_to_dict(note: ExerciseCoachingNote) -> dict:
    return {
        "id": note.id,
        "exercise_type": note.exercise_type,
        "title": note.title,
        "good_points": note.good_points,
        "issues": note.issues,
        "checklist": note.checklist,
        "source_type": note.source_type,
        "video_url": note.video_url,
        "is_active": note.is_active,
        "created_at": note.created_at.isoformat() if note.created_at else None,
    }
