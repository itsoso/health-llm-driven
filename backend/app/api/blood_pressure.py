"""血压追踪API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import date, timedelta

from app.database import get_db
from app.models.blood_pressure import BloodPressureRecord
from app.schemas.blood_pressure import (
    BloodPressureRecordCreate,
    BloodPressureRecordUpdate,
    BloodPressureRecordResponse,
    BloodPressureStats,
)

router = APIRouter()


def classify_blood_pressure(systolic: int, diastolic: int) -> str:
    """血压分类"""
    if systolic < 120 and diastolic < 80:
        return "正常"
    elif systolic < 130 and diastolic < 80:
        return "正常偏高"
    elif systolic < 140 or diastolic < 90:
        return "高血压前期"
    elif systolic < 160 or diastolic < 100:
        return "高血压1级"
    elif systolic < 180 or diastolic < 110:
        return "高血压2级"
    else:
        return "高血压3级"


@router.post("/records", response_model=BloodPressureRecordResponse)
def create_blood_pressure_record(record: BloodPressureRecordCreate, db: Session = Depends(get_db)):
    """创建血压记录"""
    db_record = BloodPressureRecord(**record.model_dump())
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    # 添加血压分类
    response = BloodPressureRecordResponse.model_validate(db_record)
    response.category = classify_blood_pressure(db_record.systolic, db_record.diastolic)
    return response


@router.get("/records/user/{user_id}", response_model=List[BloodPressureRecordResponse])
def get_user_blood_pressure_records(
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=30, le=365),
    db: Session = Depends(get_db)
):
    """获取用户血压记录"""
    query = db.query(BloodPressureRecord).filter(BloodPressureRecord.user_id == user_id)
    
    if start_date:
        query = query.filter(BloodPressureRecord.record_date >= start_date)
    if end_date:
        query = query.filter(BloodPressureRecord.record_date <= end_date)
    
    records = query.order_by(desc(BloodPressureRecord.record_date)).limit(limit).all()
    
    # 添加血压分类
    results = []
    for record in records:
        response = BloodPressureRecordResponse.model_validate(record)
        response.category = classify_blood_pressure(record.systolic, record.diastolic)
        results.append(response)
    
    return results


@router.get("/records/user/{user_id}/latest", response_model=Optional[BloodPressureRecordResponse])
def get_latest_blood_pressure(user_id: int, db: Session = Depends(get_db)):
    """获取最新血压记录"""
    record = db.query(BloodPressureRecord).filter(
        BloodPressureRecord.user_id == user_id
    ).order_by(desc(BloodPressureRecord.record_date)).first()
    
    if record:
        response = BloodPressureRecordResponse.model_validate(record)
        response.category = classify_blood_pressure(record.systolic, record.diastolic)
        return response
    return None


@router.get("/records/user/{user_id}/stats", response_model=BloodPressureStats)
def get_blood_pressure_stats(
    user_id: int,
    days: int = Query(default=30, le=365),
    db: Session = Depends(get_db)
):
    """获取血压统计"""
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
        elif category in ["正常偏高", "高血压前期"]:
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
    db: Session = Depends(get_db)
):
    """更新血压记录"""
    record = db.query(BloodPressureRecord).filter(BloodPressureRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    for key, value in update_data.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    
    db.commit()
    db.refresh(record)
    
    response = BloodPressureRecordResponse.model_validate(record)
    response.category = classify_blood_pressure(record.systolic, record.diastolic)
    return response


@router.delete("/records/{record_id}")
def delete_blood_pressure_record(record_id: int, db: Session = Depends(get_db)):
    """删除血压记录"""
    record = db.query(BloodPressureRecord).filter(BloodPressureRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    db.delete(record)
    db.commit()
    return {"message": "Record deleted successfully"}

