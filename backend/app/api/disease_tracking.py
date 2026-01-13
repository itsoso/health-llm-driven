"""
疾病追踪 API

提供疾病管理、症状追踪、视力追踪等功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel, Field
import logging

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services.disease_tracking import DiseaseTrackingService

router = APIRouter(prefix="/disease", tags=["disease-tracking"])
logger = logging.getLogger(__name__)


# ========== Pydantic 模型 ==========

class SymptomItem(BaseModel):
    name: str
    severity: int = Field(ge=0, le=10)


class MedicationItem(BaseModel):
    name: str
    time: Optional[str] = None
    dosage: Optional[str] = None


class CreateDiseaseProfileRequest(BaseModel):
    disease_name: str
    template_name: Optional[str] = None
    diagnosis_date: Optional[date] = None
    severity: str = "moderate"
    personal_triggers: List[str] = []
    current_medications: List[MedicationItem] = []


class LogSymptomsRequest(BaseModel):
    log_date: date
    overall_severity: int = Field(ge=0, le=10)
    symptoms: List[SymptomItem] = []
    triggers: List[str] = []
    medications_taken: List[MedicationItem] = []
    treatments: List[str] = []
    notes: Optional[str] = None


class VisionRecordRequest(BaseModel):
    record_date: date
    left_eye_naked: Optional[float] = None
    right_eye_naked: Optional[float] = None
    left_eye_sphere: Optional[float] = None
    right_eye_sphere: Optional[float] = None
    left_eye_cylinder: Optional[float] = None
    right_eye_cylinder: Optional[float] = None
    left_eye_axial: Optional[float] = None
    right_eye_axial: Optional[float] = None
    exam_type: str = "routine"
    exam_location: Optional[str] = None
    interventions: List[str] = []
    notes: Optional[str] = None


class DailyEyeHabitRequest(BaseModel):
    record_date: date
    outdoor_minutes: int = 0
    screen_minutes: int = 0
    reading_minutes: int = 0
    eye_rest_count: int = 0
    interventions_done: List[str] = []
    eye_fatigue: int = Field(0, ge=0, le=5)
    notes: Optional[str] = None


# ========== 疾病模板 API ==========

@router.post("/templates/init", summary="初始化默认疾病模板")
def init_disease_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """初始化系统默认的疾病模板"""
    service = DiseaseTrackingService(db, current_user.id)
    created = service.init_default_templates()
    return {"message": f"已创建 {created} 个疾病模板", "created": created}


@router.get("/templates", summary="获取疾病模板列表")
def get_disease_templates(
    category: Optional[str] = Query(None, description="分类筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取所有疾病模板"""
    service = DiseaseTrackingService(db, current_user.id)
    templates = service.get_templates(category)
    return [
        {
            "id": t.id,
            "name": t.name,
            "display_name": t.display_name,
            "category": t.category,
            "icon": t.icon,
            "symptoms": t.symptoms,
            "triggers": t.triggers,
            "environment_sensitive": t.environment_sensitive,
            "daily_tips": t.daily_tips
        }
        for t in templates
    ]


# ========== 用户疾病档案 API ==========

