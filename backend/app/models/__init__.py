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
from app.models.supplement import SupplementDefinition, SupplementRecord
from app.models.habit import HabitDefinition, HabitRecord
from app.models.weight import WeightRecord
from app.models.blood_pressure import BloodPressureRecord
from app.models.device_credential import DeviceCredential
# executor-v2: 新增模型
from app.models.user_profile import UserProfile, HealthGoal
from app.models.checkin import CheckinTemplate, CheckinRecord
from app.models.disease_tracking import (
    DiseaseTemplate, UserDiseaseProfile, SymptomLog,
    VisionRecord, DailyEyeHabit
)
from app.models.invitation import InvitationCode, UserApplication, ApplicationStatus
# 推送通知模型
from app.models.notification import (
    UserNotificationSetting, NotificationLog, ReminderConfig,
    NotificationChannel, NotificationType, NotificationStatus
)
# 复盘模型
from app.models.review import DailyReview, PeriodReview, ReviewPeriod
# 资讯模型
from app.models.news import NewsArticle, NewsApiKey
# 外部建议模型
from app.models.external_recommendation import ExternalRecommendation
# 聊天模型
from app.models.chat import ChatConversation, ChatMessage
# AI 洞察模型
from app.models.ai_insights import AIInsight, RealtimeRecommendation
# 情绪追踪模型
from app.models.mood import MoodRecord
# 健康报告模型
from app.models.health_report import HealthReport
# 用药管理模型
from app.models.medication import Medication, MedicationLog
# 女性健康模型
from app.models.womens_health import MenstrualCycle, CycleSymptom

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
    "SupplementDefinition",
    "SupplementRecord",
    "HabitDefinition",
    "HabitRecord",
    "WeightRecord",
    "BloodPressureRecord",
    "DeviceCredential",
    # executor-v2: 新增模型
    "UserProfile",
    "HealthGoal",
    "CheckinTemplate",
    "CheckinRecord",
    # 疾病追踪模型
    "DiseaseTemplate",
    "UserDiseaseProfile",
    "SymptomLog",
    "VisionRecord",
    "DailyEyeHabit",
    # 邀请码和用户申请
    "InvitationCode",
    "UserApplication",
    "ApplicationStatus",
    # 推送通知
    "UserNotificationSetting",
    "NotificationLog",
    "ReminderConfig",
    "NotificationChannel",
    "NotificationType",
    "NotificationStatus",
    # 复盘模型
    "DailyReview",
    "PeriodReview",
    "ReviewPeriod",
    # 资讯模型
    "NewsArticle",
    "NewsApiKey",
    # 外部建议模型
    "ExternalRecommendation",
    # 聊天模型
    "ChatConversation",
    "ChatMessage",
    # AI 洞察模型
    "AIInsight",
    "RealtimeRecommendation",
    # 情绪追踪模型
    "MoodRecord",
    # 健康报告模型
    "HealthReport",
    # 用药管理模型
    "Medication",
    "MedicationLog",
    # 女性健康模型
    "MenstrualCycle",
    "CycleSymptom",
]

