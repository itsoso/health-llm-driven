-- 013_add_disease_tracking.sql
-- 增强版疾病追踪表

-- 创建 disease_templates 表（疾病管理模板）
CREATE TABLE IF NOT EXISTS disease_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    category VARCHAR(255) NOT NULL,
    icon VARCHAR(255),
    symptoms JSON DEFAULT '[]',
    triggers JSON DEFAULT '[]',
    environment_sensitive BOOLEAN DEFAULT FALSE,
    sensitive_factors JSON DEFAULT '[]',
    daily_tips JSON DEFAULT '[]',
    medication_types JSON DEFAULT '[]',
    prevention_tips JSON DEFAULT '[]',
    tracking_frequency VARCHAR(255) DEFAULT 'daily',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_disease_templates_name ON disease_templates (name);
CREATE INDEX IF NOT EXISTS idx_disease_templates_category ON disease_templates (category);

-- 创建 user_disease_profiles 表（用户疾病档案）
CREATE TABLE IF NOT EXISTS user_disease_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    template_id INTEGER,
    disease_name VARCHAR(255) NOT NULL,
    diagnosis_date DATE,
    severity VARCHAR(255) DEFAULT 'moderate',
    status VARCHAR(255) DEFAULT 'chronic',
    personal_triggers JSON DEFAULT '[]',
    personal_symptoms JSON DEFAULT '[]',
    current_medications JSON DEFAULT '[]',
    tracking_enabled BOOLEAN DEFAULT TRUE,
    reminder_time TIME,
    target_symptom_days INTEGER DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (template_id) REFERENCES disease_templates (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_disease_profiles_user_id ON user_disease_profiles (user_id);
CREATE INDEX IF NOT EXISTS idx_user_disease_profiles_disease_name ON user_disease_profiles (disease_name);

-- 创建 symptom_logs 表（症状日志）
CREATE TABLE IF NOT EXISTS symptom_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    disease_profile_id INTEGER NOT NULL,
    log_date DATE NOT NULL,
    log_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    overall_severity INTEGER DEFAULT 0,
    symptoms JSON DEFAULT '[]',
    triggers JSON DEFAULT '[]',
    medications_taken JSON DEFAULT '[]',
    treatments JSON DEFAULT '[]',
    weather_data JSON DEFAULT '{}',
    air_quality_data JSON DEFAULT '{}',
    sleep_hours REAL,
    stress_level INTEGER,
    diet_notes VARCHAR(255),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (disease_profile_id) REFERENCES user_disease_profiles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_symptom_logs_user_id ON symptom_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_symptom_logs_date ON symptom_logs (log_date);
CREATE INDEX IF NOT EXISTS idx_symptom_logs_profile ON symptom_logs (disease_profile_id);

-- 创建 vision_records 表（视力记录）
CREATE TABLE IF NOT EXISTS vision_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    left_eye_naked REAL,
    right_eye_naked REAL,
    left_eye_corrected REAL,
    right_eye_corrected REAL,
    left_eye_sphere REAL,
    right_eye_sphere REAL,
    left_eye_cylinder REAL,
    right_eye_cylinder REAL,
    left_eye_axis INTEGER,
    right_eye_axis INTEGER,
    left_eye_axial REAL,
    right_eye_axial REAL,
    exam_type VARCHAR(255),
    exam_location VARCHAR(255),
    doctor_name VARCHAR(255),
    interventions JSON DEFAULT '[]',
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_vision_records_user_id ON vision_records (user_id);
CREATE INDEX IF NOT EXISTS idx_vision_records_date ON vision_records (record_date);

-- 创建 daily_eye_habits 表（每日用眼习惯）
CREATE TABLE IF NOT EXISTS daily_eye_habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    record_date DATE NOT NULL,
    outdoor_minutes INTEGER DEFAULT 0,
    outdoor_sunlight BOOLEAN DEFAULT FALSE,
    screen_minutes INTEGER DEFAULT 0,
    reading_minutes INTEGER DEFAULT 0,
    homework_minutes INTEGER DEFAULT 0,
    eye_rest_count INTEGER DEFAULT 0,
    lighting_quality VARCHAR(255),
    reading_distance VARCHAR(255),
    posture VARCHAR(255),
    interventions_done JSON DEFAULT '[]',
    eye_fatigue INTEGER DEFAULT 0,
    dry_eyes BOOLEAN DEFAULT FALSE,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_daily_eye_habits_user_id ON daily_eye_habits (user_id);
CREATE INDEX IF NOT EXISTS idx_daily_eye_habits_date ON daily_eye_habits (record_date);
