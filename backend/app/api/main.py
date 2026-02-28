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
    news,  # 资讯系统
    user_api_key,  # 用户 API Key 管理 & 外部系统接口
    chat,  # OpenClaw AI 对话
    ai_insights,  # AI 健康洞察（每日复盘+实时建议）
    mood,  # 情绪追踪
    health_report,  # 健康报告
    body_composition,  # 身体成分分析
    health_score,  # 健康评分
    medication,  # 用药管理
    womens_health,  # 女性健康
    vision,  # 视觉分析（颜值测试、图片识别）
    trip,  # 行程记录
    siri,  # Siri 快捷指令
    illness,  # 当前病症追踪
    kids_pet,  # 儿童狗狗空间
    excretion,  # 排泄记录
    sleep_record,  # 睡眠记录
    activity_status,  # 活动状态
    friendship,  # 好友关系
    pk_challenge,  # PK挑战
    daily_points,  # 每日健康积分
    vocabulary,  # 单词本
    kids_plan,  # Kids每日计划
    direct_message,  # 私信聊天
    security_life,  # 资产防御与布局
    smart_plan,  # AI 智能计划
    health_event,  # 健康事件流
    withings,  # Withings 设备集成
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
api_router.include_router(performance.router)  # 性能监控（prefix 已在 router 中定义）
api_router.include_router(news.router)  # 资讯系统（prefix 已在 router 中定义）
api_router.include_router(user_api_key.router, tags=["user-api-key"])  # 用户 API Key & 外部接口
api_router.include_router(chat.router)  # OpenClaw AI 对话
api_router.include_router(ai_insights.router, prefix="/ai-insights", tags=["ai-insights"])  # AI 健康洞察
api_router.include_router(mood.router)  # 情绪追踪
api_router.include_router(health_report.router)  # 健康报告
api_router.include_router(body_composition.router)  # 身体成分分析
api_router.include_router(health_score.router)  # 健康评分
api_router.include_router(medication.router)  # 用药管理
api_router.include_router(womens_health.router)  # 女性健康
api_router.include_router(vision.router)  # 视觉分析（颜值测试、图片识别）
api_router.include_router(trip.router)  # 行程记录
api_router.include_router(siri.router)  # Siri 快捷指令
api_router.include_router(illness.router)  # 当前病症追踪
api_router.include_router(kids_pet.router)  # 儿童狗狗空间
api_router.include_router(excretion.router)  # 排泄记录
api_router.include_router(sleep_record.router)  # 睡眠记录
api_router.include_router(activity_status.router)  # 活动状态
api_router.include_router(friendship.router)  # 好友关系
api_router.include_router(pk_challenge.router)  # PK挑战
api_router.include_router(daily_points.router)  # 每日健康积分
api_router.include_router(vocabulary.router)  # 单词本
api_router.include_router(kids_plan.router)  # Kids每日计划
api_router.include_router(direct_message.router)  # 私信聊天

# 资产防御与布局
api_router.include_router(security_life.router, prefix="/security-life", tags=["security-life"])

# AI 智能计划
api_router.include_router(smart_plan.router)  # prefix 已在 router 中定义

# 健康事件流
api_router.include_router(health_event.router)  # prefix 已在 router 中定义

# Withings 设备集成
api_router.include_router(withings.router)  # prefix 已在 router 中定义