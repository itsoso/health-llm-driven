"""Pydantic schemas"""
from app.schemas.user import UserCreate, UserResponse
from app.schemas.basic_health import BasicHealthDataCreate, BasicHealthDataResponse
from app.schemas.medical_exam import MedicalExamCreate, MedicalExamResponse, MedicalExamItemCreate
from app.schemas.disease import DiseaseRecordCreate, DiseaseRecordResponse
from app.schemas.daily_health import (
    GarminDataCreate,
    GarminDataResponse,
    ExerciseRecordCreate,
    DietRecordCreate,
    WaterIntakeCreate,
    SupplementIntakeCreate,
    OutdoorActivityCreate
)
from app.schemas.health_checkin import HealthCheckinCreate, HealthCheckinResponse
from app.schemas.goal import GoalCreate, GoalResponse, GoalProgressCreate

__all__ = [
    "UserCreate",
    "UserResponse",
    "BasicHealthDataCreate",
    "BasicHealthDataResponse",
    "MedicalExamCreate",
    "MedicalExamResponse",
    "MedicalExamItemCreate",
    "DiseaseRecordCreate",
    "DiseaseRecordResponse",
    "GarminDataCreate",
    "GarminDataResponse",
    "ExerciseRecordCreate",
    "DietRecordCreate",
    "WaterIntakeCreate",
    "SupplementIntakeCreate",
    "OutdoorActivityCreate",
    "HealthCheckinCreate",
    "HealthCheckinResponse",
    "GoalCreate",
    "GoalResponse",
    "GoalProgressCreate",
]

