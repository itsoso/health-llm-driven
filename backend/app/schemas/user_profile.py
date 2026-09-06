"""
用户画像 API Schemas - executor.life
"""
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


# =====================================================
# 隐私设置 Schema
# =====================================================

class PrivacySettings(BaseModel):
    """隐私设置 - 控制哪些字段对外部API可见"""
    model_config = ConfigDict(extra="forbid")
    weight: bool = Field(True, description="体重是否公开")
    height: bool = Field(True, description="身高是否公开")
    age: bool = Field(True, description="年龄是否公开")
    gender: bool = Field(True, description="性别是否公开")
    city: bool = Field(True, description="城市是否公开")
    location: bool = Field(True, description="IP定位是否公开")


class DetectedLocation(BaseModel):
    """IP检测的位置信息"""
    city: Optional[str] = None
    region: Optional[str] = None
    country: Optional[str] = None


class ManualLocation(BaseModel):
    """手工输入的位置信息"""
    city: Optional[str] = Field(None, description="手工输入的城市")
    region: Optional[str] = Field(None, description="手工输入的省份/地区")
    country: Optional[str] = Field(None, description="手工输入的国家")


class ManualLocationUpdate(BaseModel):
    """更新手工输入位置"""
    use_manual_location: bool = Field(..., description="是否使用手工输入位置")
    city: Optional[str] = Field(None, description="手工输入的城市")
    region: Optional[str] = Field(None, description="手工输入的省份/地区")
    country: Optional[str] = Field(None, description="手工输入的国家")


class DeviceTimezoneUpdate(BaseModel):
    """设备/系统上报的时区(自动跟随地理位置)。mobile 前台/登录时上报。"""
    timezone: str = Field(..., description="设备 IANA 时区,如 Asia/Shanghai / America/Los_Angeles")


class ManualTimezoneUpdate(BaseModel):
    """用户手动锁定时区。timezone 传 null/空 → 取消锁定,恢复自动跟随设备。"""
    timezone: Optional[str] = Field(None, description="手动锁定的 IANA 时区;null/空=取消锁定")


class EffectiveTimezone(BaseModel):
    """派生的生效时区 + 来源。"""
    timezone: str = Field(..., description="当前生效的 IANA 时区")
    source: str = Field(..., description="manual=手动锁定 / detected=设备检测 / profile=旧字段 / default=默认中国")
    detected_timezone: Optional[str] = Field(None, description="设备/位置检测到的时区")
    manual_timezone: Optional[str] = Field(None, description="用户手动锁定的时区(非空=已锁定)")


class AssistantDashboardDeviceLayout(BaseModel):
    """单设备首页布局配置"""
    order: List[str] = Field(default_factory=list, description="首页卡片顺序")
    hidden: List[str] = Field(default_factory=list, description="隐藏的首页卡片")


class AssistantDashboardLayouts(BaseModel):
    """AI 助理首页布局，按设备分别存储"""
    web: AssistantDashboardDeviceLayout = Field(default_factory=AssistantDashboardDeviceLayout)
    mobile: AssistantDashboardDeviceLayout = Field(default_factory=AssistantDashboardDeviceLayout)


class AssistantDashboardLayoutsUpdate(BaseModel):
    """AI 助理首页布局更新（允许只更新一个设备）"""
    web: Optional[AssistantDashboardDeviceLayout] = None
    mobile: Optional[AssistantDashboardDeviceLayout] = None


# =====================================================
# 用户画像 Schemas
# =====================================================

