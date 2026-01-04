"""日常健康记录模型"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date, ForeignKey, Text, Time
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class GarminData(Base):
    """Garmin可穿戴设备数据"""
    __tablename__ = "garmin_data"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 日期
    record_date = Column(Date, nullable=False, index=True)
    
    # 心率数据
    avg_heart_rate = Column(Integer)  # 平均心率 (bpm)
    max_heart_rate = Column(Integer)  # 最大心率
    min_heart_rate = Column(Integer)  # 最小心率
    resting_heart_rate = Column(Integer)  # 静息心率
    
    # 心率变异性
    hrv = Column(Float)  # 心率变异性 (ms)
    
    # 睡眠数据
    sleep_score = Column(Integer)  # 睡眠分数 (0-100)
    total_sleep_duration = Column(Integer)  # 总睡眠时长 (分钟)
    deep_sleep_duration = Column(Integer)  # 深度睡眠时长 (分钟)
    rem_sleep_duration = Column(Integer)  # 快速眼动睡眠时长 (分钟)
    light_sleep_duration = Column(Integer)  # 浅睡眠时长 (分钟)
    awake_duration = Column(Integer)  # 清醒时长 (分钟)
    nap_duration = Column(Integer)  # 小睡时长 (分钟)
    sleep_start_time = Column(Time)  # 睡眠开始时间
    sleep_end_time = Column(Time)  # 睡眠结束时间
    
    # 身体电量
    body_battery_charged = Column(Integer)  # 身体电量充电值 (0-100)
    body_battery_drained = Column(Integer)  # 身体电量消耗值
    body_battery_most_charged = Column(Integer)  # 最高充电值
    body_battery_lowest = Column(Integer)  # 最低值
    
    # 压力数据
    stress_level = Column(Integer)  # 压力水平 (0-100)
    
    # 步数
    steps = Column(Integer)  # 步数
    
    # 活动数据
    calories_burned = Column(Integer)  # 消耗卡路里
    active_minutes = Column(Integer)  # 活动分钟数
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="garmin_records")


class ExerciseRecord(Base):
    """日常锻炼记录（Garmin未记录部分）"""
    __tablename__ = "exercise_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    exercise_type = Column(String, nullable=False)  # 运动类型
    duration = Column(Integer)  # 持续时间 (分钟)
    intensity = Column(String)  # 强度（低/中/高）
    calories_burned = Column(Integer)  # 消耗卡路里
    distance = Column(Float)  # 距离 (km)
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="exercise_records")


class DietRecord(Base):
    """日常饮食记录"""
    __tablename__ = "diet_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    meal_type = Column(String, nullable=False)  # 餐次（早餐/午餐/晚餐/加餐）
    meal_time = Column(Time)  # 用餐时间
    
    # 食物信息
    food_name = Column(String, nullable=False)  # 食物名称
    quantity = Column(Float)  # 数量
    unit = Column(String)  # 单位（g/ml/份）
    
    # 营养信息
    calories = Column(Float)  # 卡路里
    protein = Column(Float)  # 蛋白质 (g)
    carbs = Column(Float)  # 碳水化合物 (g)
    fat = Column(Float)  # 脂肪 (g)
    fiber = Column(Float)  # 纤维 (g)
    
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="diet_records")


class WaterIntake(Base):
    """日常饮水记录"""
    __tablename__ = "water_intakes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    intake_time = Column(DateTime(timezone=True))  # 饮水时间
    amount = Column(Float, nullable=False)  # 饮水量 (ml)
    drink_type = Column(String)  # 饮品类型（水、茶、咖啡等）
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="water_intakes")


class SupplementIntake(Base):
    """补剂摄入记录"""
    __tablename__ = "supplement_intakes"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    supplement_name = Column(String, nullable=False)  # 补剂名称
    intake_time = Column(Time)  # 摄入时间
    dosage = Column(Float)  # 剂量
    unit = Column(String)  # 单位（mg/g/片/粒）
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="supplement_intakes")


class OutdoorActivity(Base):
    """户外活动记录（太阳照射量）"""
    __tablename__ = "outdoor_activities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)
    start_time = Column(Time)  # 开始时间
    end_time = Column(Time)  # 结束时间
    duration = Column(Integer)  # 持续时间 (分钟)
    activity_type = Column(String)  # 活动类型（散步/跑步/户外运动等）
    uv_index = Column(Float)  # 紫外线指数
    notes = Column(Text)  # 备注
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="outdoor_activities")

