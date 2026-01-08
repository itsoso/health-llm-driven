-- ============================================
-- 健康管理系统 - 数据库初始化脚本
-- 执行方式: sqlite3 /opt/health-app/backend/health.db < scripts/init_database.sql
-- 
-- 注意: 此脚本用于首次部署，创建所有必要的表
-- 如果是升级现有数据库，请使用 migrations/ 目录下的迁移脚本
-- ============================================

-- ============================================
-- 用户相关表
-- ============================================

-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email VARCHAR UNIQUE,
    username VARCHAR UNIQUE,
    hashed_password VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    
    -- 微信小程序认证
    wechat_openid VARCHAR UNIQUE,
    wechat_unionid VARCHAR,
    wechat_session_key VARCHAR,
    
    -- 基础信息
    name VARCHAR NOT NULL,
    avatar_url VARCHAR,
    birth_date DATE,
    gender VARCHAR,
    phone VARCHAR,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);

CREATE INDEX IF NOT EXISTS ix_users_email ON users(email);
CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);
CREATE INDEX IF NOT EXISTS ix_users_wechat_openid ON users(wechat_openid);
CREATE INDEX IF NOT EXISTS ix_users_wechat_unionid ON users(wechat_unionid);

-- Garmin 凭证表
CREATE TABLE IF NOT EXISTS garmin_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    encrypted_email VARCHAR NOT NULL,
    encrypted_password VARCHAR NOT NULL,
    is_cn BOOLEAN DEFAULT FALSE,
    credentials_valid BOOLEAN DEFAULT TRUE,
    last_error VARCHAR,
    error_count INTEGER DEFAULT 0,
    last_sync DATETIME,
    sync_enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- ============================================
-- Garmin 数据表
-- ============================================

-- Garmin 每日数据
CREATE TABLE IF NOT EXISTS garmin_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    
    -- 睡眠数据
    sleep_score INTEGER,
    total_sleep_duration INTEGER,
    deep_sleep_duration INTEGER,
    light_sleep_duration INTEGER,
    rem_sleep_duration INTEGER,
    awake_duration INTEGER,
    nap_duration INTEGER,
    
    -- 心率数据
    resting_heart_rate INTEGER,
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    min_heart_rate INTEGER,
    
    -- HRV 数据
    hrv INTEGER,
    hrv_status VARCHAR,
    hrv_7day_avg FLOAT,
    
    -- 活动数据
    steps INTEGER,
    calories_burned INTEGER,
    active_calories INTEGER,
    bmr_calories INTEGER,
    active_minutes INTEGER,
    intensity_minutes_goal INTEGER,
    moderate_intensity_minutes INTEGER,
    vigorous_intensity_minutes INTEGER,
    
    -- 压力和身体电量
    stress_level INTEGER,
    avg_stress INTEGER,
    max_stress INTEGER,
    body_battery_most_charged INTEGER,
    body_battery_lowest INTEGER,
    
    -- 呼吸数据
    avg_respiration_awake FLOAT,
    avg_respiration_sleep FLOAT,
    lowest_respiration FLOAT,
    highest_respiration FLOAT,
    
    -- 血氧数据
    spo2_avg FLOAT,
    spo2_min FLOAT,
    spo2_max FLOAT,
    
    -- VO2 Max
    vo2max_running FLOAT,
    vo2max_cycling FLOAT,
    
    -- 楼层和距离
    floors_climbed INTEGER,
    floors_goal INTEGER,
    distance_meters FLOAT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_garmin_data_user_id ON garmin_data(user_id);
CREATE INDEX IF NOT EXISTS ix_garmin_data_record_date ON garmin_data(record_date);
CREATE UNIQUE INDEX IF NOT EXISTS ix_garmin_data_user_date ON garmin_data(user_id, record_date);

-- 心率采样数据 (用于心率曲线图)
CREATE TABLE IF NOT EXISTS heart_rate_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sample_date DATE NOT NULL,
    sample_time TIME NOT NULL,
    heart_rate INTEGER NOT NULL,
    source VARCHAR DEFAULT 'garmin',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_heart_rate_samples_user_id ON heart_rate_samples(user_id);