@router.post("/profiles", summary="创建疾病档案", status_code=status.HTTP_201_CREATED)
def create_disease_profile(
    request: CreateDiseaseProfileRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """创建用户疾病档案"""
    service = DiseaseTrackingService(db, current_user.id)
    profile = service.create_disease_profile(
        disease_name=request.disease_name,
        template_name=request.template_name,
        diagnosis_date=request.diagnosis_date,
        severity=request.severity,
        personal_triggers=request.personal_triggers,
        current_medications=[m.model_dump() for m in request.current_medications]
    )
    return {
        "id": profile.id,
        "disease_name": profile.disease_name,
        "severity": profile.severity,
        "status": profile.status,
        "current_streak": profile.current_streak,
        "best_streak": profile.best_streak
    }


@router.get("/profiles", summary="获取用户疾病档案列表")
def get_disease_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取当前用户的所有疾病档案"""
    service = DiseaseTrackingService(db, current_user.id)
    profiles = service.get_user_disease_profiles()
    return [
        {
            "id": p.id,
            "disease_name": p.disease_name,
            "diagnosis_date": p.diagnosis_date.isoformat() if p.diagnosis_date else None,
            "severity": p.severity,
            "status": p.status,
            "tracking_enabled": p.tracking_enabled,
            "current_streak": p.current_streak,
            "best_streak": p.best_streak,
            "template": {
                "name": p.template.name,
                "display_name": p.template.display_name,
                "icon": p.template.icon
            } if p.template else None
        }
        for p in profiles
    ]


@router.get("/profiles/{profile_id}", summary="获取疾病档案详情")
def get_disease_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取指定疾病档案详情"""
    service = DiseaseTrackingService(db, current_user.id)
    profile = service.get_disease_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="疾病档案不存在")
    
    return {
        "id": profile.id,
        "disease_name": profile.disease_name,
        "diagnosis_date": profile.diagnosis_date.isoformat() if profile.diagnosis_date else None,
        "severity": profile.severity,
        "status": profile.status,
        "personal_triggers": profile.personal_triggers,
        "personal_symptoms": profile.personal_symptoms,
        "current_medications": profile.current_medications,
        "tracking_enabled": profile.tracking_enabled,
        "current_streak": profile.current_streak,
        "best_streak": profile.best_streak,
        "target_symptom_days": profile.target_symptom_days,
        "template": {
            "name": profile.template.name,
            "display_name": profile.template.display_name,
            "icon": profile.template.icon,
            "symptoms": profile.template.symptoms,
            "triggers": profile.template.triggers,
            "daily_tips": profile.template.daily_tips,
            "medication_types": profile.template.medication_types
        } if profile.template else None
    }


# ========== 症状记录 API ==========

@router.post("/profiles/{profile_id}/symptoms", summary="记录症状", status_code=status.HTTP_201_CREATED)
def log_symptoms(
    profile_id: int,
    request: LogSymptomsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """记录症状"""
    service = DiseaseTrackingService(db, current_user.id)
    
    # 验证档案存在
    profile = service.get_disease_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="疾病档案不存在")
    
    log = service.log_symptoms(
        profile_id=profile_id,
        log_date=request.log_date,
        overall_severity=request.overall_severity,
        symptoms=[s.model_dump() for s in request.symptoms],
        triggers=request.triggers,
        medications_taken=[m.model_dump() for m in request.medications_taken],
        treatments=request.treatments,
        notes=request.notes
    )
    
    return {
        "id": log.id,
        "log_date": log.log_date.isoformat(),
        "overall_severity": log.overall_severity,
        "symptoms": log.symptoms,
        "current_streak": profile.current_streak,
        "message": "记录成功！" if log.overall_severity > 0 else f"无症状日！当前连续 {profile.current_streak} 天无症状"
    }


@router.get("/profiles/{profile_id}/symptoms", summary="获取症状记录")
def get_symptoms(
    profile_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取症状记录列表"""
    service = DiseaseTrackingService(db, current_user.id)
    logs = service.get_symptom_logs(profile_id, start_date, end_date, limit)
    return [
        {
            "id": log.id,
            "log_date": log.log_date.isoformat(),
            "overall_severity": log.overall_severity,
            "symptoms": log.symptoms,
            "triggers": log.triggers,
            "medications_taken": log.medications_taken,
            "treatments": log.treatments,
            "notes": log.notes
        }
        for log in logs
    ]


@router.get("/profiles/{profile_id}/stats", summary="获取症状统计")
def get_symptom_stats(
    profile_id: int,
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取症状统计分析"""
    service = DiseaseTrackingService(db, current_user.id)
    
    # 验证档案存在
    profile = service.get_disease_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="疾病档案不存在")
    
    stats = service.get_symptom_stats(profile_id, days)
    return stats


