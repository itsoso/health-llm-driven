"""血压追踪API"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.blood_pressure import BloodPressureRecord
from app.models.user import User
from app.api.deps import get_current_user_required
from app.schemas.blood_pressure import (
    BloodPressureRecordCreate,
    BloodPressureRecordUpdate,
    BloodPressureRecordResponse,
    BloodPressureSafetyGuidance,
    BloodPressureStats,
)
from app.utils.health_record import (
    verify_user_access,
    verify_record_ownership,
    get_record_or_404,
)
# D1(garmin-sync 治理 Wave 3): 血压分类抽到 utils 做单一真源, 供 api 与进程内 reader 共用。
# 保留同名 re-export, 既有 `from app.api.blood_pressure import classify_blood_pressure` 不破。
from app.utils.blood_pressure_classify import blood_pressure_display, classify_blood_pressure

router = APIRouter()


def _invalidate_twin(user_id: int) -> None:
    """Fail-soft twin-cache invalidation after a write (rank7: also drops pregen)."""
    try:
        from app.twin.cache import invalidate_twin
        invalidate_twin(user_id)
    except Exception:  # noqa: BLE001 — a Redis error must never fail the write
        pass


def _record_response(record: BloodPressureRecord) -> BloodPressureRecordResponse:
    """Apply the canonical display and safety payload on every record response."""
    response = BloodPressureRecordResponse.model_validate(record)
    display = blood_pressure_display(record.systolic, record.diastolic)
    response.category = display["category"]
    response.category_color = display["category_color"]
    safety_guidance = display["safety_guidance"]
    response.safety_guidance = (
        BloodPressureSafetyGuidance.model_validate(safety_guidance)
        if safety_guidance is not None
        else None
    )
    return response


@router.post("/records", response_model=BloodPressureRecordResponse)
def create_blood_pressure_record(
    record: BloodPressureRecordCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建血压记录（需要登录）"""
    from datetime import datetime

    record_data = record.model_dump()
    record_data["user_id"] = current_user.id

    # 处理字段名映射：record_time -> measured_at
    # 将 record_date + record_time 合并为 measured_at
    if "record_time" in record_data and record_data["record_time"]:
        record_date = record_data["record_date"]
        record_time = record_data.pop("record_time")
        # 合并日期和时间
        record_data["measured_at"] = datetime.combine(record_date, record_time)
    elif "record_date" in record_data:
        # 如果没有时间，使用当前时间
        record_data.pop("record_time", None)
        record_data["measured_at"] = datetime.combine(
            record_data["record_date"],
            datetime.now().time()
        )

    # 移除数据库中不存在的字段
    record_data.pop("measurement_position", None)
    record_data.pop("arm", None)

    db_record = BloodPressureRecord(**record_data)
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    _invalidate_twin(current_user.id)

    return _record_response(db_record)


@router.get("/records/user/{user_id}", response_model=List[BloodPressureRecordResponse])
def get_user_blood_pressure_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户血压记录（需要登录，只能访问自己的数据）"""
    # 使用通用工具进行权限验证
    verify_user_access(user_id, current_user)

    query = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == user_id)

    if start_date:
        query = query.filter(BloodPressureRecord.record_date >= start_date)
    if end_date:
        query = query.filter(BloodPressureRecord.record_date <= end_date)

    records = query.order_by(desc(BloodPressureRecord.record_date)).limit(limit).all()

    return [_record_response(record) for record in records]


@router.get("/records/me", response_model=List[BloodPressureRecordResponse])
def get_my_blood_pressure_records(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户血压记录（需要登录）"""
    query = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == current_user.id)

    if start_date:
        query = query.filter(BloodPressureRecord.record_date >= start_date)
    if end_date:
        query = query.filter(BloodPressureRecord.record_date <= end_date)

    records = query.order_by(desc(BloodPressureRecord.record_date)).limit(limit).all()

    return [_record_response(record) for record in records]