CREATE INDEX IF NOT EXISTS ix_heart_rate_samples_date ON heart_rate_samples(sample_date);

-- ============================================
-- 运动训练表
-- ============================================

CREATE TABLE IF NOT EXISTS workout_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    
    -- 基本信息
    workout_date DATE NOT NULL,
    start_time DATETIME,
    end_time DATETIME,
    
    -- 运动类型
    workout_type VARCHAR NOT NULL,
    workout_name VARCHAR,
    
    -- 时长
    duration_seconds INTEGER,
    moving_duration_seconds INTEGER,
    
    -- 距离与配速
    distance_meters FLOAT,
    avg_pace_seconds_per_km INTEGER,
    best_pace_seconds_per_km INTEGER,
    avg_speed_kmh FLOAT,
    max_speed_kmh FLOAT,
    
    -- 心率数据
    avg_heart_rate INTEGER,
    max_heart_rate INTEGER,
    min_heart_rate INTEGER,
    hr_zone_1_seconds INTEGER,
    hr_zone_2_seconds INTEGER,
    hr_zone_3_seconds INTEGER,
    hr_zone_4_seconds INTEGER,
    hr_zone_5_seconds INTEGER,
    
    -- 卡路里
    calories INTEGER,
    active_calories INTEGER,
    
    -- 跑步/步行特有
    steps INTEGER,
    avg_stride_length_cm FLOAT,
    avg_cadence INTEGER,
    max_cadence INTEGER,
    
    -- 骑车特有
    avg_power_watts INTEGER,
    max_power_watts INTEGER,
    normalized_power_watts INTEGER,
    
    -- 游泳特有
    pool_length_meters INTEGER,
    laps INTEGER,
    strokes INTEGER,
    avg_strokes_per_length FLOAT,
    swim_style VARCHAR,
    
    -- 高度数据
    elevation_gain_meters FLOAT,
    elevation_loss_meters FLOAT,
    min_elevation_meters FLOAT,
    max_elevation_meters FLOAT,
    
    -- 训练效果
    training_effect_aerobic FLOAT,
    training_effect_anaerobic FLOAT,
    vo2max FLOAT,
    training_load INTEGER,
    
    -- 感受与评估
    perceived_exertion INTEGER,
    feeling VARCHAR,
    notes TEXT,
    
    -- AI分析结果
    ai_analysis TEXT,
    
    -- 数据来源
    source VARCHAR DEFAULT 'manual',
    external_id VARCHAR,
    
    -- 时间序列数据（JSON格式）
    heart_rate_data TEXT,
    pace_data TEXT,
    elevation_data TEXT,
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_workout_records_user_id ON workout_records(user_id);
CREATE INDEX IF NOT EXISTS ix_workout_records_workout_date ON workout_records(workout_date);
CREATE INDEX IF NOT EXISTS ix_workout_records_workout_type ON workout_records(workout_type);
CREATE INDEX IF NOT EXISTS ix_workout_records_external_id ON workout_records(external_id);

-- ============================================
-- 日常记录表
-- ============================================

-- 锻炼记录 (简单打卡)
CREATE TABLE IF NOT EXISTS exercise_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    exercise_date DATE NOT NULL,
    exercise_type VARCHAR NOT NULL,
    duration_minutes INTEGER,
    intensity VARCHAR,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_exercise_records_user_id ON exercise_records(user_id);
CREATE INDEX IF NOT EXISTS ix_exercise_records_date ON exercise_records(exercise_date);

-- 饮食记录
CREATE TABLE IF NOT EXISTS diet_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    meal_date DATE NOT NULL,
    meal_time TIME,
    meal_type VARCHAR NOT NULL,
    food_name VARCHAR,
    food_items TEXT,
    portion_size VARCHAR,
    calories INTEGER,
    protein_grams FLOAT,
    carbs_grams FLOAT,
    fat_grams FLOAT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_diet_records_user_id ON diet_records(user_id);
CREATE INDEX IF NOT EXISTS ix_diet_records_date ON diet_records(meal_date);

-- 饮水记录
CREATE TABLE IF NOT EXISTS water_intakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    intake_date DATE NOT NULL,
    intake_time TIME,
    amount_ml INTEGER NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_water_intakes_user_id ON water_intakes(user_id);
