"""
用户画像 API - executor.life
"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile, HealthGoal
from app.schemas.user_profile import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    HealthGoalCreate, HealthGoalUpdate, HealthGoalResponse,
    PrivacySettings, DetectedLocation
)
from app.api.auth import get_current_user_required
from datetime import date

router = APIRouter(prefix="/profile", tags=["用户画像"])


# =====================================================
# 用户画像 API
# =====================================================

@router.get("/me", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的画像"""
    import json
    
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    
    if not profile:
        # 自动创建空的用户画像
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    
    # 处理 JSON 字段（数据库中可能是字符串）
    def parse_json_field(field_value, default):
        if field_value is None:
            return default
        if isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except:
                return default
        return field_value
    
    # 构建响应数据，处理所有可能为 None 的字段
    response_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "gender": profile.gender,
        "birth_date": profile.birth_date,
        "height_cm": profile.height_cm,
        "blood_type": profile.blood_type,
        "current_weight_kg": profile.current_weight_kg,
        "target_weight_kg": profile.target_weight_kg,
        "body_fat_percentage": profile.body_fat_percentage,
        "muscle_mass_kg": profile.muscle_mass_kg,
        "target_steps": profile.target_steps if profile.target_steps is not None else 8000,
        "target_sleep_hours": profile.target_sleep_hours if profile.target_sleep_hours is not None else 7.5,
        "target_water_ml": profile.target_water_ml if profile.target_water_ml is not None else 2000,
        "target_calories_burn": profile.target_calories_burn,
        "target_exercise_minutes": profile.target_exercise_minutes if profile.target_exercise_minutes is not None else 30,
        "chronic_conditions": parse_json_field(profile.chronic_conditions, []),
        "allergies": parse_json_field(profile.allergies, []),
        "family_history": parse_json_field(profile.family_history, []),
        "surgeries": parse_json_field(profile.surgeries, []),
        "current_medications": parse_json_field(profile.current_medications, []),
        "exercise_frequency": profile.exercise_frequency,
        "diet_preference": profile.diet_preference,
        "smoking_status": profile.smoking_status,
        "alcohol_consumption": profile.alcohol_consumption,
        "usual_sleep_time": profile.usual_sleep_time,
        "usual_wake_time": profile.usual_wake_time,
        "sleep_environment": parse_json_field(profile.sleep_environment, {}),
        "work_type": profile.work_type,
        "work_hours_per_day": profile.work_hours_per_day,
        "sitting_hours_per_day": profile.sitting_hours_per_day,
        "city": profile.city,
        "timezone": profile.timezone or "Asia/Shanghai",
        "devices": parse_json_field(profile.devices, []),
        "privacy_settings": PrivacySettings(**parse_json_field(profile.privacy_settings, {
            "weight": True, "height": True, "age": True,
            "gender": True, "city": True, "location": True
        })),
        "age": profile.age,
        "bmi": profile.bmi,
        "bmi_category": profile.bmi_category,
        "detected_location": DetectedLocation(
            city=profile.detected_city,
            region=profile.detected_region,
            country=profile.detected_country
        ) if profile.detected_city or profile.detected_region or profile.detected_country else None,
        "location_updated_at": profile.location_updated_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }

    return UserProfileResponse(**response_data)


