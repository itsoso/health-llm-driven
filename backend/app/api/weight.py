"""体重追踪API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.weight import WeightRecord
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.weight import (
    WeightRecordInput,
    WeightRecordCreate,
    WeightRecordUpdate,
    WeightRecordResponse,
    WeightStats,
)
from app.api.deps import get_current_user_required
from app.services.period_goal_service import PeriodGoalService

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


def _sync_weight_to_profile(db: Session, user_id: int, weight_record: WeightRecord):
    """同步体重数据到用户画像"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        # 如果用户画像不存在，创建一个
        profile = UserProfile(user_id=user_id)
        db.add(profile)

    # 更新体重
    if weight_record.weight:
        profile.current_weight_kg = weight_record.weight

    # 更新体脂率
    if weight_record.body_fat_percentage:
        profile.body_fat_percentage = weight_record.body_fat_percentage

    # 更新肌肉量
    if weight_record.muscle_mass_kg:
        profile.muscle_mass_kg = weight_record.muscle_mass_kg


def _auto_update_goal_metrics(db: Session, user_id: int, weight_record: WeightRecord):
    """自动更新阶段性目标中的身体指标"""
    try:
        service = PeriodGoalService(db)
        if weight_record.weight:
            service.update_metric_current_value(user_id, "weight", weight_record.weight)
        if weight_record.bmi:
            service.update_metric_current_value(user_id, "bmi", weight_record.bmi)
        if weight_record.body_fat_percentage:
            service.update_metric_current_value(user_id, "body_fat", weight_record.body_fat_percentage)
        if weight_record.muscle_mass_kg:
            service.update_metric_current_value(user_id, "muscle_mass", weight_record.muscle_mass_kg)
    except Exception:
        pass  # 不影响体重记录本身


