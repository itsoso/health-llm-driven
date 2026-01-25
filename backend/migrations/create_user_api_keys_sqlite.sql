-- 用户 API Key 系统数据库表 (SQLite 版本)
-- 创建时间: 2025-01-25
-- 功能: 允许外部系统访问用户健康数据和写入建议

-- 用户 API Key 表
CREATE TABLE IF NOT EXISTS user_api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 hash
    scopes VARCHAR(255) DEFAULT 'read,write',
    is_active INTEGER DEFAULT 1,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_user_api_keys_user_id ON user_api_keys(user_id);
CREATE INDEX IF NOT EXISTS ix_user_api_keys_api_key ON user_api_keys(api_key);

-- 外部健康建议表
CREATE TABLE IF NOT EXISTS external_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category VARCHAR(50) NOT NULL,  -- exercise, diet, sleep, supplement, general
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    source_name VARCHAR(100) NOT NULL,  -- Browser-LLM-Driven, GPT Health, etc.
    source_api_key_id INTEGER,
    recommendation_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (source_api_key_id) REFERENCES user_api_keys(id) ON DELETE SET NULL
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_id ON external_recommendations(user_id);
CREATE INDEX IF NOT EXISTS ix_ext_rec_date ON external_recommendations(recommendation_date);
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_date ON external_recommendations(user_id, recommendation_date);
CREATE INDEX IF NOT EXISTS ix_ext_rec_user_category ON external_recommendations(user_id, category);
