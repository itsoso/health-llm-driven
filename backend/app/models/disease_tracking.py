"""
增强版疾病追踪模型

支持:
- 每日症状记录
- 疾病管理模板
- 用药提醒
- 环境关联预警
"""

from sqlalchemy import Column, Integer, String, DateTime, Date, Float, ForeignKey, Text, Boolean, JSON, Time
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DiseaseTemplate(Base):
    """
    疾病管理模板
    
    预定义常见疾病的追踪项目和管理建议
    """
    __tablename__ = "disease_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    name = Column(String, nullable=False, unique=True, index=True)  # 疾病名称
    display_name = Column(String, nullable=False)  # 显示名称
    category = Column(String, nullable=False)  # 分类: respiratory/vision/cardiovascular/digestive/skin/mental/other
    icon = Column(String)  # 图标
    
    # 症状列表
    symptoms = Column(JSON, default=[])  # 预定义的症状选项
    # 例如: ["鼻塞", "流涕", "打喷嚏", "鼻痒", "嗅觉减退"]
    
    # 触发因素
    triggers = Column(JSON, default=[])  # 常见触发因素
    # 例如: ["花粉", "尘螨", "冷空气", "油烟", "香水"]
    
    # 环境敏感性
    environment_sensitive = Column(Boolean, default=False)  # 是否对环境敏感
    sensitive_factors = Column(JSON, default=[])  # 敏感因素: air_quality, temperature, humidity, pollen
    
    # 管理建议
    daily_tips = Column(JSON, default=[])  # 日常护理建议
    medication_types = Column(JSON, default=[])  # 常用药物类型
    prevention_tips = Column(JSON, default=[])  # 预防建议
    
    # 追踪频率建议
    tracking_frequency = Column(String, default="daily")  # daily/weekly/on_symptom
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserDiseaseProfile(Base):
    """
    用户疾病档案
    
    记录用户的慢性病/长期健康问题
    """
    __tablename__ = "user_disease_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    template_id = Column(Integer, ForeignKey("disease_templates.id"), nullable=True)
    
    # 疾病信息
    disease_name = Column(String, nullable=False, index=True)
    diagnosis_date = Column(Date)  # 确诊日期
    severity = Column(String, default="moderate")  # mild/moderate/severe
    status = Column(String, default="chronic")  # chronic/improving/controlled/cured
    
    # 个性化设置
    personal_triggers = Column(JSON, default=[])  # 个人触发因素
    personal_symptoms = Column(JSON, default=[])  # 个人常见症状
    
    # 用药情况
    current_medications = Column(JSON, default=[])  # 当前用药
    # [{"name": "氯雷他定", "dosage": "10mg", "frequency": "每日1次"}]
    
    # 追踪设置
    tracking_enabled = Column(Boolean, default=True)
    reminder_time = Column(Time)  # 每日记录提醒时间
    
    # 目标设置
    target_symptom_days = Column(Integer, default=0)  # 目标无症状天数
    current_streak = Column(Integer, default=0)  # 当前连续无症状天数
    best_streak = Column(Integer, default=0)  # 最长连续无症状天数
    
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    template = relationship("DiseaseTemplate")
    symptom_logs = relationship("SymptomLog", back_populates="disease_profile", cascade="all, delete-orphan")


class SymptomLog(Base):
    """
    症状日志
    
    每日症状记录
    """
    __tablename__ = "symptom_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    disease_profile_id = Column(Integer, ForeignKey("user_disease_profiles.id"), nullable=False)
    
    # 记录时间
    log_date = Column(Date, nullable=False, index=True)
    log_time = Column(DateTime(timezone=True), server_default=func.now())
    
    # 症状评分 (0-10，0表示无症状)
    overall_severity = Column(Integer, default=0)  # 总体严重程度
    
    # 具体症状记录
    symptoms = Column(JSON, default=[])
    # [{"name": "鼻塞", "severity": 5}, {"name": "流涕", "severity": 3}]
    
    # 触发因素
    triggers = Column(JSON, default=[])  # 当日触发因素
    
    # 用药记录
    medications_taken = Column(JSON, default=[])
    # [{"name": "氯雷他定", "time": "08:00"}]
    
    # 治疗措施
    treatments = Column(JSON, default=[])
    # ["洗鼻", "热敷", "雾化"]
    
    # 环境数据（自动关联）
    weather_data = Column(JSON, default={})  # 当日天气
    air_quality_data = Column(JSON, default={})  # 当日空气质量
    
    # 生活因素
    sleep_hours = Column(Float)  # 睡眠时长
    stress_level = Column(Integer)  # 压力水平 (1-5)
    diet_notes = Column(String)  # 饮食记录
    
    # 备注
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    disease_profile = relationship("UserDiseaseProfile", back_populates="symptom_logs")


class VisionRecord(Base):
    """
    视力记录
    
    专门用于青少年近视追踪
    """
    __tablename__ = "vision_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    
    # 裸眼视力
    left_eye_naked = Column(Float)  # 左眼裸眼视力
    right_eye_naked = Column(Float)  # 右眼裸眼视力
    
    # 矫正视力
    left_eye_corrected = Column(Float)  # 左眼矫正视力
    right_eye_corrected = Column(Float)  # 右眼矫正视力
    
    # 屈光度
    left_eye_sphere = Column(Float)  # 左眼球镜度数（近视为负，远视为正）
    right_eye_sphere = Column(Float)  # 右眼球镜度数
    left_eye_cylinder = Column(Float)  # 左眼散光度数
    right_eye_cylinder = Column(Float)  # 右眼散光度数
    left_eye_axis = Column(Integer)  # 左眼散光轴向
    right_eye_axis = Column(Integer)  # 右眼散光轴向
    
    # 眼轴长度
    left_eye_axial = Column(Float)  # 左眼眼轴长度 (mm)
    right_eye_axial = Column(Float)  # 右眼眼轴长度 (mm)
    
    # 检查信息
    exam_type = Column(String)  # 检查类型: routine/comprehensive/optometry
    exam_location = Column(String)  # 检查地点
    doctor_name = Column(String)
    
    # 干预措施
    interventions = Column(JSON, default=[])
    # ["OK镜", "低浓度阿托品", "户外活动2小时"]
    
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DailyEyeHabit(Base):
    """
    每日用眼习惯记录
    
    用于近视防控
    """
    __tablename__ = "daily_eye_habits"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    
    # 户外活动
    outdoor_minutes = Column(Integer, default=0)  # 户外活动时长
    outdoor_sunlight = Column(Boolean, default=False)  # 是否有阳光
    
    # 用眼时长
    screen_minutes = Column(Integer, default=0)  # 屏幕使用时长
    reading_minutes = Column(Integer, default=0)  # 阅读时长
    homework_minutes = Column(Integer, default=0)  # 作业时长
    
    # 用眼习惯
    eye_rest_count = Column(Integer, default=0)  # 眼睛休息次数（20-20-20法则）
    lighting_quality = Column(String)  # 光线质量: good/moderate/poor
    reading_distance = Column(String)  # 阅读距离: proper/close/very_close
    posture = Column(String)  # 坐姿: good/moderate/poor
    
    # 干预执行
    interventions_done = Column(JSON, default=[])
    # ["OK镜佩戴", "阿托品滴眼", "眼保健操"]
    
    # 眼部症状
    eye_fatigue = Column(Integer, default=0)  # 眼疲劳程度 (0-5)
    dry_eyes = Column(Boolean, default=False)  # 是否干眼
    
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
