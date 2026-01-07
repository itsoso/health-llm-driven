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
    food_name = Column(String, nullable=True)  # 食物名称（旧字段，保留兼容）
    food_items = Column(String, nullable=True)  # 食物列表，逗号分隔
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


class HeartRateSample(Base):
    """心率采样数据（每15分钟一个点，每天约96个点）"""
    __tablename__ = "heart_rate_samples"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    record_date = Column(Date, nullable=False, index=True)  # 记录日期
    sample_time = Column(Time, nullable=False)  # 采样时间 (HH:MM)
    heart_rate = Column(Integer, nullable=False)  # 心率值 (bpm)
    
    # 可选：标记数据来源或类型
    source = Column(String, default="garmin")  # 数据来源
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", backref="heart_rate_samples")
    
    # 复合索引：按用户和日期快速查询
    __table_args__ = (
        # 确保同一用户同一天同一时间只有一条记录
        # Index('ix_hr_user_date', 'user_id', 'record_date'),
    )


class WorkoutRecord(Base):
    """运动训练记录（跑步、游泳、骑车、HIIT等）"""
    __tablename__ = "workout_records"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # 基本信息
    workout_date = Column(Date, nullable=False, index=True)  # 训练日期
    start_time = Column(DateTime(timezone=True))  # 开始时间
    end_time = Column(DateTime(timezone=True))  # 结束时间
    
    # 运动类型
    workout_type = Column(String, nullable=False)  # running, swimming, cycling, hiit, cardio, strength, yoga, walking, hiking, other
    workout_name = Column(String)  # 训练名称（如"晨跑"、"有氧运动"）
    
    # 时长
    duration_seconds = Column(Integer)  # 持续时间（秒）
    moving_duration_seconds = Column(Integer)  # 移动时间（秒）
    
    # 距离与配速（适用于跑步、骑车、游泳）
    distance_meters = Column(Float)  # 距离（米）
    avg_pace_seconds_per_km = Column(Integer)  # 平均配速（秒/公里）
    best_pace_seconds_per_km = Column(Integer)  # 最佳配速（秒/公里）
    avg_speed_kmh = Column(Float)  # 平均速度（km/h）
    max_speed_kmh = Column(Float)  # 最大速度（km/h）
    
    # 心率数据
    avg_heart_rate = Column(Integer)  # 平均心率
    max_heart_rate = Column(Integer)  # 最大心率
    min_heart_rate = Column(Integer)  # 最低心率
    hr_zone_1_seconds = Column(Integer)  # 心率区间1时长（热身区）
    hr_zone_2_seconds = Column(Integer)  # 心率区间2时长（燃脂区）
    hr_zone_3_seconds = Column(Integer)  # 心率区间3时长（有氧区）
    hr_zone_4_seconds = Column(Integer)  # 心率区间4时长（阈值区）
    hr_zone_5_seconds = Column(Integer)  # 心率区间5时长（极限区）
    
    # 卡路里
    calories = Column(Integer)  # 消耗卡路里
    active_calories = Column(Integer)  # 活动卡路里
    
    # 跑步/步行特有
    steps = Column(Integer)  # 步数
    avg_stride_length_cm = Column(Float)  # 平均步幅（cm）
    avg_cadence = Column(Integer)  # 平均步频（步/分钟）
    max_cadence = Column(Integer)  # 最大步频
    
    # 骑车特有
    avg_power_watts = Column(Integer)  # 平均功率（瓦）
    max_power_watts = Column(Integer)  # 最大功率
    normalized_power_watts = Column(Integer)  # 标准化功率
    
    # 游泳特有
    pool_length_meters = Column(Integer)  # 泳池长度（米）
    laps = Column(Integer)  # 圈数
    strokes = Column(Integer)  # 划水次数
    avg_strokes_per_length = Column(Float)  # 每圈平均划水次数
    swim_style = Column(String)  # 泳姿（freestyle, backstroke, breaststroke, butterfly, mixed）
    
    # 高度数据（适用于跑步、骑车、徒步）
    elevation_gain_meters = Column(Float)  # 累计爬升（米）
    elevation_loss_meters = Column(Float)  # 累计下降（米）
    min_elevation_meters = Column(Float)  # 最低海拔
    max_elevation_meters = Column(Float)  # 最高海拔
    
    # 训练效果
    training_effect_aerobic = Column(Float)  # 有氧训练效果 (0-5)
    training_effect_anaerobic = Column(Float)  # 无氧训练效果 (0-5)
    vo2max = Column(Float)  # 最大摄氧量
    training_load = Column(Integer)  # 训练负荷
    
    # 感受与评估
    perceived_exertion = Column(Integer)  # 主观疲劳度 (1-10)
    feeling = Column(String)  # 感受（great, good, normal, tired, exhausted）
    notes = Column(Text)  # 备注
    
    # AI分析结果（JSON格式）
    ai_analysis = Column(Text)  # AI训练分析（JSON）
    
    # 数据来源
    source = Column(String, default="manual")  # manual, garmin, strava, apple_health
    external_id = Column(String)  # 外部ID（Garmin活动ID等）
    
    # 心率时间序列数据（JSON格式，用于绘图）
    heart_rate_data = Column(Text)  # 心率数据 [{"time": 0, "hr": 120}, ...]
    pace_data = Column(Text)  # 配速数据 [{"time": 0, "pace": 360}, ...]
    elevation_data = Column(Text)  # 海拔数据 [{"distance": 0, "elevation": 100}, ...]
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User", backref="workout_records")