class UserProfileBase(BaseModel):
    """用户画像基础字段"""
    gender: Optional[str] = Field(None, description="性别: male/female/other")
    birth_date: Optional[date] = Field(None, description="出生日期")
    height_cm: Optional[float] = Field(None, ge=50, le=300, description="身高(cm)")
    blood_type: Optional[str] = Field(None, description="血型: A/B/AB/O")

    # 身体数据
    current_weight_kg: Optional[float] = Field(None, ge=20, le=500, description="当前体重(kg)")
    target_weight_kg: Optional[float] = Field(None, ge=20, le=500, description="目标体重(kg)")
    body_fat_percentage: Optional[float] = Field(None, ge=1, le=70, description="体脂率(%)")
    muscle_mass_kg: Optional[float] = Field(None, ge=10, le=200, description="肌肉量(kg)")

    # 健康目标
    target_steps: int = Field(8000, ge=1000, le=100000, description="目标步数")
    target_sleep_hours: float = Field(7.5, ge=4, le=12, description="目标睡眠时长(小时)")
    target_water_ml: int = Field(2000, ge=500, le=5000, description="目标饮水量(ml)")
    target_calories_burn: Optional[int] = Field(None, ge=100, le=5000, description="目标消耗卡路里")
    target_exercise_minutes: int = Field(30, ge=0, le=300, description="目标运动时长(分钟/天)")

    # 疾病历史
    chronic_conditions: List[str] = Field(default_factory=list, description="慢性病列表")
    allergies: List[str] = Field(default_factory=list, description="过敏源列表")
    family_history: List[str] = Field(default_factory=list, description="家族病史")
    surgeries: List[Dict[str, Any]] = Field(default_factory=list, description="手术历史")

    # 正在服用的药物/补剂
    current_medications: List[Dict[str, Any]] = Field(default_factory=list, description="正在服用的药物")

    # 生活习惯
    exercise_frequency: Optional[str] = Field(None, description="运动频率")
    diet_preference: Optional[str] = Field(None, description="饮食偏好")
    smoking_status: Optional[str] = Field(None, description="吸烟状态")
    alcohol_consumption: Optional[str] = Field(None, description="饮酒情况")

    # 睡眠习惯
    usual_sleep_time: Optional[str] = Field(None, description="通常入睡时间")
    usual_wake_time: Optional[str] = Field(None, description="通常起床时间")
    sleep_environment: Dict[str, Any] = Field(default_factory=dict, description="睡眠环境")

    # 工作环境
    work_type: Optional[str] = Field(None, description="工作类型")
    work_hours_per_day: Optional[float] = Field(None, ge=0, le=24, description="每天工作时长")
    sitting_hours_per_day: Optional[float] = Field(None, ge=0, le=24, description="久坐时长")
    work_start_time: Optional[str] = Field(None, description="上班时间 HH:MM(时点日程避开工作窗)")
    work_end_time: Optional[str] = Field(None, description="下班时间 HH:MM")

    # 锻炼时点偏好(时点日程据此排锻炼块)
    workout_pref_window: Optional[str] = Field(None, description="锻炼偏好时段 morning/midday/evening/any(空=不排锻炼块)")
    workout_target_minutes: Optional[int] = Field(None, ge=10, le=240, description="目标锻炼时长(分钟),缺省 40")

    # 地理位置
    city: Optional[str] = Field(None, description="所在城市")
    timezone: str = Field("Asia/Shanghai", description="时区")

    # 设备信息
    devices: List[str] = Field(default_factory=list, description="设备列表")

    # AI 助理首页布局
    assistant_dashboard_layouts: AssistantDashboardLayouts = Field(
        default_factory=AssistantDashboardLayouts,
        description="AI 助理首页布局配置（按设备分开）"
    )

    # 隐私设置
    privacy_settings: Optional[PrivacySettings] = Field(
        default_factory=lambda: PrivacySettings(),
        description="隐私设置"
    )


class UserProfileCreate(UserProfileBase):
    """创建用户画像"""
    pass


