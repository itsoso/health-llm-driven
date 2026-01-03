"""Garmin数据分析API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.garmin_analysis import GarminAnalysisService

router = APIRouter()


@router.get("/user/{user_id}/sleep")
def analyze_sleep_quality(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """分析睡眠质量"""
    service = GarminAnalysisService()
    return service.analyze_sleep_quality(db, user_id, days)


@router.get("/user/{user_id}/heart-rate")
def analyze_heart_rate(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """分析心率数据"""
    service = GarminAnalysisService()
    return service.analyze_heart_rate(db, user_id, days)


@router.get("/user/{user_id}/body-battery")
def analyze_body_battery(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """分析身体电量"""
    service = GarminAnalysisService()
    return service.analyze_body_battery(db, user_id, days)


@router.get("/user/{user_id}/activity")
def analyze_activity(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """分析活动数据"""
    service = GarminAnalysisService()
    return service.analyze_activity(db, user_id, days)


@router.get("/user/{user_id}/comprehensive")
def get_comprehensive_analysis(
    user_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """获取Garmin数据综合分析"""
    service = GarminAnalysisService()
    return service.get_comprehensive_analysis(db, user_id, days)

