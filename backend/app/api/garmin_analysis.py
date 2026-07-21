"""Garmin数据分析API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.services.garmin_analysis import GarminAnalysisService
from app.models.user import User
from app.api.deps import get_current_user_required, require_self_or_admin

router = APIRouter()


@router.get("/user/{user_id}/sleep")
def analyze_sleep_quality(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析睡眠质量"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = GarminAnalysisService()
    return service.analyze_sleep_quality(db, user_id, days)


@router.get("/user/{user_id}/heart-rate")
def analyze_heart_rate(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析心率数据"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = GarminAnalysisService()
    return service.analyze_heart_rate(db, user_id, days)


@router.get("/user/{user_id}/body-battery")
def analyze_body_battery(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析身体电量"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = GarminAnalysisService()
    return service.analyze_body_battery(db, user_id, days)


@router.get("/user/{user_id}/activity")
def analyze_activity(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析活动数据"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = GarminAnalysisService()
    return service.analyze_activity(db, user_id, days)


@router.get("/user/{user_id}/comprehensive")
def get_comprehensive_analysis(
    user_id: int,
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取Garmin数据综合分析"""
    require_self_or_admin(current_user, user_id, resource="Garmin 数据")
    service = GarminAnalysisService()
    return service.get_comprehensive_analysis(db, user_id, days)


# ========== /me 端点（使用当前登录用户）==========

@router.get("/me/comprehensive")
def get_my_comprehensive_analysis(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的Garmin数据综合分析（需要登录）"""
    service = GarminAnalysisService()
    return service.get_comprehensive_analysis(db, current_user.id, days)


@router.get("/me/sleep")
def analyze_my_sleep_quality(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户睡眠质量（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_sleep_quality(db, current_user.id, days)


@router.get("/me/heart-rate")
def analyze_my_heart_rate(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户心率数据（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_heart_rate(db, current_user.id, days)


@router.get("/me/body-battery")
def analyze_my_body_battery(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户身体电量（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_body_battery(db, current_user.id, days)


@router.get("/me/activity")
def analyze_my_activity(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户活动数据（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_activity(db, current_user.id, days)


@router.get("/me/hrv")
def analyze_my_hrv(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户HRV心率变异性数据（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_hrv(db, current_user.id, days)


@router.get("/me/spo2")
def analyze_my_spo2(
    days: int = 7,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """分析当前用户血氧SpO2数据（需要登录）"""
    service = GarminAnalysisService()
    return service.analyze_spo2(db, current_user.id, days)
