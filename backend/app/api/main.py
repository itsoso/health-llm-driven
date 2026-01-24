"""主API路由"""
from fastapi import APIRouter
from app.api import (
    auth,
    admin,
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
    # habits,  # 已废弃，模块已移除
    weight,
    blood_pressure,
    diet,
    water,
    heart_rate,
    workout,
    wechat,
    devices,  # 多设备管理
    user_merge,  # 用户合并
    upload,  # 文件上传
    invitation,  # 邀请码系统
    monitoring,  # 系统监控
    # executor-v2: 新增模块
    user_profile,  # 用户画像
    checkin,  # 打卡系统2.0
    knowledge,  # 知识库RAG系统
    environment,  # 环境数据（天气、空气质量）
    disease_tracking,  # 增强版疾病追踪
    ai_scheduler,  # AI 日程编排引擎
    digital_twin,  # 数字孪生
    notification,  # 推送通知
    review,  # 每日复盘
    diet_recommendation,  # 智能饮食推荐
    performance,  # 性能监控
)

api_router = APIRouter()

# 认证路由（放在最前面）
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(wechat.router, prefix="/wechat", tags=["wechat"])
api_router.include_router(user_merge.router, prefix="/user-merge", tags=["user-merge"])
api_router.include_router(invitation.router, tags=["invitation"])  # 邀请码系统

# 管理员路由
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(monitoring.router, prefix="/monitoring", tags=["monitoring"])  # 系统监控

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
# api_router.include_router(habits.router, prefix="/habits", tags=["habits"])  # 已废弃，模块已移除
api_router.include_router(weight.router, prefix="/weight", tags=["weight"])
api_router.include_router(blood_pressure.router, prefix="/blood-pressure", tags=["blood-pressure"])
api_router.include_router(diet.router, prefix="/diet", tags=["diet"])
api_router.include_router(water.router, prefix="/water", tags=["water"])
api_router.include_router(heart_rate.router, prefix="/heart-rate", tags=["heart-rate"])
api_router.include_router(workout.router, prefix="/workout", tags=["workout"])
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])  # 多设备管理
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])  # 文件上传

# executor-v2: 新增路由
api_router.include_router(user_profile.router, tags=["user-profile"])  # 用户画像
api_router.include_router(checkin.router, tags=["checkin-v2"])  # 打卡系统2.0
api_router.include_router(knowledge.router, tags=["knowledge-base"])  # 知识库RAG系统
api_router.include_router(environment.router, tags=["environment"])  # 环境数据
api_router.include_router(disease_tracking.router, tags=["disease-tracking"])  # 疾病追踪
api_router.include_router(ai_scheduler.router, tags=["ai-scheduler"])  # AI 日程编排引擎
api_router.include_router(digital_twin.router, prefix="/digital-twin", tags=["digital-twin"])  # 数字孪生
api_router.include_router(notification.router, tags=["notification"])  # 推送通知
api_router.include_router(review.router, tags=["review"])  # 每日复盘
api_router.include_router(diet_recommendation.router)  # 智能饮食推荐（prefix 已在 router 中定义）
api_router.include_router(performance.router, prefix="/performance", tags=["performance"])  # 性能监控