@router.post("/records", response_model=WeightRecordResponse)
def create_weight_record(
    record: WeightRecordInput,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建体重记录（需要登录）"""
    user_id = current_user.id

    # 检查是否已有当天记录
    existing = db.query(WeightRecord).filter(
        WeightRecord.user_id == user_id,
        WeightRecord.record_date == record.record_date
    ).first()

    if existing:
        # 更新已有记录
        for key, value in record.model_dump(exclude={"user_id"}).items():
            if value is not None:
                # 处理字段名映射：muscle_mass -> muscle_mass_kg
                if key == "muscle_mass":
                    setattr(existing, "muscle_mass_kg", value)
                else:
                    setattr(existing, key, value)

        # 同步到用户画像
        _sync_weight_to_profile(db, user_id, existing)

        db.commit()
        db.refresh(existing)

        # 自动更新阶段性目标指标
        _auto_update_goal_metrics(db, user_id, existing)
        _invalidate_twin(user_id)

        return existing

    # 创建新记录
    record_data = record.model_dump()
    record_data["user_id"] = user_id

    # 处理字段名映射：muscle_mass -> muscle_mass_kg
    if "muscle_mass" in record_data:
        record_data["muscle_mass_kg"] = record_data.pop("muscle_mass")

    db_record = WeightRecord(**record_data)
    db.add(db_record)

    # 同步到用户画像
    _sync_weight_to_profile(db, user_id, db_record)

    db.commit()
    db.refresh(db_record)

    # 自动更新阶段性目标指标
    _auto_update_goal_metrics(db, user_id, db_record)
    _invalidate_twin(user_id)

    return db_record


@router.get("/records/user/{user_id}", response_model=List[WeightRecordResponse])
def get_user_weight_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户体重记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    query = db.query(WeightRecord).filter(WeightRecord.user_id == current_user.id)

    if start_date:
        query = query.filter(WeightRecord.record_date >= start_date)
    if end_date:
        query = query.filter(WeightRecord.record_date <= end_date)

    records = query.order_by(desc(WeightRecord.record_date)).limit(limit).all()
    return records


@router.get("/records/me", response_model=List[WeightRecordResponse])
def get_my_weight_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户体重记录（需要登录）"""
    query = db.query(WeightRecord).filter(WeightRecord.user_id == current_user.id)

    if start_date:
        query = query.filter(WeightRecord.record_date >= start_date)
    if end_date:
        query = query.filter(WeightRecord.record_date <= end_date)

    records = query.order_by(desc(WeightRecord.record_date)).limit(limit).all()
    return records


@router.get("/records/user/{user_id}/latest", response_model=Optional[WeightRecordResponse])
def get_latest_weight(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取最新体重记录（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    record = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id
    ).order_by(desc(WeightRecord.record_date)).first()
    return record


@router.get("/records/user/{user_id}/stats", response_model=WeightStats)
def get_weight_stats(
    user_id: int,
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取体重统计（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")

    start_date = date.today() - timedelta(days=days)

    records = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id,
        WeightRecord.record_date >= start_date
    ).order_by(desc(WeightRecord.record_date)).all()

    if not records:
        return WeightStats(total_records=0)

    weights = [r.weight for r in records if r.weight]

    # 计算30天变化
    weight_change = None
    if len(records) >= 2:
        latest = records[0].weight
        oldest = records[-1].weight
        weight_change = round(latest - oldest, 2)

    return WeightStats(
        current_weight=records[0].weight if records else None,
        highest_weight=max(weights) if weights else None,
        lowest_weight=min(weights) if weights else None,
        average_weight=round(sum(weights) / len(weights), 2) if weights else None,
        weight_change_30d=weight_change,
        total_records=len(records)
    )


@router.get("/records/me/stats", response_model=WeightStats)
def get_my_weight_stats(
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户体重统计（需要登录）"""
    start_date = date.today() - timedelta(days=days)

    records = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id,
        WeightRecord.record_date >= start_date
    ).order_by(desc(WeightRecord.record_date)).all()

    if not records:
        return WeightStats(total_records=0)

    weights = [r.weight for r in records if r.weight]

    # 30 天变化
    weight_change_30d = None
    if len(records) >= 2:
        weight_change_30d = round(records[0].weight - records[-1].weight, 2)

    # 7 天变化
    weight_change_7d = None
    seven_days_ago = date.today() - timedelta(days=7)
    recent_7d = [r for r in records if r.record_date >= seven_days_ago and r.weight]
    if len(recent_7d) >= 2:
        weight_change_7d = round(recent_7d[0].weight - recent_7d[-1].weight, 2)

    return WeightStats(
        current_weight=records[0].weight if records else None,
        highest_weight=max(weights) if weights else None,
        lowest_weight=min(weights) if weights else None,
        average_weight=round(sum(weights) / len(weights), 2) if weights else None,
        weight_change_7d=weight_change_7d,
        weight_change_30d=weight_change_30d,
        total_records=len(records)
    )


@router.put("/records/{record_id}", response_model=WeightRecordResponse)
def update_weight_record(
    record_id: int,
    update_data: WeightRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新体重记录（需要登录，只能更新自己的）"""
    record = db.query(WeightRecord).filter(WeightRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改其他用户的数据")

    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)

    # 如果更新的是最新记录，同步到用户画像
    latest_record = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id
    ).order_by(desc(WeightRecord.record_date)).first()

    if latest_record and latest_record.id == record_id:
        _sync_weight_to_profile(db, current_user.id, record)

    db.commit()
    db.refresh(record)
    return record


@router.delete("/records/{record_id}")
def delete_weight_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除体重记录（需要登录，只能删除自己的）"""
    record = db.query(WeightRecord).filter(WeightRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除其他用户的数据")

    # 检查是否删除的是最新记录
    latest_record = db.query(WeightRecord).filter(
        WeightRecord.user_id == current_user.id
    ).order_by(desc(WeightRecord.record_date)).first()

    is_latest = latest_record and latest_record.id == record_id

    db.delete(record)
    db.commit()

    # 如果删除的是最新记录，用次新记录更新画像
    if is_latest:
        new_latest = db.query(WeightRecord).filter(
            WeightRecord.user_id == current_user.id
        ).order_by(desc(WeightRecord.record_date)).first()

        if new_latest:
            _sync_weight_to_profile(db, current_user.id, new_latest)
            db.commit()

    return {"message": "Record deleted successfully"}