CREATE INDEX IF NOT EXISTS ix_water_intakes_date ON water_intakes(intake_date);

-- 补剂摄入记录
CREATE TABLE IF NOT EXISTS supplement_intakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    intake_date DATE NOT NULL,
    intake_time TIME,
    supplement_name VARCHAR NOT NULL,
    dosage VARCHAR,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_supplement_intakes_user_id ON supplement_intakes(user_id);
CREATE INDEX IF NOT EXISTS ix_supplement_intakes_date ON supplement_intakes(intake_date);

-- 户外活动记录
CREATE TABLE IF NOT EXISTS outdoor_activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    activity_date DATE NOT NULL,
    start_time TIME,
    end_time TIME,
    activity_type VARCHAR,
    duration_minutes INTEGER,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_outdoor_activities_user_id ON outdoor_activities(user_id);
CREATE INDEX IF NOT EXISTS ix_outdoor_activities_date ON outdoor_activities(activity_date);

-- ============================================
-- 健康追踪表
-- ============================================

-- 体重记录
CREATE TABLE IF NOT EXISTS weight_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    weight_kg FLOAT NOT NULL,
    body_fat_percentage FLOAT,
    muscle_mass_kg FLOAT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_weight_records_user_id ON weight_records(user_id);
CREATE INDEX IF NOT EXISTS ix_weight_records_date ON weight_records(record_date);

-- 血压记录
CREATE TABLE IF NOT EXISTS blood_pressure_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    record_time TIME,
    systolic INTEGER NOT NULL,
    diastolic INTEGER NOT NULL,
    pulse INTEGER,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_blood_pressure_records_user_id ON blood_pressure_records(user_id);
CREATE INDEX IF NOT EXISTS ix_blood_pressure_records_date ON blood_pressure_records(record_date);

-- 基础健康数据 (身高、BMI等)
CREATE TABLE IF NOT EXISTS basic_health_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    height_cm FLOAT,
    weight_kg FLOAT,
    bmi FLOAT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_basic_health_data_user_id ON basic_health_data(user_id);
CREATE INDEX IF NOT EXISTS ix_basic_health_data_date ON basic_health_data(record_date);

-- 健康打卡 (每日症状记录，如鼻炎追踪)
CREATE TABLE IF NOT EXISTS health_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    checkin_date DATE NOT NULL,
    checkin_type VARCHAR NOT NULL,
    severity INTEGER,
    symptoms TEXT,
    triggers TEXT,
    medication_taken TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_health_checkins_user_id ON health_checkins(user_id);
CREATE INDEX IF NOT EXISTS ix_health_checkins_date ON health_checkins(checkin_date);
CREATE INDEX IF NOT EXISTS ix_health_checkins_type ON health_checkins(checkin_type);

-- 疾病记录
CREATE TABLE IF NOT EXISTS disease_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    disease_name VARCHAR NOT NULL,
    diagnosis_date DATE,
    status VARCHAR,
    doctor VARCHAR,
    hospital VARCHAR,
    treatment TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_disease_records_user_id ON disease_records(user_id);

-- ============================================
-- 补剂和习惯管理表
-- ============================================

-- 补剂定义
CREATE TABLE IF NOT EXISTS supplement_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    brand VARCHAR,
    dosage VARCHAR,
    frequency VARCHAR,
    time_of_day VARCHAR,
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_supplement_definitions_user_id ON supplement_definitions(user_id);

-- 补剂服用记录
CREATE TABLE IF NOT EXISTS supplement_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    supplement_id INTEGER NOT NULL,
    taken_date DATE NOT NULL,
    taken_time TIME,
    dosage VARCHAR,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (supplement_id) REFERENCES supplement_definitions(id)
);

CREATE INDEX IF NOT EXISTS ix_supplement_records_user_id ON supplement_records(user_id);
CREATE INDEX IF NOT EXISTS ix_supplement_records_date ON supplement_records(taken_date);

-- 习惯定义
CREATE TABLE IF NOT EXISTS habit_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR NOT NULL,
    description TEXT,
    category VARCHAR,
    frequency VARCHAR,
    target_value FLOAT,
    unit VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_habit_definitions_user_id ON habit_definitions(user_id);

