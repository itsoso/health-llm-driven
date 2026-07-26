"""日常健康记录模型"""
from sqlalchemy import CheckConstraint, Column, Integer, BigInteger, Float, String, DateTime, Date, ForeignKey, Text, Time, Boolean, Index, UniqueConstraint, text
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
from app.models.agent_audit_log import JSONColumn


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
    hrv_status = Column(String)  # HRV状态 (balanced, unbalanced, low)
    hrv_7day_avg = Column(Float)  # 7天平均HRV

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
    body_battery_current = Column(Integer)  # 当前实时电量

    # 压力数据
    stress_level = Column(Integer)  # 压力水平 (0-100)

    # 步数
    steps = Column(Integer)  # 步数

    # 活动数据
    calories_burned = Column(Integer)  # 消耗卡路里（总消耗）
    active_calories = Column(Integer)  # 活动卡路里（运动消耗）
    bmr_calories = Column(Integer)  # 基础代谢卡路里（静息消耗）
    active_minutes = Column(Integer)  # 活动分钟数

    # 强度活动时间（周目标）
    intensity_minutes_goal = Column(Integer)  # 强度活动时间周目标（分钟）
    moderate_intensity_minutes = Column(Integer)  # 中等强度活动时间
    vigorous_intensity_minutes = Column(Integer)  # 高强度活动时间

    # 呼吸数据
    avg_respiration_awake = Column(Float)  # 清醒平均呼吸频率 (brpm)
    avg_respiration_sleep = Column(Float)  # 睡眠平均呼吸频率 (brpm)
    lowest_respiration = Column(Float)  # 最低呼吸频率
    highest_respiration = Column(Float)  # 最高呼吸频率
    respiratory_rate_min = Column(Float)  # HealthKit RespiratoryRate 当日最低
    respiratory_rate_max = Column(Float)  # HealthKit RespiratoryRate 当日最高

    # 体温(基线偏移,Apple Watch / Oura 给出的不是绝对体温)
    body_temp_deviation_c = Column(Float)

    # 血氧饱和度
    spo2_avg = Column(Float)  # 平均血氧饱和度 (%)
    spo2_min = Column(Float)  # 最低血氧饱和度
    spo2_max = Column(Float)  # 最高血氧饱和度

    # VO2 Max（最大摄氧量）
    vo2max_running = Column(Float)  # 跑步最大摄氧量
    vo2max_cycling = Column(Float)  # 骑行最大摄氧量

    # 楼层
    floors_climbed = Column(Integer)  # 爬楼层数
    floors_goal = Column(Integer)  # 楼层目标

    # 距离
    distance_meters = Column(Float)  # 总距离（米）

    # Garmin Training Readiness / Status (P1a)
    training_readiness_score = Column(Integer)  # 0-100
    training_readiness_level = Column(String)  # poor/low/moderate/high/prime
    training_readiness_factors = Column(JSONColumn)  # 各因子分解 JSON
    training_status = Column(String)  # productive/maintaining/detraining/overreaching/peaking/recovery/unproductive
    training_status_feedback = Column(Text)
    acute_load = Column(Float)
    load_ratio = Column(Float)  # ACWR

    # 其他 Garmin 指标 (P1a)
    endurance_score = Column(Integer)
    hill_score = Column(Integer)
    race_predictions = Column(JSONColumn)  # {5k, 10k, half_marathon, marathon} seconds
    hydration_ml = Column(Integer)
    vo2max_fitness_age = Column(Integer)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 数据来源(garmin / apple-watch / ringconn / oura / withings-app / manual / unknown)。
    # HealthKit 同步进来的多源数据按 sourceName bundle id 细分;同 (user, date) 允许多 source 共存。
    data_source = Column(String(30), nullable=False, default="garmin", server_default="garmin", index=True)

    user = relationship("User", backref="garmin_records")

    # 复合索引:优化按用户和日期查询;并发起 (user_id, record_date, data_source) 唯一约束让多源 upsert 不互相覆盖
    __table_args__ = (
        Index('idx_garmin_user_date', 'user_id', 'record_date'),
        Index('idx_garmin_user_date_source', 'user_id', 'record_date', 'data_source', unique=True),
    )


