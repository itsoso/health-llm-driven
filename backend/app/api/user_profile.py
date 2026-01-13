"""
用户画像 API - executor.life
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile, HealthGoal
from app.schemas.user_profile import (
    UserProfileCreate, UserProfileUpdate, UserProfileResponse,
    HealthGoalCreate, HealthGoalUpdate, HealthGoalResponse
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
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    
    if not profile:
        # 自动创建空的用户画像
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    
    # 添加计算字段
    response = UserProfileResponse.model_validate(profile)
    response.age = profile.age
    response.bmi = profile.bmi
    response.bmi_category = profile.bmi_category
    
    return response


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
    
    # 添加计算字段
    response = UserProfileResponse.model_validate(profile)
    response.age = profile.age
    response.bmi = profile.bmi
    response.bmi_category = profile.bmi_category
    
    return response


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
