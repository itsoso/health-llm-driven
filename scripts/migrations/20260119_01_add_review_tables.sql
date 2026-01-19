-- 每日/周期复盘表
-- 创建日期: 2026-01-19

-- 每日复盘表
CREATE TABLE IF NOT EXISTS daily_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    review_date DATE NOT NULL,
    
    -- 睡眠数据
    sleep_score INTEGER,
    sleep_duration_hours REAL,
    sleep_quality VARCHAR(50),
    
    -- 运动数据
    workout_count INTEGER DEFAULT 0,
    workout_duration_minutes INTEGER DEFAULT 0,
    workout_calories INTEGER DEFAULT 0,
    workout_types VARCHAR(200),
    
    -- 小睡数据
    nap_count INTEGER DEFAULT 0,
    nap_duration_minutes INTEGER DEFAULT 0,
    
    -- 步数和活动
    steps INTEGER DEFAULT 0,
    active_calories INTEGER DEFAULT 0,
    
    -- 饮食数据
    meals_count INTEGER DEFAULT 0,
    total_calories_in INTEGER DEFAULT 0,
    total_protein REAL DEFAULT 0,
    total_carbs REAL DEFAULT 0,
    total_fat REAL DEFAULT 0,
    
    -- 饮水数据
    water_intake_ml INTEGER DEFAULT 0,
    water_goal_met BOOLEAN DEFAULT FALSE,
    
    -- 洗鼻数据
    nasal_wash_count INTEGER DEFAULT 0,
    nasal_wash_done BOOLEAN DEFAULT FALSE,
    
    -- 打卡数据
    checkin_completed INTEGER DEFAULT 0,
    checkin_total INTEGER DEFAULT 0,
    checkin_items TEXT,
    
    -- 补剂数据
    supplements_taken INTEGER DEFAULT 0,
    supplements_list TEXT,
    
    -- 身体状态
    body_battery_high INTEGER,
    body_battery_low INTEGER,
    stress_avg INTEGER,
    resting_hr INTEGER,
    
    -- 用户手动输入
    mood_score INTEGER,
    energy_score INTEGER,
    productivity_score INTEGER,
    highlights TEXT,
    challenges TEXT,
    learnings TEXT,
    gratitude TEXT,
    tomorrow_plan TEXT,
    summary TEXT,
    ai_summary TEXT,
    
    -- 元数据
    is_completed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, review_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_reviews_user_date ON daily_reviews(user_id, review_date);

-- 周期复盘表
CREATE TABLE IF NOT EXISTS period_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    period_type VARCHAR(20) NOT NULL,  -- daily, weekly, monthly, quarterly, yearly
    
    -- 周期范围
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    period_label VARCHAR(50),
    
    -- 睡眠统计
    avg_sleep_score REAL,
    avg_sleep_duration REAL,
    best_sleep_date DATE,
    worst_sleep_date DATE,
    
    -- 运动统计
    total_workouts INTEGER DEFAULT 0,
    total_workout_minutes INTEGER DEFAULT 0,
    total_workout_calories INTEGER DEFAULT 0,
    workout_days INTEGER DEFAULT 0,
    
    -- 步数统计
    total_steps INTEGER DEFAULT 0,
    avg_steps INTEGER DEFAULT 0,
    best_steps_date DATE,
    
    -- 饮食统计
    avg_calories_in INTEGER DEFAULT 0,
    avg_protein REAL DEFAULT 0,
    
    -- 饮水统计
    avg_water_intake INTEGER DEFAULT 0,
    water_goal_days INTEGER DEFAULT 0,
    
    -- 打卡统计
    avg_checkin_rate REAL,
    perfect_days INTEGER DEFAULT 0,
    
    -- 复盘完成情况
    review_days INTEGER DEFAULT 0,
    total_days INTEGER DEFAULT 0,
    
    -- 用户输入
    achievements TEXT,
    challenges TEXT,
    learnings TEXT,
    goals_review TEXT,
    next_period_goals TEXT,
    summary TEXT,
    ai_summary TEXT,
    
    -- 元数据
    is_completed BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(user_id, period_type, start_date, end_date)
);

CREATE INDEX IF NOT EXISTS idx_period_reviews_user_type ON period_reviews(user_id, period_type);
CREATE INDEX IF NOT EXISTS idx_period_reviews_dates ON period_reviews(start_date, end_date);
