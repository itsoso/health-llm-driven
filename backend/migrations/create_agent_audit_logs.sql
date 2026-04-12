-- Agent 审计日志表
CREATE TABLE IF NOT EXISTS agent_audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    agent_type VARCHAR(50) NOT NULL,
    specialist_name VARCHAR(80),
    action VARCHAR(50) NOT NULL,
    query TEXT,
    result_summary TEXT,
    alerts_count INTEGER DEFAULT 0,
    findings_count INTEGER DEFAULT 0,
    result_detail JSONB,
    twin_build_ms INTEGER,
    evaluate_ms INTEGER,
    total_ms INTEGER,
    twin_sources JSONB,
    intent_categories JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_audit_user_id ON agent_audit_logs(user_id);
CREATE INDEX IF NOT EXISTS ix_audit_agent_type ON agent_audit_logs(agent_type);
CREATE INDEX IF NOT EXISTS ix_audit_created_at ON agent_audit_logs(created_at);

COMMENT ON TABLE agent_audit_logs IS 'Agent/Specialist 评估审计日志，支持"系统为什么告诉我这个"的可追溯查询';