class ExerciseRecord(Base):
    """日常锻炼记录（Garmin未记录部分）"""
    __tablename__ = "exercise_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    exercise_type = Column(String, nullable=False)  # 运动类型
    duration = Column(Integer)  # 持续时间 (分钟) — 跑步/瑜伽 等粗粒度场景
    duration_seconds = Column(Integer)  # 持续时间 (秒) — 倒立/平板支撑 等需要亚分钟精度的场景
    intensity = Column(String)  # 强度（低/中/高）
    calories_burned = Column(Integer)  # 消耗卡路里
    reps = Column(Integer)  # 次数（如俯卧撑30个）
    sets = Column(Integer)  # 组数
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
    food_id = Column(String(120), nullable=True)  # 结构化食物库 ID,用于追溯营养来源
    source = Column(String(80), nullable=True)  # 营养数据来源,如 china_food_composition/fdc/manual
    quantity = Column(Float)  # 数量
    unit = Column(String)  # 单位（g/ml/份）

    # 营养信息
    calories = Column(Float)  # 卡路里
    protein = Column(Float)  # 蛋白质 (g)
    carbs = Column(Float)  # 碳水化合物 (g)
    fat = Column(Float)  # 脂肪 (g)
    fiber = Column(Float)  # 纤维 (g)
    alcohol_units = Column(Float, nullable=True)  # 酒精标准杯数 (1 unit ≈ 14g 纯酒精)

    # 图片和AI识别
    image_url = Column(String, nullable=True)  # 食物图片URL
    client_action_id = Column(String(160), nullable=True)
    ai_recognized = Column(Boolean, default=False)  # 是否AI识别
    ai_confidence = Column(Float, nullable=True)  # AI识别置信度
    ai_raw_result = Column(Text, nullable=True)  # AI识别原始结果(JSON)

    notes = Column(Text)  # 备注
    health_tips = Column(Text, nullable=True)  # AI健康提示

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="diet_records")
    photo_assets = relationship(
        "DietPhotoAsset",
        back_populates="diet_record",
        foreign_keys="DietPhotoAsset.diet_record_id",
        order_by="DietPhotoAsset.ordinal",
    )

    # 复合索引：优化按用户、日期和餐次查询
    __table_args__ = (
        CheckConstraint(
            "image_url IS NULL OR image_url NOT LIKE '%?%'",
            name="ck_diet_records_image_url_canonical",
        ),
        Index('idx_diet_user_date', 'user_id', 'record_date'),
        Index('idx_diet_user_date_meal', 'user_id', 'record_date', 'meal_type'),
        Index('idx_diet_food_id', 'food_id'),
        Index(
            'uq_diet_records_user_client_action_id',
            'user_id',
            'client_action_id',
            unique=True,
            postgresql_where=text('client_action_id IS NOT NULL'),
            sqlite_where=text('client_action_id IS NOT NULL'),
        ),
    )


