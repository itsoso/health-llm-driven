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
from app.models.garmin_timeseries import (
    RespirationSample,
    HrvReading,
    StressSample,
)
from app.models.workout_hr_zone import WorkoutHrZone
from app.models.garmin_device import GarminDevice
from app.models.nocturnal_spo2_event import NocturnalSpO2Event
from app.models.health_checkin import HealthCheckin
from app.models.goal import Goal, GoalProgress
from app.models.daily_recommendation import DailyRecommendation
from app.models.daily_insight import DailyInsight
from app.models.user_judgment_feedback import UserJudgmentFeedback
from app.models.health_analysis_cache import HealthAnalysisCache
from app.models.supplement import SupplementProduct, SupplementDefinition, SupplementRecord
# HabitDefinition/HabitRecord — DEPRECATED: router disabled, models retained for DB compat only
# from app.models.habit import HabitDefinition, HabitRecord
from app.models.weight import WeightRecord
from app.models.waist import WaistRecord
from app.models.daily_operating_plan import DailyOperatingPlan
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
# 用户 API 密钥
from app.models.user_api_key import UserApiKey
# 聊天模型
from app.models.chat import ChatConversation, ChatMessage
# AI 洞察模型
from app.models.ai_insights import AIInsight, RealtimeRecommendation
# 情绪追踪模型
from app.models.mood import MoodRecord
# 通用症状记录 (偶发症状, 不绑慢病档案)
from app.models.symptom_entry import SymptomEntry
# 跑步动态指导会话 (Live Run Coach)
from app.models.live_run import LiveRunSession
# 健康报告模型
from app.models.health_report import HealthReport
# 用药管理模型
from app.models.medication import Medication, MedicationLog
# 女性健康模型
from app.models.womens_health import MenstrualCycle, CycleSymptom
# 视觉API使用记录
from app.models.vision_usage import VisionUsageLog
# 当前病症追踪模型
from app.models.illness import IllnessEpisode, IllnessUpdate
# 排泄记录模型
from app.models.excretion import ExcretionRecord
# 睡眠记录模型
from app.models.sleep_record import SleepRecord
# 活动状态模型
from app.models.activity_status import ActivityStatus
# 健康事件流模型
from app.models.health_event import HealthEvent, EventSource, EventStatus
# 健康异常预警
from app.models.anomaly_alert import AnomalyAlert
# 健康趋势预测
from app.models.health_trend import HealthTrendReport
# OpenClaw Channel
from app.models.openclaw import OpenClawConversation, OpenClawMessage
# 智能助理专用 OpenClaw
from app.models.assistant_openclaw import (
    AssistantOpenClawBinding,
    AssistantOpenClawConversation,
    AssistantOpenClawMessage,
)
# 对话记忆
from app.models.conversation_memory import ConversationMemory
# 对话分享
from app.models.shared_conversation import SharedConversation
# 补剂审计
from app.models.supplement_audit import SupplementAudit, SupplementAuditItem
# 健康咨询
from app.models.health_consultation import HealthConsultation, ConsultationItem
# Agent-Native v3 — Episode 闭环 (Run Recovery Coach 第一刀)
from app.models.episode import (
    HealthEpisode, EpisodeAction, EpisodeFeedback, EpisodeOutcome,
)
from app.models.advice_ledger import AdviceLedger
from app.models.genetic_data import GeneticImportJob, GeneticProfile, GeneticVariant

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
    "SupplementProduct",
    "SupplementDefinition",
    "SupplementRecord",
    # "HabitDefinition",  # DEPRECATED
    # "HabitRecord",      # DEPRECATED
    "WeightRecord",
    "WaistRecord",
    "DailyOperatingPlan",
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
    # 用户API密钥
    "UserApiKey",
    # 聊天模型
    "ChatConversation",
    "ChatMessage",
    # AI 洞察模型
    "AIInsight",
    "RealtimeRecommendation",
    # 情绪追踪模型
    "MoodRecord",
    "SymptomEntry",
    # 健康报告模型
    "HealthReport",
    # 用药管理模型
    "Medication",
    "MedicationLog",
    # 女性健康模型
    "MenstrualCycle",
    "CycleSymptom",
    # 视觉API使用记录
    "VisionUsageLog",
    # 当前病症追踪
    "IllnessEpisode",
    "IllnessUpdate",
    # 排泄记录
    "ExcretionRecord",
    # 睡眠记录
    "SleepRecord",
    # 活动状态
    "ActivityStatus",
    # 健康事件流
    "HealthEvent",
    "EventSource",
    "EventStatus",
    # 健康异常预警
    "AnomalyAlert",
    # 健康趋势预测
    "HealthTrendReport",
    # OpenClaw Channel
    "OpenClawConversation",
    "OpenClawMessage",
    # 智能助理专用 OpenClaw
    "AssistantOpenClawBinding",
    "AssistantOpenClawConversation",
    "AssistantOpenClawMessage",
    # 对话记忆
    "ConversationMemory",
    # 对话分享
    "SharedConversation",
    # 补剂审计
    "SupplementAudit",
    "SupplementAuditItem",
    # 健康咨询
    "HealthConsultation",
    "ConsultationItem",
    # Agent-Native v3 Episode 闭环
    "HealthEpisode",
    "EpisodeAction",
    "EpisodeFeedback",
    "EpisodeOutcome",
    "AdviceLedger",
    "GeneticProfile",
    "GeneticVariant",
    "GeneticImportJob",
]
