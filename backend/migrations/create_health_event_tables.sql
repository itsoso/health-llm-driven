-- 健康事件流表
-- 统一的事件中间层，用于自动化健康数据采集

-- 事件状态枚举
DO $$ BEGIN
    CREATE TYPE event_status AS ENUM ('pending', 'auto_confirmed', 'confirmed', 'corrected', 'dismissed');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- 健康事件表
CREATE TABLE IF NOT EXISTS health_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),

    event_type VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    source_device_id VARCHAR(100),

    raw_data JSONB,
    ai_inference JSONB,
    confidence FLOAT DEFAULT 0.0,

    status event_status NOT NULL DEFAULT 'pending',

    confirmed_data JSONB,
    target_record_type VARCHAR(50),
    target_record_id INTEGER,

    event_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_health_events_user_status ON health_events(user_id, status);
CREATE INDEX IF NOT EXISTS idx_health_events_user_type ON health_events(user_id, event_type);
CREATE INDEX IF NOT EXISTS idx_health_events_event_time ON health_events(user_id, event_time);

-- 事件来源表（设备/传感器注册）
CREATE TABLE IF NOT EXISTS event_sources (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),

    source_type VARCHAR(50) NOT NULL,
    device_id VARCHAR(100) NOT NULL,
    name VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,

    config JSONB DEFAULT '{}',
    auto_confirm_threshold FLOAT DEFAULT 0.8,
    is_active VARCHAR(10) DEFAULT 'true',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_event_sources_user ON event_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_event_sources_device ON event_sources(device_id);
