-- Clinical Journal — Agent 的"记得你"层
-- case_threads + clinical_journal_entries (SOAP)

CREATE TABLE IF NOT EXISTS case_threads (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    theme VARCHAR(40) NOT NULL,
    metric_key VARCHAR(50),
    title VARCHAR(200),
    summary TEXT,
    status VARCHAR(20) DEFAULT 'active',
    severity VARCHAR(20),
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    last_updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_case_threads_user_id ON case_threads(user_id);
CREATE INDEX IF NOT EXISTS ix_case_threads_theme ON case_threads(theme);
CREATE INDEX IF NOT EXISTS ix_case_threads_metric_key ON case_threads(metric_key);
CREATE INDEX IF NOT EXISTS ix_case_threads_status ON case_threads(status);
CREATE INDEX IF NOT EXISTS idx_case_thread_user_status ON case_threads(user_id, status);
CREATE INDEX IF NOT EXISTS idx_case_thread_user_theme ON case_threads(user_id, theme);


CREATE TABLE IF NOT EXISTS clinical_journal_entries (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    case_thread_id INTEGER REFERENCES case_threads(id) ON DELETE SET NULL,
    subjective TEXT,
    objective TEXT,
    assessment TEXT,
    plan TEXT,
    source_conversation_id INTEGER,
    source_message_id INTEGER,
    used_specialists VARCHAR(200),
    related_action_card_ids VARCHAR(120),
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    created_by VARCHAR(40) DEFAULT 'orchestrator'
);
CREATE INDEX IF NOT EXISTS ix_clinical_journal_user_id ON clinical_journal_entries(user_id);
CREATE INDEX IF NOT EXISTS ix_clinical_journal_case_thread ON clinical_journal_entries(case_thread_id);
CREATE INDEX IF NOT EXISTS ix_clinical_journal_source_conv ON clinical_journal_entries(source_conversation_id);
CREATE INDEX IF NOT EXISTS ix_clinical_journal_generated ON clinical_journal_entries(generated_at);
CREATE INDEX IF NOT EXISTS idx_journal_user_generated ON clinical_journal_entries(user_id, generated_at);
