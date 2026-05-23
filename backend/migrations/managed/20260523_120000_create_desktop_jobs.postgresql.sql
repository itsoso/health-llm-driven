CREATE TABLE IF NOT EXISTS desktop_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    source_kind VARCHAR(50),
    source_name VARCHAR(500),
    source_hash VARCHAR(128),
    request_payload JSONB,
    result_payload JSONB,
    error_message TEXT,
    retry_of_job_id INTEGER REFERENCES desktop_jobs(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_desktop_jobs_user_created ON desktop_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_desktop_jobs_user_status ON desktop_jobs(user_id, status);
