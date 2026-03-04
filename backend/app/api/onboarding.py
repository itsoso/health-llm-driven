"""新手引导API"""
from datetime import date, datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.models.checkin import CheckinTemplate, DEFAULT_CHECKIN_TEMPLATES
from app.api.deps import get_current_user_required
from app.schemas.onboarding import (
    OnboardingStatusResponse,
    OnboardingStep1Request,
    OnboardingStep2Request,
    OnboardingCompleteRequest,
    ProfileData,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取新手引导状态"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    has_profile = profile is not None and (
        profile.height_cm is not None or profile.current_weight_kg is not None
    )
    has_health_goals = profile is not None and (
        profile.target_steps != 8000
        or profile.target_sleep_hours != 7.5
        or profile.target_water_ml != 2000
        or profile.target_exercise_minutes != 30
    )
    has_checkin_templates = (
        db.query(CheckinTemplate)
        .filter(CheckinTemplate.user_id == current_user.id)
        .count()
        > 0
    )
    # 返回已有的档案数据供前端预填
    profile_data = None
    if profile is not None:
        profile_data = ProfileData(
            height_cm=profile.height_cm,
            current_weight_kg=profile.current_weight_kg,
            gender=profile.gender,
            birth_date=str(profile.birth_date) if profile.birth_date else None,
            target_steps=profile.target_steps or 8000,
            target_sleep_hours=profile.target_sleep_hours or 7.5,
            target_water_ml=profile.target_water_ml or 2000,
            target_exercise_minutes=profile.target_exercise_minutes or 30,
        )

    return OnboardingStatusResponse(
        onboarding_completed=current_user.onboarding_completed or False,
        has_profile=has_profile,
        has_health_goals=has_health_goals,
        has_checkin_templates=has_checkin_templates,
        profile_data=profile_data,
    )


@router.post("/step1")
async def save_step1(
    data: OnboardingStep1Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """保存基本信息到UserProfile"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    if data.height_cm is not None:
        profile.height_cm = data.height_cm
    if data.current_weight_kg is not None:
        profile.current_weight_kg = data.current_weight_kg
    if data.gender is not None:
        profile.gender = data.gender
    if data.birth_date is not None:
        profile.birth_date = date.fromisoformat(data.birth_date)

    db.commit()
    db.refresh(profile)
    return {"message": "基本信息已保存", "profile_id": profile.id}


@router.post("/step2")
async def save_step2(
    data: OnboardingStep2Request,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """保存健康目标到UserProfile"""
    profile = db.query(UserProfile).filter(UserProfile.user_id == current_user.id).first()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)

    profile.target_steps = data.target_steps
    profile.target_sleep_hours = data.target_sleep_hours
    profile.target_water_ml = data.target_water_ml
    profile.target_exercise_minutes = data.target_exercise_minutes

    db.commit()
    db.refresh(profile)
    return {"message": "健康目标已保存", "profile_id": profile.id}


@router.post("/complete")
async def complete_onboarding(
    data: OnboardingCompleteRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """完成新手引导"""
    # 初始化打卡模板（如果用户选择且尚无模板）
    templates_created = 0
    if data.init_default_templates:
        existing_count = (
            db.query(CheckinTemplate)
            .filter(CheckinTemplate.user_id == current_user.id)
            .count()
        )
        if existing_count == 0:
            selected_names = set(data.selected_template_names) if data.selected_template_names else None
            for tmpl_data in DEFAULT_CHECKIN_TEMPLATES:
                if selected_names is not None and tmpl_data["name"] not in selected_names:
                    continue
                template = CheckinTemplate(user_id=current_user.id, **tmpl_data)
                db.add(template)
                templates_created += 1

    # 标记完成
    current_user.onboarding_completed = True
    db.commit()

    return {
        "message": "新手引导已完成",
        "onboarding_completed": True,
        "templates_created": templates_created,
    }


@router.post("/skip")
async def skip_onboarding(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """跳过新手引导（不标记完成，下次登录仍会提示）"""
    return {"message": "已跳过，下次登录将继续引导", "onboarding_completed": False}
