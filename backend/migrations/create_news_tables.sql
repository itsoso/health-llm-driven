-- 资讯系统数据库表 (PostgreSQL)
-- 创建时间: 2025-01-25

-- 资讯文章表
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,

    -- 来源标识
    source_batch_id VARCHAR(100) NOT NULL UNIQUE,
    source_type VARCHAR(50) NOT NULL,  -- chatlog_analysis, custom_prompt, daily_recap

    -- 文章内容
    title VARCHAR(500) NOT NULL,
    summary TEXT,
    content TEXT NOT NULL,

    -- 元数据 (JSON 数组格式存储)
    tags TEXT,
    topics TEXT,
    key_people TEXT,
    source_group VARCHAR(200),

    -- LLM 信息
    llm_models TEXT,
    aggregator_model VARCHAR(100),

    -- 状态
    is_published BOOLEAN DEFAULT TRUE,
    is_pinned BOOLEAN DEFAULT FALSE,
    view_count INTEGER DEFAULT 0,

    -- 时间
    source_created_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_news_articles_source_batch_id ON news_articles(source_batch_id);
CREATE INDEX IF NOT EXISTS ix_news_published_created ON news_articles(is_published, created_at);

-- 资讯 API 密钥表
CREATE TABLE IF NOT EXISTS news_api_keys (
    id SERIAL PRIMARY KEY,

    name VARCHAR(100) NOT NULL,
    api_key VARCHAR(64) NOT NULL UNIQUE,  -- SHA256 hash

    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP WITH TIME ZONE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 创建索引
CREATE INDEX IF NOT EXISTS ix_news_api_keys_api_key ON news_api_keys(api_key);
