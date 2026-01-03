"""日常健康记录API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date
from app.database import get_db
from app.schemas.daily_health import (
    GarminDataCreate,
    GarminDataResponse,
    ExerciseRecordCreate,
    DietRecordCreate,
    WaterIntakeCreate,
    SupplementIntakeCreate,
    OutdoorActivityCreate
)
from app.models.daily_health import (
    GarminData,
    ExerciseRecord,
    DietRecord,
    WaterIntake,
    SupplementIntake,
    OutdoorActivity
)

router = APIRouter()


# Garmin数据
@router.post("/garmin", response_model=GarminDataResponse)
def create_garmin_data(
    data: GarminDataCreate,
    db: Session = Depends(get_db)
):
    """创建Garmin数据"""
    # 检查是否已存在
    existing = db.query(GarminData).filter(
        GarminData.user_id == data.user_id,
        GarminData.record_date == data.record_date
    ).first()
    
    if existing:
        for key, value in data.model_dump(exclude={"user_id", "record_date"}).items():
            if value is not None:
                setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    
    db_data = GarminData(**data.model_dump())
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data


@router.get("/garmin/user/{user_id}", response_model=List[GarminDataResponse])
def get_user_garmin_data(
    user_id: int,
    start_date: date = None,
    end_date: date = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取用户的Garmin数据"""
    query = db.query(GarminData).filter(GarminData.user_id == user_id)
    
    if start_date:
        query = query.filter(GarminData.record_date >= start_date)
    if end_date:
        query = query.filter(GarminData.record_date <= end_date)
    
    data_list = query.order_by(GarminData.record_date.desc()).offset(skip).limit(limit).all()
    return data_list


# 锻炼记录
@router.post("/exercise", response_model=dict)
def create_exercise_record(
    exercise: ExerciseRecordCreate,
    db: Session = Depends(get_db)
):
    """创建锻炼记录"""
    db_exercise = ExerciseRecord(**exercise.model_dump())
    db.add(db_exercise)
    db.commit()
    db.refresh(db_exercise)
    return {"message": "创建成功", "id": db_exercise.id}


# 饮食记录
@router.post("/diet", response_model=dict)
def create_diet_record(
    diet: DietRecordCreate,
    db: Session = Depends(get_db)
):
    """创建饮食记录"""
    db_diet = DietRecord(**diet.model_dump())
    db.add(db_diet)
    db.commit()
    db.refresh(db_diet)
    return {"message": "创建成功", "id": db_diet.id}


# 饮水记录
@router.post("/water", response_model=dict)
def create_water_intake(
    water: WaterIntakeCreate,
    db: Session = Depends(get_db)
):
    """创建饮水记录"""
    db_water = WaterIntake(**water.model_dump())
    db.add(db_water)
    db.commit()
    db.refresh(db_water)
    return {"message": "创建成功", "id": db_water.id}


# 补剂记录
@router.post("/supplement", response_model=dict)
def create_supplement_intake(
    supplement: SupplementIntakeCreate,
    db: Session = Depends(get_db)
):
    """创建补剂记录"""
    db_supplement = SupplementIntake(**supplement.model_dump())
    db.add(db_supplement)
    db.commit()
    db.refresh(db_supplement)
    return {"message": "创建成功", "id": db_supplement.id}


# 户外活动记录
@router.post("/outdoor", response_model=dict)
def create_outdoor_activity(
    activity: OutdoorActivityCreate,
    db: Session = Depends(get_db)
):
    """创建户外活动记录"""
    db_activity = OutdoorActivity(**activity.model_dump())
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    return {"message": "创建成功", "id": db_activity.id}

