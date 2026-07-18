"""数据模型"""
from app.models.user import User
from app.models.phone_auth import PhoneAuthCode
from app.models.basic_health import BasicHealthData
from app.models.medical_exam import MedicalExam, MedicalExamItem
from app.models.disease import DiseaseRecord
from app.models.daily_health import (
    GarminData,
    ExerciseRecord,
    DietRecord,
    DietPhotoDraft,
    WaterIntake,
    SupplementIntake,
    OutdoorActivity
)
from app.models.food_nutrition import FoodItem, FoodNutrient
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
from app.models.desktop_job import DesktopJob
from app.models.health_analysis_cache import HealthAnalysisCache
from app.models.supplement import SupplementProduct, SupplementDefinition, SupplementRecord
from app.models.supplement_inventory import SupplementInventory
from app.models.supplement_ingredient import SupplementIngredient
# P5(D2)复购下单 — 财务一等对象 ReorderIntent(SCAFFOLD,不真下单;独立于 WriteIntent)
from app.models.reorder_intent import ReorderIntent
# HabitDefinition/HabitRecord — DEPRECATED: router disabled, models retained for DB compat only
# from app.models.habit import HabitDefinition, HabitRecord
from app.models.weight import WeightRecord
from app.models.waist import WaistRecord
from app.models.daily_operating_plan import DailyOperatingPlan
from app.models.intervention_event import InterventionEvent
from app.models.daily_artifact import DailyArtifactEvent
from app.models.epigenetic_report import EpigeneticReport
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
# 事件前提醒去重(P1-B)
from app.models.sent_event_reminder import SentEventReminder
# 复盘模型
from app.models.review import DailyReview, PeriodReview, ReviewPeriod
# 用户 API 密钥
from app.models.user_api_key import UserApiKey
# 聊天模型
from app.models.chat import ChatConversation, ChatMessage
# LLM 使用量 / 成本追踪
from app.models.llm_usage import LlmUsageLog
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
from app.models.medication import Medication, MedicationLog, MedicationRegimen
from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.models.health_problem import HealthProblem
from app.models.health_program import HealthProgram
from app.models.originator_recommendation import OriginatorRecommendation
from app.models.connection_checkin import ConnectionCheckin
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
# Agent 对话持久化(物理表名沿用早期历史表, 代码层使用 Agent 命名)
from app.models.agent_conversation import AgentConversation, AgentMessage
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
# 多租户基因原始数据 (专用表, Postgres RLS + per-tenant 加密)
from app.models.genetic_raw import GeneticRawFile, GeneticRawAudit
from app.models.system_knowledge import KBAudit, KBDocument, KBDocumentVector, KBEdge
# Personal Health OS P1 数据底座 + P2 干预闭环
from app.models.twin_snapshot import TwinSnapshot
from app.models.biomarker_observation import BiomarkerObservation
from app.models.intervention_cycle import InterventionCycle, OutcomeMetric
from app.models.crossover_experiment import CrossoverExperiment  # R16 P4 A·B·A·B 交叉实验
# Apple Watch ECG 房颤筛查信号 (点事件, 独立表)
from app.models.ecg_observation import EcgObservation
from app.models.data_connection import (
    ConsentGrant,
    ConnectorPolicy,
    DataConnection,
    ProvenanceRecord,
)
from app.models.health_runtime_governance import (
    DataSourceQuality,
    HealthRuntimeControl,
    UserDataSourcePreference,
)
# 智能卧室环境快照 (家居传感器点事件, §11 不进通用 LLM)
from app.models.bedroom_environment import (
    BedroomAutomationEvent,
    BedroomEnvironmentSnapshot,
)
# Write 层意图 (audio/visual/glance 事件 FK 指向 write_intents — 必须在此集中注册,
# 否则只 `import app.models` 的子进程 (eval runner) 的 create_all 会缺 write_intents 表)
from app.models.write_intent import WriteIntent
# Write 自治层每日上限硬保证计数表(cap-TOCTOU 封口,见 write_autonomy._reserve_autonomy_slot)
from app.models.autonomy_daily_counter import AutonomyDailyCounter
from app.models.client_event import ClientEvent
from app.models.app_release_policy import AppReleasePolicy
from app.models.ambient_wearable import (
    AudioInputEvent,
    GlanceCard,
    HearingHealthTask,
    MealMonitoringSession,
    VisualInputEvent,
)
from app.models.rokid_operation import RokidOperation
from app.models.rokid_pushup import RokidPushupEvent, RokidPushupSession
from app.models.fitness_plan import FitnessPlan
# 程序性记忆/配方 (Harness Slice 3 — 确定性重放的工具序列)
from app.models.procedure_recipe import ProcedureRecipe
from app.models.account_deletion_request import AccountDeletionRequest
from app.models.aigc_media_job import AIGCMediaJob
from app.models.aigc_media_confirmation import AIGCMediaConfirmation

__all__ = [
    "FitnessPlan",
    "ProcedureRecipe",
    "AccountDeletionRequest",
    "AIGCMediaJob",
    "AIGCMediaConfirmation",
    "User",
    "PhoneAuthCode",
    "BasicHealthData",
    "MedicalExam",
    "MedicalExamItem",
    "TwinSnapshot",
    "BiomarkerObservation",
    "InterventionCycle",
    "OutcomeMetric",
    "CrossoverExperiment",
    "EcgObservation",
    "DataConnection",
    "ConsentGrant",
    "ConnectorPolicy",
    "ProvenanceRecord",
    "DataSourceQuality",
    "UserDataSourcePreference",
    "HealthRuntimeControl",
    "BedroomEnvironmentSnapshot",
    "BedroomAutomationEvent",
    "AudioInputEvent",
    "HearingHealthTask",
    "VisualInputEvent",
    "MealMonitoringSession",
    "GlanceCard",
    "RokidOperation",
    "ClientEvent",
    "AppReleasePolicy",
    "RokidPushupSession",
    "RokidPushupEvent",
    "DiseaseRecord",
    "GarminData",
    "ExerciseRecord",
    "DietRecord",
    "FoodItem",
    "FoodNutrient",
    "WaterIntake",
    "SupplementIntake",
    "OutdoorActivity",
    "HealthCheckin",
    "Goal",
    "GoalProgress",
    "DailyRecommendation",
    "DesktopJob",
    "HealthAnalysisCache",
    "SupplementProduct",
    "SupplementDefinition",
    "SupplementRecord",
    "SupplementInventory",
    "SupplementIngredient",
    "ReorderIntent",
    # "HabitDefinition",  # DEPRECATED
    # "HabitRecord",      # DEPRECATED
    "WeightRecord",
    "WaistRecord",
    "DailyOperatingPlan",
    "InterventionEvent",
    "DailyArtifactEvent",
    "EpigeneticReport",
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
    "SentEventReminder",
    "WriteIntent",
    # 复盘模型
    "DailyReview",
    "PeriodReview",
    "ReviewPeriod",
    # 用户API密钥
    "UserApiKey",
    # 聊天模型
    "ChatConversation",
    "ChatMessage",
    "LlmUsageLog",
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
    "MedicationRegimen",
    "HealthProtocol",
    "HealthProtocolEvent",
    "HealthProblem",
    "HealthProgram",
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
    "AgentConversation",
    "AgentMessage",
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
    "GeneticRawFile",
    "GeneticRawAudit",
    "KBDocument",
    "KBEdge",
    "KBAudit",
]
