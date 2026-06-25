"""
用户画像模型 - executor.life 健康模块
包含用户的基本信息、健康目标、疾病历史等
"""
from datetime import UTC, date, datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, Date, DateTime, JSON, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.database import Base


class UserProfile(Base):
    """用户画像 - 存储用户的详细健康相关信息"""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # === 基本信息 ===
    gender = Column(String(10), nullable=True)  # male/female/other
    birth_date = Column(Date, nullable=True)  # 出生日期，用于计算年龄
    height_cm = Column(Float, nullable=True)  # 身高(cm)
    blood_type = Column(String(10), nullable=True)  # A/B/AB/O/Rh+/Rh-

    # === 身体数据 ===
    current_weight_kg = Column(Float, nullable=True)  # 当前体重(kg)
    target_weight_kg = Column(Float, nullable=True)  # 目标体重(kg)
    body_fat_percentage = Column(Float, nullable=True)  # 体脂率(%)
    muscle_mass_kg = Column(Float, nullable=True)  # 肌肉量(kg)

    # === 健康目标 ===
    target_steps = Column(Integer, default=8000)  # 目标步数
    target_sleep_hours = Column(Float, default=7.5)  # 目标睡眠时长(小时)
    target_water_ml = Column(Integer, default=2000)  # 目标饮水量(ml)
    target_calories_burn = Column(Integer, nullable=True)  # 目标消耗卡路里
    target_exercise_minutes = Column(Integer, default=30)  # 目标运动时长(分钟/天)

    # === 疾病历史 (JSON格式存储) ===
    chronic_conditions = Column(JSON, default=list)  # 慢性病: ["鼻炎", "咽炎", "高血压"]
    allergies = Column(JSON, default=list)  # 过敏源: ["花粉", "海鲜", "青霉素"]
    family_history = Column(JSON, default=list)  # 家族病史: ["糖尿病", "心脏病"]
    surgeries = Column(JSON, default=list)  # 手术历史: [{"name": "阑尾切除", "date": "2020-01-01"}]

    # === 正在服用的药物/补剂 ===
    current_medications = Column(JSON, default=list)  # [{"name": "维生素D", "dosage": "1000IU", "frequency": "daily"}]

    # === 生活习惯 ===
    exercise_frequency = Column(String(50), nullable=True)  # never/occasionally/weekly/daily
    diet_preference = Column(String(50), nullable=True)  # normal/vegetarian/vegan/low_carb/keto
    smoking_status = Column(String(20), nullable=True)  # never/former/current
    alcohol_consumption = Column(String(20), nullable=True)  # never/occasionally/moderate/heavy

    # === 睡眠习惯 ===
    usual_sleep_time = Column(String(10), nullable=True)  # "23:00"
    usual_wake_time = Column(String(10), nullable=True)  # "07:00"
    sleep_environment = Column(JSON, default=dict)  # {"mattress": "记忆棉", "room_temp": 22, "noise_level": "quiet"}

    # === 工作环境 ===
    work_type = Column(String(50), nullable=True)  # office/remote/physical/mixed
    work_hours_per_day = Column(Float, nullable=True)  # 每天工作时长
    sitting_hours_per_day = Column(Float, nullable=True)  # 久坐时长
    work_start_time = Column(String(10), nullable=True)  # 上班 "09:00"(时点日程避开工作窗用)
    work_end_time = Column(String(10), nullable=True)  # 下班 "18:00"

    # === 锻炼时点偏好(timing-solver 据此在空窗排锻炼块)===
    workout_pref_window = Column(String(20), nullable=True)  # morning/midday/evening/any(None=不排锻炼块)
    workout_target_minutes = Column(Integer, nullable=True)  # 目标锻炼时长(分钟);缺省走 DEFAULT_WORKOUT_MINUTES
    # P4 锻炼链(opt-in):开启后把单锻炼块展开成「预检→锻炼→拉伸→淋浴→按摩→餐→复盘」链式议程,
    # 每步落一条可完成 HealthProtocol。NULL/False = 维持既有单锻炼项(无回归)。须同时有 workout_pref_window。
    workout_chain_enabled = Column(Boolean, nullable=True)  # None/False=旧单项;True=展开锻炼链

    # === 地理位置（用于天气/空气质量） ===
    city = Column(String(100), nullable=True)  # 所在城市
    timezone = Column(String(50), default="Asia/Shanghai")  # 时区

    # === 设备信息 ===
    devices = Column(JSON, default=list)  # ["Garmin Fenix 7", "Apple Watch", "小米体重秤"]

    # === AI 助理首页布局 ===
    assistant_dashboard_layouts = Column(JSON, default=dict)  # {"web": {"order": [], "hidden": []}, "mobile": {"order": [], "hidden": []}}

    # === 隐私设置 ===
    # 控制哪些字段对外部API可见
    privacy_settings = Column(JSON, default=lambda: {
        "weight": True,
        "height": True,
        "age": True,
        "gender": True,
        "city": True,
        "location": True
    })

    # === IP定位信息 ===
    detected_city = Column(String(100), nullable=True)  # 基于IP检测的城市
    detected_region = Column(String(100), nullable=True)  # 基于IP检测的省份/地区
    detected_country = Column(String(100), nullable=True)  # 基于IP检测的国家
    detected_lat = Column(Float, nullable=True)  # 2026-05-12 GPS 精确坐标 (绕开 city dict fallback)
    detected_lon = Column(Float, nullable=True)
    detected_source = Column(String(16), nullable=True)  # 2026-05-17 'gps' | 'ip' | NULL (legacy). manual 由 use_manual_location flag 决定, 不 stamp 这里.
    location_updated_at = Column(DateTime, nullable=True)  # IP定位最后更新时间
    last_ip = Column(String(45), nullable=True)  # 最后检测的IP地址

    # === 手工输入位置 ===
    manual_city = Column(String(100), nullable=True)  # 手工输入的城市
    manual_region = Column(String(100), nullable=True)  # 手工输入的省份/地区
    manual_country = Column(String(100), nullable=True)  # 手工输入的国家
    use_manual_location = Column(Boolean, default=False)  # 是否使用手工输入的位置

    # === 时区:用户地理位置时区(自动跟随)+ 手动覆盖 (2026-06-25) ===
    # 生效时区优先级 manual_timezone → detected_timezone → 旧 timezone → 默认中国
    # (见 app/utils/timezone.resolve_timezone_name)。旧 `timezone` 列保留为兼容兜底。
    detected_timezone = Column(String(64), nullable=True)  # 设备/IP 检测到的 IANA 时区,自动跟随当前位置
    manual_timezone = Column(String(64), nullable=True)    # 用户手动锁定的 IANA 时区;非空=pin,覆盖 detected

    # === 用户级 LLM 偏好 (2026-05-13) ===
    # 个人选择 chat 用哪个 LLM 模型 (model_id from app/services/llm/model_registry.py).
    # NULL = 走 admin 全局或 settings.llm_provider 默认; 例如 'qwen3.6-plus' / 'gpt-4o' 等.
    # 优先级: user > admin global (set_active_model_id) > settings 默认.
    # 只在前端可见的 chat 入口生效 (agent_executor / orchestrator), 后台任务/specialist 仍走全局.
    llm_model_id = Column(String(50), nullable=True)

    # === 主健康目标 (Onboarding step 5, 2026-05-14) ===
    # 用户最想改善的 1 件事, 给 ActionCard / WeeklyAdvisor 推荐用作偏好信号.
    # 取值: weight_loss / glucose / blood_pressure / sleep / hrv / rhinitis / general
    # NULL = 没填 (允许 onboarding 跳过).
    primary_goal = Column(String(40), nullable=True)

    # === 时间戳 ===
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # 关系
    user = relationship("User", back_populates="profile")

    @property
    def age(self) -> Optional[int]:
        """计算年龄"""
        if self.birth_date:
            today = date.today()
            return today.year - self.birth_date.year - (
                (today.month, today.day) < (self.birth_date.month, self.birth_date.day)
            )
        return None

    @property
    def bmi(self) -> Optional[float]:
        """计算BMI"""
        if self.current_weight_kg and self.height_cm:
            height_m = self.height_cm / 100
            return round(self.current_weight_kg / (height_m * height_m), 1)
        return None

    @property
    def bmi_category(self) -> Optional[str]:
        """BMI分类"""
        bmi = self.bmi
        if bmi is None:
            return None
        if bmi < 18.5:
            return "偏瘦"
        elif bmi < 24:
            return "正常"
        elif bmi < 28:
            return "超重"
        else:
            return "肥胖"


class HealthGoal(Base):
    """健康目标 - 支持用户设置多个具体目标"""
    __tablename__ = "health_goals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # 目标类型
    goal_type = Column(String(50), nullable=False)  # weight/exercise/sleep/water/habit/custom

    # 目标详情
    name = Column(String(200), nullable=False)  # "减重10公斤"
    description = Column(Text, nullable=True)

    # 目标值
    target_value = Column(Float, nullable=True)  # 目标数值
    current_value = Column(Float, nullable=True)  # 当前进度
    unit = Column(String(20), nullable=True)  # kg/步/小时/ml

    # 时间范围
    start_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=True)  # 目标完成日期

    # 状态
    status = Column(String(20), default="active")  # active/completed/paused/abandoned
    priority = Column(Integer, default=1)  # 1-5, 1最高

    # AI生成的建议
    ai_suggestions = Column(JSON, default=list)  # AI给出的达成建议

    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    completed_at = Column(DateTime, nullable=True)