class UserProfileUpdate(BaseModel):
    """更新用户画像（所有字段可选）"""
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    height_cm: Optional[float] = None
    blood_type: Optional[str] = None
    current_weight_kg: Optional[float] = None
    target_weight_kg: Optional[float] = None
    body_fat_percentage: Optional[float] = None
    muscle_mass_kg: Optional[float] = None
    target_steps: Optional[int] = None
    target_sleep_hours: Optional[float] = None
    target_water_ml: Optional[int] = None
    target_calories_burn: Optional[int] = None
    target_exercise_minutes: Optional[int] = None
    chronic_conditions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    family_history: Optional[List[str]] = None
    surgeries: Optional[List[Dict[str, Any]]] = None
    current_medications: Optional[List[Dict[str, Any]]] = None
    exercise_frequency: Optional[str] = None
    diet_preference: Optional[str] = None
    smoking_status: Optional[str] = None
    alcohol_consumption: Optional[str] = None
    usual_sleep_time: Optional[str] = None
    usual_wake_time: Optional[str] = None
    sleep_environment: Optional[Dict[str, Any]] = None
    work_type: Optional[str] = None
    work_hours_per_day: Optional[float] = None
    sitting_hours_per_day: Optional[float] = None
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    workout_pref_window: Optional[str] = None
    workout_target_minutes: Optional[int] = Field(None, ge=10, le=240)
    city: Optional[str] = None
    timezone: Optional[str] = None
    devices: Optional[List[str]] = None
    assistant_dashboard_layouts: Optional[AssistantDashboardLayoutsUpdate] = None
    privacy_settings: Optional[PrivacySettings] = None


class UserProfileResponse(UserProfileBase):
    """用户画像响应"""
    id: int
    user_id: int
    age: Optional[int] = Field(None, description="年龄（计算值）")
    bmi: Optional[float] = Field(None, description="BMI（计算值）")
    bmi_category: Optional[str] = Field(None, description="BMI分类（计算值）")

    # IP定位信息
    detected_location: Optional[DetectedLocation] = Field(None, description="IP检测的位置")
    location_updated_at: Optional[datetime] = Field(None, description="位置更新时间")

    # 手工输入位置信息
    manual_location: Optional[ManualLocation] = Field(None, description="手工输入的位置")
    use_manual_location: bool = Field(False, description="是否使用手工输入位置")

    # 时区(自动跟随设备/位置 + 手动覆盖)
    detected_timezone: Optional[str] = Field(None, description="设备/位置检测到的时区")
    manual_timezone: Optional[str] = Field(None, description="用户手动锁定的时区(非空=已锁定)")
    effective_timezone: Optional[str] = Field(None, description="当前生效的 IANA 时区(派生)")
    timezone_source: Optional[str] = Field(None, description="生效时区来源 manual/detected/profile/default")

    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# 健康目标 Schemas
# =====================================================

class HealthGoalBase(BaseModel):
    """健康目标基础字段"""
    goal_type: str = Field(..., description="目标类型: weight/exercise/sleep/water/habit/custom")
    name: str = Field(..., max_length=200, description="目标名称")
    description: Optional[str] = Field(None, description="目标描述")
    target_value: Optional[float] = Field(None, description="目标值")
    current_value: Optional[float] = Field(None, description="当前进度")
    unit: Optional[str] = Field(None, description="单位")
    start_date: date = Field(..., description="开始日期")
    target_date: Optional[date] = Field(None, description="目标完成日期")
    priority: int = Field(1, ge=1, le=5, description="优先级1-5")


class HealthGoalCreate(HealthGoalBase):
    """创建健康目标"""
    pass


class HealthGoalUpdate(BaseModel):
    """更新健康目标"""
    name: Optional[str] = None
    description: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    target_date: Optional[date] = None
    status: Optional[str] = None
    priority: Optional[int] = None


class HealthGoalResponse(HealthGoalBase):
    """健康目标响应"""
    id: int
    user_id: int
    status: str
    ai_suggestions: List[str] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # 计算字段
    progress_percentage: Optional[float] = Field(None, description="完成百分比")
    days_remaining: Optional[int] = Field(None, description="剩余天数")

    model_config = ConfigDict(from_attributes=True)
