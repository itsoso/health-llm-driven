-- H2-4: 月度复盘报告表
-- 依赖: users 表
-- 幂等: 用 IF NOT EXISTS

CREATE TABLE IF NOT EXISTS monthly_reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    report_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    version VARCHAR(16) NOT NULL DEFAULT 'v1',
    CONSTRAINT uq_monthly_report_user_ym UNIQUE (user_id, year, month)
);

CREATE INDEX IF NOT EXISTS ix_monthly_report_user_ym
    ON monthly_reports (user_id, year, month);
