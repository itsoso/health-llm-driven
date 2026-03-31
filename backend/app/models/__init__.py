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
from app.models.user_api_key import UserApiKey
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
# 视觉API使用记录
from app.models.vision_usage import VisionUsageLog
# 行程记录模型
from app.models.trip import Trip, TripItem
# 当前病症追踪模型
from app.models.illness import IllnessEpisode, IllnessUpdate
from app.models.kids_pet import KidsPetProfile
# 排泄记录模型
from app.models.excretion import ExcretionRecord
# 睡眠记录模型
from app.models.sleep_record import SleepRecord
# 活动状态模型
from app.models.activity_status import ActivityStatus
# 好友关系和PK挑战模型
from app.models.friendship import Friendship, PKChallenge, ChallengeParticipant
# 单词本模型
from app.models.vocabulary import VocabularyWord
# Kids每日计划模型
from app.models.kids_plan import KidsDailyPlan
# 私信消息模型
from app.models.direct_message import DirectMessage
# 健康事件流模型
from app.models.health_event import HealthEvent, EventSource, EventStatus
# 群聊模型
from app.models.group_chat import GroupChat, GroupMember, GroupMessage
# 健康异常预警
from app.models.anomaly_alert import AnomalyAlert
# 成就徽章
from app.models.achievement import BadgeDefinition, UserBadge
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
    # 用户API密钥
    "UserApiKey",
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
    # 视觉API使用记录
    "VisionUsageLog",
    # 行程记录
    "Trip",
    "TripItem",
    # 当前病症追踪
    "IllnessEpisode",
    "IllnessUpdate",
    "KidsPetProfile",
    # 排泄记录
    "ExcretionRecord",
    # 睡眠记录
    "SleepRecord",
    # 活动状态
    "ActivityStatus",
    # 好友关系和PK挑战
    "Friendship",
    "PKChallenge",
    "ChallengeParticipant",
    # 单词本
    "VocabularyWord",
    # Kids每日计划
    "KidsDailyPlan",
    # 私信消息
    "DirectMessage",
    # 健康事件流
    "HealthEvent",
    "EventSource",
    "EventStatus",
    # 群聊
    "GroupChat",
    "GroupMember",
    "GroupMessage",
    # 健康异常预警
    "AnomalyAlert",
    # 成就徽章
    "BadgeDefinition",
    "UserBadge",
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
]
