"""
行程记录 API
"""
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.user import User
from app.models.trip import Trip, TripItem
from app.api.deps import get_current_user_required
from app.schemas.trip import (
    TripCreate, TripUpdate, TripResponse, TripListResponse,
    TripItemCreate, TripItemUpdate, TripItemResponse,
)

router = APIRouter(prefix="/trip", tags=["行程记录"])


# =====================================================
# 行程 CRUD
# =====================================================

@router.post("/trips", response_model=TripResponse)
async def create_trip(
    data: TripCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """创建行程（可携带明细）"""
    if data.end_date < data.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

    trip = Trip(
        user_id=current_user.id,
        trip_name=data.trip_name,
        start_date=data.start_date,
        end_date=data.end_date,
        destination=data.destination,
        notes=data.notes,
    )
    db.add(trip)
    db.flush()  # 获取 trip.id

    if data.items:
        for item_data in data.items:
            item = TripItem(
                trip_id=trip.id,
                user_id=current_user.id,
                **item_data.model_dump(),
            )
            db.add(item)

    db.commit()
    db.refresh(trip)
    return trip


@router.get("/trips", response_model=List[TripListResponse])
async def list_trips(
    days: int = Query(365, ge=1, le=3650, description="查询最近N天内的行程"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取行程列表"""
    since = date.today() - timedelta(days=days)
    trips = db.query(Trip).filter(
        Trip.user_id == current_user.id,
        Trip.end_date >= since,
    ).order_by(Trip.start_date.desc()).all()
    return trips


@router.get("/trips/{trip_id}", response_model=TripResponse)
async def get_trip(
    trip_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取行程详情（含所有明细）"""
    trip = db.query(Trip).options(
        joinedload(Trip.items)
    ).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id,
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")
    return trip


@router.put("/trips/{trip_id}", response_model=TripResponse)
async def update_trip(
    trip_id: int,
    data: TripUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新行程基本信息"""
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id,
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(trip, key, value)

    # 校验日期
    if trip.end_date < trip.start_date:
        raise HTTPException(status_code=400, detail="结束日期不能早于开始日期")

    db.commit()
    db.refresh(trip)
    return trip


@router.delete("/trips/{trip_id}")
async def delete_trip(
    trip_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除行程（级联删除明细）"""
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id,
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")

    db.delete(trip)
    db.commit()
    return {"ok": True}


# =====================================================
# 行程明细 CRUD
# =====================================================

@router.post("/trips/{trip_id}/items", response_model=TripItemResponse)
async def add_trip_item(
    trip_id: int,
    data: TripItemCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """添加行程明细"""
    trip = db.query(Trip).filter(
        Trip.id == trip_id,
        Trip.user_id == current_user.id,
    ).first()
    if not trip:
        raise HTTPException(status_code=404, detail="行程不存在")

    item = TripItem(
        trip_id=trip_id,
        user_id=current_user.id,
        **data.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=TripItemResponse)
async def update_trip_item(
    item_id: int,
    data: TripItemUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """更新行程明细"""
    item = db.query(TripItem).filter(
        TripItem.id == item_id,
        TripItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="行程明细不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)

    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
async def delete_trip_item(
    item_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """删除行程明细"""
    item = db.query(TripItem).filter(
        TripItem.id == item_id,
        TripItem.user_id == current_user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="行程明细不存在")

    db.delete(item)
    db.commit()
    return {"ok": True}
