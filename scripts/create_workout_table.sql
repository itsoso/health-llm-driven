-- 创建运动训练记录表
-- 在服务器上执行: sqlite3 /opt/health-app/backend/health.db < scripts/create_workout_table.sql

CREATE TABLE IF NOT EXISTS workout_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    
    -- 基本信息
    workout_date DATE NOT NULL,
    start_time DATETIME,
    end_time DATETIME,
    
    -- 运动类型
    workout_type VARCHAR NOT NULL,  -- running, swimming, cycling, hiit, cardio, strength, yoga, walking, hiking, other
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

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_workout_records_user_id ON workout_records(user_id);
CREATE INDEX IF NOT EXISTS ix_workout_records_workout_date ON workout_records(workout_date);
CREATE INDEX IF NOT EXISTS ix_workout_records_workout_type ON workout_records(workout_type);
CREATE INDEX IF NOT EXISTS ix_workout_records_external_id ON workout_records(external_id);

