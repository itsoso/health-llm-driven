"""数据模型"""
from app.models.user import User
from app.models.basic_health import BasicHealthData
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.disease import DiseaseRecord
from app.models.daily_health import (
    GarminData,
    ExerciseRecord,
    DietRecord,
    WaterIntake,
    SupplementIntake,
    OutdoorActivity
)
from app.models.health_checkin import HealthCheckin
from app.models.goal import Goal, GoalProgress
from app.models.daily_recommendation import DailyRecommendation
from app.models.health_analysis_cache import HealthAnalysisCache

__all__ = [
    "User",
    "BasicHealthData",
    "MedicalExam",
    "MedicalExamItem",
    "DiseaseRecord",
    "GarminData",
    "ExerciseRecord",
    "DietRecord",
    "WaterIntake",
    "SupplementIntake",
    "OutdoorActivity",
    "HealthCheckin",
    "Goal",
    "GoalProgress",
    "DailyRecommendation",
    "HealthAnalysisCache",
]

