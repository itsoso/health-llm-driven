-- executor-v2 迁移脚本
-- 添加用户画像和打卡系统表
-- 执行日期: 2026-01-13

-- =====================================================
-- 1. 用户画像表
-- =====================================================
CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,

    -- 基本信息
    gender VARCHAR(10),
    birth_date DATE,
    height_cm REAL,
    blood_type VARCHAR(10),

    -- 身体数据
    current_weight_kg REAL,
    target_weight_kg REAL,
    body_fat_percentage REAL,
    muscle_mass_kg REAL,

    -- 健康目标
    target_steps INTEGER DEFAULT 8000,
    target_sleep_hours REAL DEFAULT 7.5,
    target_water_ml INTEGER DEFAULT 2000,
    target_calories_burn INTEGER,
    target_exercise_minutes INTEGER DEFAULT 30,

    -- 疾病历史 (JSON)
    chronic_conditions TEXT DEFAULT '[]',
    allergies TEXT DEFAULT '[]',
    family_history TEXT DEFAULT '[]',
    surgeries TEXT DEFAULT '[]',

    -- 正在服用的药物/补剂 (JSON)
    current_medications TEXT DEFAULT '[]',

    -- 生活习惯
    exercise_frequency VARCHAR(50),
    diet_preference VARCHAR(50),
    smoking_status VARCHAR(20),
    alcohol_consumption VARCHAR(20),

    -- 睡眠习惯
    usual_sleep_time VARCHAR(10),
    usual_wake_time VARCHAR(10),
    sleep_environment TEXT DEFAULT '{}',

    -- 工作环境
    work_type VARCHAR(50),
    work_hours_per_day REAL,
    sitting_hours_per_day REAL,

    -- 地理位置
    city VARCHAR(100),
    timezone VARCHAR(50) DEFAULT 'Asia/Shanghai',

    -- 设备信息 (JSON)
    devices TEXT DEFAULT '[]',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);

-- =====================================================
-- 2. 健康目标表
-- =====================================================
CREATE TABLE IF NOT EXISTS health_goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    -- 目标类型
    goal_type VARCHAR(50) NOT NULL,

    -- 目标详情
    name VARCHAR(200) NOT NULL,
    description TEXT,

    -- 目标值
    target_value REAL,
    current_value REAL,
    unit VARCHAR(20),

    -- 时间范围
    start_date DATE NOT NULL,
    target_date DATE,

    -- 状态
    status VARCHAR(20) DEFAULT 'active',
    priority INTEGER DEFAULT 1,

    -- AI建议 (JSON)
    ai_suggestions TEXT DEFAULT '[]',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_health_goals_user_id ON health_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_health_goals_status ON health_goals(status);

-- =====================================================
-- 3. 打卡模板表
-- =====================================================
CREATE TABLE IF NOT EXISTS checkin_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,

    -- 基本信息
    name VARCHAR(100) NOT NULL,
    description TEXT,
    icon VARCHAR(50) DEFAULT '✅',
    color VARCHAR(20) DEFAULT '#4f46e5',

    -- 分类
    category VARCHAR(50) NOT NULL,

    -- 计量配置
    unit VARCHAR(20) DEFAULT '次',
    default_target REAL DEFAULT 1,
    min_value REAL DEFAULT 0,
    max_value REAL,
    step_value REAL DEFAULT 1,

    -- 提醒配置
    reminder_enabled BOOLEAN DEFAULT 0,
    reminder_time TIME,
    reminder_days TEXT DEFAULT '[]',

    -- 频率配置
    frequency VARCHAR(20) DEFAULT 'daily',
    frequency_target INTEGER DEFAULT 1,

    -- 统计数据
    total_checkins INTEGER DEFAULT 0,
    total_value REAL DEFAULT 0,
    current_streak INTEGER DEFAULT 0,
    best_streak INTEGER DEFAULT 0,
    last_checkin_date DATE,

    -- 状态
    is_active BOOLEAN DEFAULT 1,
    is_archived BOOLEAN DEFAULT 0,
    sort_order INTEGER DEFAULT 0,

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkin_templates_user_id ON checkin_templates(user_id);
CREATE INDEX IF NOT EXISTS idx_checkin_templates_category ON checkin_templates(category);
CREATE INDEX IF NOT EXISTS idx_checkin_templates_is_active ON checkin_templates(is_active);

-- =====================================================
-- 4. 打卡记录表
-- =====================================================
CREATE TABLE IF NOT EXISTS checkin_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,

    -- 打卡日期和时间
    checkin_date DATE NOT NULL,
    checkin_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- 完成情况
    value REAL NOT NULL,
    target REAL,
    completion_rate REAL,

    -- 附加数据
    duration_seconds INTEGER,
    calories_burned REAL,
    heart_rate_avg INTEGER,

    -- 主观感受
    difficulty VARCHAR(20),
    mood_before VARCHAR(20),
    mood_after VARCHAR(20),
    energy_level INTEGER,

    -- 备注和标签
    notes TEXT,
    tags TEXT DEFAULT '[]',

    -- 位置信息
    location VARCHAR(200),
    latitude REAL,
    longitude REAL,

    -- 媒体附件 (JSON)
    photos TEXT DEFAULT '[]',

    -- 时间戳
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (template_id) REFERENCES checkin_templates(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_checkin_records_template_id ON checkin_records(template_id);
CREATE INDEX IF NOT EXISTS idx_checkin_records_user_id ON checkin_records(user_id);
CREATE INDEX IF NOT EXISTS idx_checkin_records_checkin_date ON checkin_records(checkin_date);
CREATE INDEX IF NOT EXISTS idx_checkin_records_user_date ON checkin_records(user_id, checkin_date);

-- =====================================================
-- 5. 记录迁移版本
-- =====================================================
INSERT INTO _migrations (version, description, applied_at)
VALUES ('012', 'Add user profile and checkin system tables', datetime('now'))
ON CONFLICT DO NOTHING;
