"""主API路由"""
from fastapi import APIRouter
from app.api import (
    auth,
    users,
    basic_health,
    medical_exams,
    diseases,
    daily_health,
    health_checkin,
    goals,
    data_collection,
    health_analysis,
    garmin_analysis,
    garmin_connect,
    daily_recommendation,
    supplements,
    habits,
    weight,
    blood_pressure,
    diet,
    water,
)

api_router = APIRouter()

# 认证路由（放在最前面）
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(basic_health.router, prefix="/basic-health", tags=["basic-health"])
api_router.include_router(medical_exams.router, prefix="/medical-exams", tags=["medical-exams"])
api_router.include_router(diseases.router, prefix="/diseases", tags=["diseases"])
api_router.include_router(daily_health.router, prefix="/daily-health", tags=["daily-health"])
api_router.include_router(health_checkin.router, prefix="/checkin", tags=["checkin"])
api_router.include_router(goals.router, prefix="/goals", tags=["goals"])
api_router.include_router(data_collection.router, prefix="/data-collection", tags=["data-collection"])
api_router.include_router(health_analysis.router, prefix="/analysis", tags=["analysis"])
api_router.include_router(garmin_analysis.router, prefix="/garmin-analysis", tags=["garmin-analysis"])
api_router.include_router(garmin_connect.router, prefix="/garmin-connect", tags=["garmin-connect"])
api_router.include_router(daily_recommendation.router, prefix="/daily-recommendation", tags=["daily-recommendation"])
api_router.include_router(supplements.router, prefix="/supplements", tags=["supplements"])
api_router.include_router(habits.router, prefix="/habits", tags=["habits"])
api_router.include_router(weight.router, prefix="/weight", tags=["weight"])
api_router.include_router(blood_pressure.router, prefix="/blood-pressure", tags=["blood-pressure"])
api_router.include_router(diet.router, prefix="/diet", tags=["diet"])
api_router.include_router(water.router, prefix="/water", tags=["water"])

