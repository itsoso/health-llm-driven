-- 用户 API Key 系统数据库表 (PostgreSQL)
-- 创建时间: 2025-01-25
-- 功能: 允许外部系统访问用户健康数据和写入建议

-- 用户 API Key 表
CREATE TABLE IF NOT EXISTS user_api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 hash

    -- 权限范围
    scopes VARCHAR(255) DEFAULT 'read,write',

    -- 状态
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS ix_user_api_keys_api_key ON user_api_keys(api_key);

-- 外部健康建议表
CREATE TABLE IF NOT EXISTS external_recommendations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 建议类型
    category VARCHAR(50) NOT NULL,  -- exercise, diet, sleep, supplement, general

    -- 内容
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,

    -- 来源
    source_name VARCHAR(100) NOT NULL,  -- Browser-LLM-Driven, GPT Health, etc.
    source_api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE SET NULL,

    -- 时间
    recommendation_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_id ON external_recommendations(user_id);
CREATE INDEX IF NOT EXISTS ix_ext_rec_date ON external_recommendations(recommendation_date);
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_date ON external_recommendations(user_id, recommendation_date);
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_category ON external_recommendations(user_id, category);
