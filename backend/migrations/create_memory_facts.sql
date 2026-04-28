-- Memory Fact — LLM Wiki v2 风格的事实级记忆
-- 三元组 (subject, predicate, object_value) + confidence + supersession + 遗忘曲线
-- 支持 working / episodic / semantic / procedural 四层

CREATE TABLE IF NOT EXISTS memory_facts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    tier VARCHAR(20) NOT NULL,

    subject VARCHAR(200) NOT NULL,
    predicate VARCHAR(80) NOT NULL,
    object_value TEXT NOT NULL,
    object_unit VARCHAR(20),

    confidence FLOAT NOT NULL DEFAULT 0.5,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb,

    last_reinforced_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    reinforcement_count INTEGER NOT NULL DEFAULT 1,
    decay_rate FLOAT NOT NULL DEFAULT 0.02,

    supersedes_id INTEGER REFERENCES memory_facts(id) ON DELETE SET NULL,
    superseded_by_id INTEGER REFERENCES memory_facts(id) ON DELETE SET NULL,
    superseded_at TIMESTAMP WITH TIME ZONE,

    is_private BOOLEAN NOT NULL DEFAULT true,
    is_sensitive BOOLEAN NOT NULL DEFAULT false,

    tags JSONB DEFAULT '[]'::jsonb,

    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- 索引
CREATE INDEX IF NOT EXISTS ix_memory_facts_user_id ON memory_facts(user_id);
CREATE INDEX IF NOT EXISTS ix_memory_facts_tier ON memory_facts(tier);
CREATE INDEX IF NOT EXISTS ix_memory_facts_predicate ON memory_facts(predicate);
CREATE INDEX IF NOT EXISTS idx_memory_user_tier ON memory_facts(user_id, tier);
CREATE INDEX IF NOT EXISTS idx_memory_user_predicate ON memory_facts(user_id, predicate);
CREATE INDEX IF NOT EXISTS idx_memory_active ON memory_facts(user_id, superseded_at) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_memory_reinforced ON memory_facts(user_id, last_reinforced_at);

-- GIN 索引便于按 tags / sources 查询
CREATE INDEX IF NOT EXISTS idx_memory_tags_gin ON memory_facts USING gin(tags);
CREATE INDEX IF NOT EXISTS idx_memory_sources_gin ON memory_facts USING gin(sources);