@router.get("/profiles/{profile_id}/alert", summary="获取环境预警")
async def get_environment_alert(
    profile_id: int,
    city: Optional[str] = Query(None, description="城市名称"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取疾病相关的环境预警"""
    service = DiseaseTrackingService(db, current_user.id)
    
    # 验证档案存在
    profile = service.get_disease_profile(profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="疾病档案不存在")
    
    alert = await service.get_environment_alert(profile_id, city)
    return alert


# ========== 视力追踪 API ==========

@router.post("/vision/records", summary="添加视力记录", status_code=status.HTTP_201_CREATED)
def add_vision_record(
    request: VisionRecordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """添加视力检查记录"""
    service = DiseaseTrackingService(db, current_user.id)
    record = service.add_vision_record(
        record_date=request.record_date,
        left_eye_naked=request.left_eye_naked,
        right_eye_naked=request.right_eye_naked,
        left_eye_sphere=request.left_eye_sphere,
        right_eye_sphere=request.right_eye_sphere,
        left_eye_cylinder=request.left_eye_cylinder,
        right_eye_cylinder=request.right_eye_cylinder,
        left_eye_axial=request.left_eye_axial,
        right_eye_axial=request.right_eye_axial,
        exam_type=request.exam_type,
        exam_location=request.exam_location,
        interventions=request.interventions,
        notes=request.notes
    )
    return {
        "id": record.id,
        "record_date": record.record_date.isoformat(),
        "left_eye_sphere": record.left_eye_sphere,
        "right_eye_sphere": record.right_eye_sphere
    }


@router.get("/vision/records", summary="获取视力记录")
def get_vision_records(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取视力检查记录列表"""
    service = DiseaseTrackingService(db, current_user.id)
    records = service.get_vision_records(limit)
    return [
        {
            "id": r.id,
            "record_date": r.record_date.isoformat(),
            "left_eye_naked": r.left_eye_naked,
            "right_eye_naked": r.right_eye_naked,
            "left_eye_sphere": r.left_eye_sphere,
            "right_eye_sphere": r.right_eye_sphere,
            "left_eye_cylinder": r.left_eye_cylinder,
            "right_eye_cylinder": r.right_eye_cylinder,
            "left_eye_axial": r.left_eye_axial,
            "right_eye_axial": r.right_eye_axial,
            "exam_type": r.exam_type,
            "interventions": r.interventions
        }
        for r in records
    ]


@router.get("/vision/trend", summary="获取视力变化趋势")
def get_vision_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取视力变化趋势分析"""
    service = DiseaseTrackingService(db, current_user.id)
    return service.get_vision_trend()


@router.post("/vision/habits", summary="记录用眼习惯", status_code=status.HTTP_201_CREATED)
def log_eye_habit(
    request: DailyEyeHabitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """记录每日用眼习惯"""
    service = DiseaseTrackingService(db, current_user.id)
    habit = service.log_daily_eye_habit(
        record_date=request.record_date,
        outdoor_minutes=request.outdoor_minutes,
        screen_minutes=request.screen_minutes,
        reading_minutes=request.reading_minutes,
        eye_rest_count=request.eye_rest_count,
        interventions_done=request.interventions_done,
        eye_fatigue=request.eye_fatigue,
        notes=request.notes
    )
    return {
        "id": habit.id,
        "record_date": habit.record_date.isoformat(),
        "outdoor_minutes": habit.outdoor_minutes,
        "target_achieved": habit.outdoor_minutes >= 120,
        "message": "户外活动达标！" if habit.outdoor_minutes >= 120 else f"还差 {120 - habit.outdoor_minutes} 分钟达到2小时目标"
    }


@router.get("/vision/habits/stats", summary="获取用眼习惯统计")
def get_eye_habit_stats(
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """获取用眼习惯统计分析"""
    service = DiseaseTrackingService(db, current_user.id)
    return service.get_eye_habit_stats(days)
