"""基础健康数据API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.schemas.basic_health import BasicHealthDataCreate, BasicHealthDataResponse
from app.models.basic_health import BasicHealthData
from app.models.user import User
from app.api.deps import get_current_user_required

router = APIRouter()


@router.post("/", response_model=BasicHealthDataResponse)
def create_basic_health_data(
    data: BasicHealthDataCreate,
    db: Session = Depends(get_db)
):
    """创建基础健康数据"""
    # 如果未提供BMI，自动计算
    if data.weight and data.height and not data.bmi:
        data.bmi = data.weight / ((data.height / 100) ** 2)
    
    db_data = BasicHealthData(**data.model_dump())
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data


# ========== /me 端点必须在 /user/{user_id} 之前定义，否则会被错误匹配 ==========

@router.get("/me/latest", response_model=BasicHealthDataResponse)
def get_my_latest_basic_health_data(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户最新的基础健康数据（需要登录）"""
    data = db.query(BasicHealthData).filter(
        BasicHealthData.user_id == current_user.id
    ).order_by(BasicHealthData.record_date.desc()).first()
    
    if not data:
        raise HTTPException(status_code=404, detail="未找到基础健康数据")
    return data


@router.get("/me", response_model=List[BasicHealthDataResponse])
def get_my_basic_health_data(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的基础健康数据（需要登录）"""
    data_list = db.query(BasicHealthData).filter(
        BasicHealthData.user_id == current_user.id
    ).order_by(BasicHealthData.record_date.desc()).offset(skip).limit(limit).all()
    return data_list


# ========== /user/{user_id} 端点 ==========

@router.get("/user/{user_id}", response_model=List[BasicHealthDataResponse])
def get_user_basic_health_data(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取用户的基础健康数据"""
    data_list = db.query(BasicHealthData).filter(
        BasicHealthData.user_id == user_id
    ).order_by(BasicHealthData.record_date.desc()).offset(skip).limit(limit).all()
    return data_list


@router.get("/user/{user_id}/latest", response_model=BasicHealthDataResponse)
def get_latest_basic_health_data(
    user_id: int,
    db: Session = Depends(get_db)
):
    """获取用户最新的基础健康数据"""
    data = db.query(BasicHealthData).filter(
        BasicHealthData.user_id == user_id
    ).order_by(BasicHealthData.record_date.desc()).first()
    
    if not data:
        raise HTTPException(status_code=404, detail="未找到基础健康数据")
    return data