class DietPhotoDraft(Base):
    """Owner-scoped, short-lived photo pending manual diet confirmation."""
    __tablename__ = "diet_photo_drafts"

    token = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # Contextual Agent captures use the originating user message as the
    # session boundary.  Nullable keeps direct REST photo drafts compatible.
    source_message_id = Column(Integer, nullable=True)
    image_url = Column(String, nullable=True)
    image_type = Column(String(20), nullable=False)
    recognition_result = Column(JSONColumn, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_record_id = Column(
        Integer,
        ForeignKey("diet_records.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(
            "image_url IS NULL OR image_url NOT LIKE '%?%'",
            name="ck_diet_photo_drafts_image_url_canonical",
        ),
        CheckConstraint(
            "status IN ('pending', 'consumed', 'cancelled', 'expired')",
            name="ck_diet_photo_drafts_status",
        ),
        Index("idx_diet_photo_drafts_user_status", "user_id", "status"),
        Index("idx_diet_photo_drafts_expires_at", "expires_at"),
        Index(
            "uq_diet_photo_drafts_user_source_message",
            "user_id",
            "source_message_id",
            unique=True,
            postgresql_where=text("source_message_id IS NOT NULL"),
            sqlite_where=text("source_message_id IS NOT NULL"),
        ),
    )


class DietPhotoAsset(Base):
    """Authoritative private photo ownership for a diet record or pending draft.

    ``storage_key`` is always a canonical owner-scoped upload path.  Capability
    URLs are generated only while building an API response and must never be
    persisted here.
    """
    __tablename__ = "diet_photo_assets"

    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    diet_record_id = Column(
        Integer,
        ForeignKey("diet_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    photo_draft_token = Column(
        String(64),
        ForeignKey("diet_photo_drafts.token", ondelete="SET NULL"),
        nullable=True,
    )
    storage_key = Column(String(1024), nullable=False)
    content_sha256 = Column(String(64), nullable=False)
    media_type = Column(String(40), nullable=False)
    origin = Column(String(40), nullable=False)
    origin_message_id = Column(Integer, nullable=True)
    ordinal = Column(Integer, nullable=False, default=0)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    captured_timezone = Column(String(64), nullable=True)
    classification = Column(String(24), nullable=False)
    recognition_confidence = Column(Float, nullable=True)
    intent_decision = Column(String(24), nullable=False)
    recognition_snapshot = Column(JSONColumn, nullable=True)
    lifecycle = Column(String(24), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attached_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    diet_record = relationship(
        "DietRecord",
        back_populates="photo_assets",
        foreign_keys=[diet_record_id],
    )

    __table_args__ = (
        CheckConstraint("storage_key NOT LIKE '%?%'", name="ck_diet_photo_assets_storage_key_canonical"),
        CheckConstraint("ordinal >= 0", name="ck_diet_photo_assets_ordinal"),
        CheckConstraint(
            "classification IN ('food', 'non_food', 'unknown')",
            name="ck_diet_photo_assets_classification",
        ),
        CheckConstraint(
            "intent_decision IN ('auto_record', 'confirm', 'analyze_only')",
            name="ck_diet_photo_assets_intent_decision",
        ),
        CheckConstraint(
            "lifecycle IN ('pending', 'attached', 'deleted')",
            name="ck_diet_photo_assets_lifecycle",
        ),
        UniqueConstraint(
            "user_id",
            "origin_message_id",
            "ordinal",
            name="uq_diet_photo_assets_user_origin_ordinal",
        ),
        UniqueConstraint(
            "diet_record_id",
            "ordinal",
            name="uq_diet_photo_assets_record_ordinal",
        ),
        Index("idx_diet_photo_assets_user_record", "user_id", "diet_record_id", "ordinal"),
        Index("idx_diet_photo_assets_draft", "photo_draft_token"),
        Index("idx_diet_photo_assets_user_hash", "user_id", "content_sha256", "created_at"),
    )


class WaterIntake(Base):
    """日常饮水记录"""
    __tablename__ = "water_intakes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False, index=True)
    intake_time = Column(DateTime(timezone=True))  # 饮水时间
    amount_ml = Column(Integer, nullable=False, name="amount_ml")  # 饮水量 (ml) - 匹配数据库字段名
    drink_type = Column(String)  # 饮品类型（水、茶、咖啡等）
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="water_intakes")

    # 为了兼容性，添加 amount 属性作为 amount_ml 的别名
    @property
    def amount(self):
        return self.amount_ml

    @amount.setter
    def amount(self, value):
        self.amount_ml = value

    # 复合索引：优化按用户和日期查询
    __table_args__ = (
        Index('idx_water_user_date', 'user_id', 'record_date'),
    )


class SupplementIntake(Base):
    """补剂摄入记录"""
    __tablename__ = "supplement_intakes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    record_date = Column(Date, nullable=False, index=True)
    supplement_name = Column(String, nullable=False)  # 补剂名称
    intake_time = Column(Time)  # 摄入时间
    dosage = Column(Float)  # 剂量
    unit = Column(String)  # 单位（mg/g/片/粒）
    notes = Column(Text)  # 备注

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="supplement_intakes")

    # 复合索引：优化按用户和日期查询
    __table_args__ = (
        Index('idx_supplement_user_date', 'user_id', 'record_date'),
    )


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

    # 复合索引：按用户、日期和时间快速查询
    __table_args__ = (
        Index('idx_hr_user_date', 'user_id', 'record_date'),
        Index('idx_hr_user_date_time', 'user_id', 'record_date', 'sample_time'),
    )


class SpO2Sample(Base):
    """睡眠期间血氧采样数据（每分钟一个点，每晚约 400-500 个点）"""
    __tablename__ = "spo2_samples"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    record_date = Column(Date, nullable=False)
    sample_time = Column(Time, nullable=False)
    spo2_value = Column(Integer, nullable=False)
    epoch_ms = Column(BigInteger)

    source = Column(String, default="garmin")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="spo2_samples")

    __table_args__ = (
        Index('idx_spo2_user_date', 'user_id', 'record_date'),
        Index('idx_spo2_user_date_time', 'user_id', 'record_date', 'sample_time'),
        # 逐分钟去重的 DB 兜底: 同一 (用户, 日期, 分钟, 来源) 至多一行。
        # 没有它时, HealthKit 与 garmin 采集器都用「按 (user,date,source) 删后插」+
        # 「同源导入串行」的假设保幂等; 但同 (user, source) 两个并发导入会双删双插 →
        # 重复分钟行 → 虚高 spo2_below_90_pct / spo2_odi → 污染夜间低氧 CRITICAL 的
        # 「持续负荷」佐证 (见 vitals.spo2_min_nocturnal_severe)。约束含 source, 故多设备
        # 同日同分钟 (apple-watch vs ringconn vs garmin) 是不同槽, 正常并存。
        UniqueConstraint(
            'user_id', 'record_date', 'sample_time', 'source',
            name='uq_spo2_user_date_time_source',
        ),
    )


