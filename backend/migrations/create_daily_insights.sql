-- 每日 Insight 洞察 (阶段"从管你到懂你")
-- 每用户每日一条, 由 Celery 06:30 task 生成

CREATE TABLE IF NOT EXISTS daily_insights (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    insight_date DATE NOT NULL,

    kind VARCHAR(50) NOT NULL,           -- gene_pgx / lab_trend / hrv_pattern / ...
    rule_id VARCHAR(80),

    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    evidence JSONB DEFAULT '{}'::jsonb,

    confidence REAL NOT NULL DEFAULT 0.7,
    severity VARCHAR(20) NOT NULL DEFAULT 'info',

    -- 用户反馈 (为 Trust Loop 第 2 步预留)
    user_feedback VARCHAR(20),
    feedback_note TEXT,
    feedback_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_insights_user_date
    ON daily_insights (user_id, insight_date);

CREATE INDEX IF NOT EXISTS ix_insights_user_feedback
    ON daily_insights (user_id, user_feedback);

CREATE INDEX IF NOT EXISTS ix_insights_kind
    ON daily_insights (kind);