@router.put("/me", response_model=UserProfileResponse)
async def update_my_profile(
    profile_data: UserProfileUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新当前用户的画像"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    
    if not profile:
        # 自动创建
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
    
    # 更新非空字段
    update_data = profile_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    
    db.commit()
    db.refresh(profile)
    
    # 处理 JSON 字段（数据库中可能是字符串）
    def parse_json_field(field_value, default):
        if field_value is None:
            return default
        if isinstance(field_value, str):
            try:
                return json.loads(field_value)
            except:
                return default
        return field_value
    
    # 构建响应数据，处理所有可能为 None 的字段
    response_data = {
        "id": profile.id,
        "user_id": profile.user_id,
        "gender": profile.gender,
        "birth_date": profile.birth_date,
        "height_cm": profile.height_cm,
        "blood_type": profile.blood_type,
        "current_weight_kg": profile.current_weight_kg,
        "target_weight_kg": profile.target_weight_kg,
        "body_fat_percentage": profile.body_fat_percentage,
        "muscle_mass_kg": profile.muscle_mass_kg,
        "target_steps": profile.target_steps if profile.target_steps is not None else 8000,
        "target_sleep_hours": profile.target_sleep_hours if profile.target_sleep_hours is not None else 7.5,
        "target_water_ml": profile.target_water_ml if profile.target_water_ml is not None else 2000,
        "target_calories_burn": profile.target_calories_burn,
        "target_exercise_minutes": profile.target_exercise_minutes if profile.target_exercise_minutes is not None else 30,
        "chronic_conditions": parse_json_field(profile.chronic_conditions, []),
        "allergies": parse_json_field(profile.allergies, []),
        "family_history": parse_json_field(profile.family_history, []),
        "surgeries": parse_json_field(profile.surgeries, []),
        "current_medications": parse_json_field(profile.current_medications, []),
        "exercise_frequency": profile.exercise_frequency,
        "diet_preference": profile.diet_preference,
        "smoking_status": profile.smoking_status,
        "alcohol_consumption": profile.alcohol_consumption,
        "usual_sleep_time": profile.usual_sleep_time,
        "usual_wake_time": profile.usual_wake_time,
        "sleep_environment": parse_json_field(profile.sleep_environment, {}),
        "work_type": profile.work_type,
        "work_hours_per_day": profile.work_hours_per_day,
        "sitting_hours_per_day": profile.sitting_hours_per_day,
        "city": profile.city,
        "timezone": profile.timezone or "Asia/Shanghai",
        "devices": parse_json_field(profile.devices, []),
        "privacy_settings": PrivacySettings(**parse_json_field(profile.privacy_settings, {
            "weight": True, "height": True, "age": True,
            "gender": True, "city": True, "location": True
        })),
        "age": profile.age,
        "bmi": profile.bmi,
        "bmi_category": profile.bmi_category,
        "detected_location": DetectedLocation(
            city=profile.detected_city,
            region=profile.detected_region,
            country=profile.detected_country
        ) if profile.detected_city or profile.detected_region or profile.detected_country else None,
        "location_updated_at": profile.location_updated_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at
    }

    return UserProfileResponse(**response_data)


@router.post("/me/refresh-location")
async def refresh_my_location(
    request: Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    手动刷新用户位置信息（基于IP）

    返回更新后的位置信息
    """
    from app.services.ip_geolocation import get_geolocation_service

    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()

    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    # 获取客户端 IP
    client_ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.headers.get("X-Real-IP", "")
    if not client_ip:
        client_ip = request.client.host if request.client else ""

    if not client_ip:
        raise HTTPException(status_code=400, detail="无法获取客户端 IP")

    # 强制获取位置（不检查时间间隔）
    service = get_geolocation_service()
    location = await service.get_location_from_ip(client_ip)

    if location:
        from datetime import datetime
        profile.detected_city = location.city
        profile.detected_region = location.region
        profile.detected_country = location.country
        profile.location_updated_at = datetime.utcnow()
        profile.last_ip = client_ip
        db.commit()
        db.refresh(profile)

        return {
            "success": True,
            "location": {
                "city": location.city,
                "region": location.region,
                "country": location.country
            },
            "ip": client_ip,
            "updated_at": profile.location_updated_at
        }
    else:
        return {
            "success": False,
            "message": "无法获取位置信息（可能是本地IP或服务不可用）",
            "ip": client_ip
        }


@router.post("/me/chronic-conditions", response_model=UserProfileResponse)
async def add_chronic_condition(
    condition: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """添加慢性病"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id, chronic_conditions=[])
        db.add(profile)
    
    conditions = profile.chronic_conditions or []
    if condition not in conditions:
        conditions.append(condition)
        profile.chronic_conditions = conditions
        db.commit()
        db.refresh(profile)
    
    return UserProfileResponse.model_validate(profile)


@router.delete("/me/chronic-conditions/{condition}", response_model=UserProfileResponse)
async def remove_chronic_condition(
    condition: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """移除慢性病"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        raise HTTPException(status_code=404, detail="用户画像不存在")
    
    conditions = profile.chronic_conditions or []
    if condition in conditions:
        conditions.remove(condition)
        profile.chronic_conditions = conditions
        db.commit()
        db.refresh(profile)
    
    return UserProfileResponse.model_validate(profile)


# =====================================================
# 健康目标 API
# =====================================================

@router.get("/goals", response_model=list[HealthGoalResponse])
async def get_my_goals(
    status_filter: Optional[str] = None,
    goal_type: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户的健康目标"""
    query = db.query(HealthGoal).filter(HealthGoal.user_id == current_user.id)
    
    if status_filter:
        query = query.filter(HealthGoal.status == status_filter)
    if goal_type:
        query = query.filter(HealthGoal.goal_type == goal_type)
    
    goals = query.order_by(HealthGoal.priority, HealthGoal.created_at.desc()).all()
    
    # 计算进度
    result = []
    for goal in goals:
        response = HealthGoalResponse.model_validate(goal)
        
        # 计算完成百分比
        if goal.target_value and goal.current_value is not None:
            response.progress_percentage = round((goal.current_value / goal.target_value) * 100, 1)
        
        # 计算剩余天数
        if goal.target_date:
            remaining = (goal.target_date - date.today()).days
            response.days_remaining = max(0, remaining)
        
        result.append(response)
    
    return result


@router.post("/goals", response_model=HealthGoalResponse)
async def create_goal(
    goal_data: HealthGoalCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建健康目标"""
    goal = HealthGoal(
        user_id=current_user.id,
        **goal_data.model_dump()
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    
    return HealthGoalResponse.model_validate(goal)


@router.put("/goals/{goal_id}", response_model=HealthGoalResponse)
async def update_goal(
    goal_id: int,
    goal_data: HealthGoalUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新健康目标"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()
    
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    update_data = goal_data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(goal, key, value)
    
    # 如果状态变为completed，记录完成时间
    if goal_data.status == "completed":
        from datetime import datetime
        goal.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(goal)
    
    return HealthGoalResponse.model_validate(goal)


@router.delete("/goals/{goal_id}")
async def delete_goal(
    goal_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """删除健康目标"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()
    
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    db.delete(goal)
    db.commit()
    
    return {"message": "目标已删除"}


@router.post("/goals/{goal_id}/progress", response_model=HealthGoalResponse)
async def update_goal_progress(
    goal_id: int,
    current_value: float,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """更新目标进度"""
    goal = db.query(HealthGoal).filter(
        HealthGoal.id == goal_id,
        HealthGoal.user_id == current_user.id
    ).first()
    
    if not goal:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    goal.current_value = current_value
    
    # 检查是否达成目标
    if goal.target_value and current_value >= goal.target_value:
        goal.status = "completed"
        from datetime import datetime
        goal.completed_at = datetime.utcnow()
    
    db.commit()
    db.refresh(goal)
    
    response = HealthGoalResponse.model_validate(goal)
    if goal.target_value:
        response.progress_percentage = round((goal.current_value / goal.target_value) * 100, 1)
    
    return response


# =====================================================
# AI 个性化建议 API
# =====================================================

@router.get("/advice/morning")
async def get_morning_advice(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取早间个性化健康建议"""
    from app.services.ai.personalized_advice import get_personalized_advice
    return get_personalized_advice(db, current_user.id, 'morning')


@router.get("/advice/summary")
async def get_daily_summary_advice(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取每日总结和建议"""
    from app.services.ai.personalized_advice import get_personalized_advice
    return get_personalized_advice(db, current_user.id, 'summary')


@router.get("/advice/checkin/{template_name}")
async def get_checkin_advice(
    template_name: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取打卡前的鼓励建议"""
    from app.services.ai.personalized_advice import PersonalizedAdviceService
    service = PersonalizedAdviceService(db, current_user.id)
    return {"advice": service.get_checkin_advice(template_name)}