@router.get("/records/me/stats", response_model=BloodPressureStats)
def get_my_blood_pressure_stats(
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户血压统计（需要登录）"""
    start_date = date.today() - timedelta(days=days)

    records = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == current_user.id,
        BloodPressureRecord.record_date >= start_date
    ).all()

    if not records:
        return BloodPressureStats(total_records=0)

    systolics = [r.systolic for r in records]
    diastolics = [r.diastolic for r in records]
    pulses = [r.pulse for r in records if r.pulse]

    # 统计分类
    normal_count = 0
    elevated_count = 0
    high_count = 0

    for r in records:
        category = classify_blood_pressure(r.systolic, r.diastolic)
        if category == "正常":
            normal_count += 1
        elif category == "正常偏高":
            elevated_count += 1
        else:
            high_count += 1

    return BloodPressureStats(
        average_systolic=round(sum(systolics) / len(systolics), 1) if systolics else None,
        average_diastolic=round(sum(diastolics) / len(diastolics), 1) if diastolics else None,
        average_pulse=round(sum(pulses) / len(pulses), 1) if pulses else None,
        highest_systolic=max(systolics) if systolics else None,
        lowest_systolic=min(systolics) if systolics else None,
        highest_diastolic=max(diastolics) if diastolics else None,
        lowest_diastolic=min(diastolics) if diastolics else None,
        total_records=len(records),
        normal_count=normal_count,
        elevated_count=elevated_count,
        high_count=high_count
    )


@router.get("/records/user/{user_id}/latest", response_model=Optional[BloodPressureRecordResponse])
def get_latest_blood_pressure(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取最新血压记录（需要登录，只能访问自己的数据）"""
    # 使用通用工具进行权限验证
    verify_user_access(user_id, current_user)

    record = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user_id
    ).order_by(desc(BloodPressureRecord.record_date)).first()

    if record:
        return _record_response(record)
    return None


@router.get("/records/user/{user_id}/stats", response_model=BloodPressureStats)
def get_blood_pressure_stats(
    user_id: int,
    days: int = Query(default=30, le=365),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取血压统计（需要登录，只能访问自己的数据）"""
    # 使用通用工具进行权限验证
    verify_user_access(user_id, current_user)

    start_date = date.today() - timedelta(days=days)

    records = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user_id,
        BloodPressureRecord.record_date >= start_date
    ).all()

    if not records:
        return BloodPressureStats(total_records=0)

    systolics = [r.systolic for r in records]
    diastolics = [r.diastolic for r in records]
    pulses = [r.pulse for r in records if r.pulse]

    # 统计分类
    normal_count = 0
    elevated_count = 0
    high_count = 0

    for r in records:
        category = classify_blood_pressure(r.systolic, r.diastolic)
        if category == "正常":
            normal_count += 1
        elif category == "正常偏高":
            elevated_count += 1
        else:
            high_count += 1

    return BloodPressureStats(
        average_systolic=round(sum(systolics) / len(systolics), 1) if systolics else None,
        average_diastolic=round(sum(diastolics) / len(diastolics), 1) if diastolics else None,
        average_pulse=round(sum(pulses) / len(pulses), 1) if pulses else None,
        highest_systolic=max(systolics) if systolics else None,
        lowest_systolic=min(systolics) if systolics else None,
        highest_diastolic=max(diastolics) if diastolics else None,
        lowest_diastolic=min(diastolics) if diastolics else None,
        total_records=len(records),
        normal_count=normal_count,
        elevated_count=elevated_count,
        high_count=high_count
    )


@router.put("/records/{record_id}", response_model=BloodPressureRecordResponse)
def update_blood_pressure_record(
    record_id: int,
    update_data: BloodPressureRecordUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新血压记录（需要登录，只能修改自己的记录）"""
    # 使用通用工具获取记录并验证权限
    record = get_record_or_404(db, BloodPressureRecord, record_id)
    verify_record_ownership(record, current_user, "修改")

    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)

    db.commit()
    db.refresh(record)
    _invalidate_twin(current_user.id)

    return _record_response(record)


@router.delete("/records/{record_id}")
def delete_blood_pressure_record(
    record_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除血压记录（需要登录，只能删除自己的记录）"""
    # 使用通用工具获取记录并验证权限
    record = get_record_or_404(db, BloodPressureRecord, record_id)
    verify_record_ownership(record, current_user, "删除")

    db.delete(record)
    db.commit()
    _invalidate_twin(current_user.id)
    return {"message": "Record deleted successfully"}