class SleepLevelInterval(Base):
    """睡眠阶段时间段（deep/light/rem/awake，每晚约 30-60 段）"""
    __tablename__ = "sleep_level_intervals"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_date = Column(Date, nullable=False)
    start_epoch_ms = Column(BigInteger, nullable=False)
    end_epoch_ms = Column(BigInteger, nullable=False)
    activity_level = Column(String(10), nullable=False)  # deep, light, rem, awake
    source = Column(String, default="garmin")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="sleep_level_intervals")

    __table_args__ = (
        Index('idx_sleep_level_user_date', 'user_id', 'record_date'),
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
    post_workout_analysis = Column(Text)  # 运动后科学分析（JSON）

    # 数据来源
    source = Column(String, default="manual")  # manual, garmin, strava, apple_health
    external_id = Column(String)  # 外部ID（Garmin活动ID等）

    # 心率时间序列数据（JSON格式，用于绘图）
    heart_rate_data = Column(Text)  # 心率数据 [{"time": 0, "hr": 120}, ...]
    pace_data = Column(Text)  # 配速数据 [{"time": 0, "pace": 360}, ...]
    elevation_data = Column(Text)  # 海拔数据 [{"distance": 0, "elevation": 100}, ...]
    route_data = Column(Text)  # GPS路线数据 [{"lat": 39.9, "lng": 116.4, "elevation": 100, "time": 0}, ...]
    lap_data = Column(Text)  # 计圈数据 [{"lap": 1, "distance": 1000, "duration": 300, "avg_hr": 150, "avg_pace": 300}, ...]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="workout_records")

    # 复合索引：优化按用户、日期和类型查询
    __table_args__ = (
        Index('idx_workout_user_date', 'user_id', 'workout_date'),
        Index('idx_workout_user_type', 'user_id', 'workout_type'),
        Index('idx_workout_source_external', 'source', 'external_id'),
        Index('uix_workout_user_external', 'user_id', 'external_id',
              unique=True, postgresql_where=text("external_id IS NOT NULL")),
    )


class WorkoutAnalysisResult(Base):
    """运动分析结果（支持多个分析关联到同一次运动）"""
    __tablename__ = "workout_analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    workout_id = Column(Integer, ForeignKey("workout_records.id"), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    source = Column(String(50), nullable=False)  # "multi_model", "openai", "rule_engine"
    status = Column(String(20))  # "completed", "partial", "timeout", "error"
    aggregation = Column(Text)  # 综合分析结论
    model_results = Column(Text)  # 各模型独立结果 (JSON array)
    prompt = Column(Text)  # 发送给AI的prompt
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workout = relationship("WorkoutRecord", backref="analysis_results")
