"""当前病症追踪 API"""
from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.models.illness import IllnessEpisode, IllnessUpdate
from app.api.deps import get_current_user_required
from app.schemas.illness import (
    IllnessEpisodeCreate, IllnessEpisodePatch, IllnessEpisodeResponse,
    IllnessEpisodeListResponse, IllnessUpdateCreate, IllnessUpdateResponse,
)

router = APIRouter(prefix="/illness", tags=["illness"])


@router.post("/episodes", response_model=IllnessEpisodeResponse, summary="新建病症发作")
def create_episode(
    data: IllnessEpisodeCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    episode = IllnessEpisode(
        user_id=current_user.id,
        name=data.name,
        start_date=data.start_date,
        severity=data.severity,
        status=data.status,
        notes=data.notes,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass
    return episode


@router.get("/episodes", response_model=List[IllnessEpisodeListResponse], summary="获取病症列表")
def list_episodes(
    status: Optional[str] = None,   # 逗号分隔，如 "active,improving"；不传则返回所有未痊愈
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    q = db.query(IllnessEpisode).filter(IllnessEpisode.user_id == current_user.id)
    if status:
        statuses = [s.strip() for s in status.split(",")]
        q = q.filter(IllnessEpisode.status.in_(statuses))
    else:
        q = q.filter(IllnessEpisode.status != "resolved")
    return q.order_by(IllnessEpisode.start_date.desc()).all()


@router.get("/episodes/all", response_model=List[IllnessEpisodeListResponse], summary="获取所有病症（含已痊愈）")
def list_all_episodes(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    return (
        db.query(IllnessEpisode)
        .filter(IllnessEpisode.user_id == current_user.id)
        .order_by(IllnessEpisode.start_date.desc())
        .all()
    )


@router.get("/episodes/{episode_id}", response_model=IllnessEpisodeResponse, summary="获取病症详情")
def get_episode(
    episode_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    episode = (
        db.query(IllnessEpisode)
        .options(joinedload(IllnessEpisode.updates))
        .filter(IllnessEpisode.id == episode_id, IllnessEpisode.user_id == current_user.id)
        .first()
    )
    if not episode:
        raise HTTPException(status_code=404, detail="病症记录不存在")
    return episode


@router.patch("/episodes/{episode_id}", response_model=IllnessEpisodeResponse, summary="更新病症状态（PATCH）")
@router.put("/episodes/{episode_id}", response_model=IllnessEpisodeResponse, summary="更新病症状态（PUT）")
def patch_episode(
    episode_id: int,
    data: IllnessEpisodePatch,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    episode = db.query(IllnessEpisode).filter(
        IllnessEpisode.id == episode_id, IllnessEpisode.user_id == current_user.id
    ).first()
    if not episode:
        raise HTTPException(status_code=404, detail="病症记录不存在")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(episode, field, value)

    # 标记痊愈时自动设置结束日期
    if data.status == "resolved" and not episode.end_date:
        episode.end_date = date.today()

    db.commit()
    db.refresh(episode)
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass
    return episode


@router.delete("/episodes/{episode_id}", summary="删除病症记录")
def delete_episode(
    episode_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    episode = db.query(IllnessEpisode).filter(
        IllnessEpisode.id == episode_id, IllnessEpisode.user_id == current_user.id
    ).first()
    if not episode:
        raise HTTPException(status_code=404, detail="病症记录不存在")
    db.delete(episode)
    db.commit()
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass
    return {"ok": True}


@router.post("/episodes/{episode_id}/updates", response_model=IllnessUpdateResponse, summary="添加进展更新")
def add_update(
    episode_id: int,
    data: IllnessUpdateCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    episode = db.query(IllnessEpisode).filter(
        IllnessEpisode.id == episode_id, IllnessEpisode.user_id == current_user.id
    ).first()
    if not episode:
        raise HTTPException(status_code=404, detail="病症记录不存在")

    update = IllnessUpdate(
        episode_id=episode_id,
        user_id=current_user.id,
        update_date=data.update_date,
        severity=data.severity,
        status=data.status,
        notes=data.notes,
    )
    db.add(update)

    # 同步更新 episode 的当前状态
    if data.severity is not None:
        episode.severity = data.severity
    if data.status:
        episode.status = data.status
        if data.status == "resolved" and not episode.end_date:
            episode.end_date = date.today()

    db.commit()
    db.refresh(update)
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass
    return update


@router.delete("/updates/{update_id}", summary="删除进展更新")
def delete_update(
    update_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    update = db.query(IllnessUpdate).filter(
        IllnessUpdate.id == update_id, IllnessUpdate.user_id == current_user.id
    ).first()
    if not update:
        raise HTTPException(status_code=404, detail="更新记录不存在")
    db.delete(update)
    db.commit()
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(current_user.id)
    except Exception:
        pass
    return {"ok": True}