-- 习惯完成记录
CREATE TABLE IF NOT EXISTS habit_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    habit_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    completed BOOLEAN DEFAULT FALSE,
    value FLOAT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (habit_id) REFERENCES habit_definitions(id)
);

CREATE INDEX IF NOT EXISTS ix_habit_records_user_id ON habit_records(user_id);
CREATE INDEX IF NOT EXISTS ix_habit_records_date ON habit_records(record_date);

-- ============================================
-- 目标管理表
-- ============================================

CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title VARCHAR NOT NULL,
    description TEXT,
    category VARCHAR NOT NULL,
    goal_type VARCHAR NOT NULL,
    target_value FLOAT,
    current_value FLOAT DEFAULT 0,
    unit VARCHAR,
    start_date DATE,
    end_date DATE,
    status VARCHAR DEFAULT 'active',
    priority INTEGER DEFAULT 3,
    parent_goal_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (parent_goal_id) REFERENCES goals(id)
);

CREATE INDEX IF NOT EXISTS ix_goals_user_id ON goals(user_id);
CREATE INDEX IF NOT EXISTS ix_goals_category ON goals(category);
CREATE INDEX IF NOT EXISTS ix_goals_status ON goals(status);

-- 目标进度记录
CREATE TABLE IF NOT EXISTS goal_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    value FLOAT NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (goal_id) REFERENCES goals(id)
);

CREATE INDEX IF NOT EXISTS ix_goal_progress_goal_id ON goal_progress(goal_id);
CREATE INDEX IF NOT EXISTS ix_goal_progress_date ON goal_progress(record_date);

-- ============================================
-- 体检报告表
-- ============================================

CREATE TABLE IF NOT EXISTS medical_exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    exam_date DATE NOT NULL,
    exam_type VARCHAR,
    hospital VARCHAR,
    department VARCHAR,
    doctor VARCHAR,
    summary TEXT,
    recommendations TEXT,
    pdf_path VARCHAR,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_medical_exams_user_id ON medical_exams(user_id);
CREATE INDEX IF NOT EXISTS ix_medical_exams_date ON medical_exams(exam_date);

-- 体检项目详情
CREATE TABLE IF NOT EXISTS medical_exam_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id INTEGER NOT NULL,
    item_name VARCHAR NOT NULL,
    item_value VARCHAR,
    unit VARCHAR,
    reference_range VARCHAR,
    status VARCHAR,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (exam_id) REFERENCES medical_exams(id)
);

CREATE INDEX IF NOT EXISTS ix_medical_exam_items_exam_id ON medical_exam_items(exam_id);

-- ============================================
-- AI 分析缓存表
-- ============================================

-- 每日建议缓存
CREATE TABLE IF NOT EXISTS daily_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    recommendation_date DATE NOT NULL,
    analysis_date DATE,
    sleep_analysis TEXT,
    activity_analysis TEXT,
    stress_analysis TEXT,
    overall_summary TEXT,
    goals TEXT,
    tips TEXT,
    data_snapshot TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_daily_recommendations_user_id ON daily_recommendations(user_id);
CREATE INDEX IF NOT EXISTS ix_daily_recommendations_date ON daily_recommendations(recommendation_date);
CREATE UNIQUE INDEX IF NOT EXISTS ix_daily_recommendations_user_date ON daily_recommendations(user_id, recommendation_date);

-- 健康分析缓存
CREATE TABLE IF NOT EXISTS health_analysis_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    analysis_type VARCHAR NOT NULL,
    analysis_date DATE NOT NULL,
    input_hash VARCHAR,
    result TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS ix_health_analysis_cache_user_id ON health_analysis_cache(user_id);
CREATE INDEX IF NOT EXISTS ix_health_analysis_cache_type ON health_analysis_cache(analysis_type);

-- ============================================
-- 初始化完成
-- ============================================
-- 提示: 运行此脚本后，请继续运行以下命令创建第一个管理员用户:
-- cd backend && source venv/bin/activate
-- python scripts/create_user.py --email admin@example.com --password yourpassword --admin

