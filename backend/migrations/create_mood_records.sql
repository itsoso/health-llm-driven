-- 情绪追踪表
-- 创建时间: 2026-02-13

CREATE TABLE IF NOT EXISTS mood_records (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    record_date DATE NOT NULL,
    record_time TIMESTAMPTZ DEFAULT NOW(),
    mood_score INTEGER NOT NULL CHECK (mood_score >= 1 AND mood_score <= 5),
    mood_tags JSONB DEFAULT '[]',
    energy_level INTEGER CHECK (energy_level >= 1 AND energy_level <= 5),
    stress_level INTEGER CHECK (stress_level >= 1 AND stress_level <= 5),
    anxiety_level INTEGER CHECK (anxiety_level >= 1 AND anxiety_level <= 5),
    sleep_quality INTEGER CHECK (sleep_quality >= 1 AND sleep_quality <= 5),
    journal TEXT,
    triggers JSONB DEFAULT '[]',
    coping_methods JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMP
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_mood_user_date ON mood_records(user_id, record_date);
CREATE INDEX IF NOT EXISTS idx_mood_user_score ON mood_records(user_id, mood_score);
CREATE INDEX IF NOT EXISTS idx_mood_record_date ON mood_records(record_date);
