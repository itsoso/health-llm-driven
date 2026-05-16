-- Structured provenance for genetic imports (PostgreSQL production).

CREATE TABLE IF NOT EXISTS genetic_import_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    profile_id INTEGER NOT NULL REFERENCES genetic_profiles(id) ON DELETE CASCADE,
    source_type VARCHAR(20) NOT NULL,
    provider VARCHAR(100),
    status VARCHAR(20) DEFAULT 'queued',
    parser_version VARCHAR(50) NOT NULL DEFAULT 'genetic-import-v2',
    raw_file_hash VARCHAR(64),
    raw_record_count INTEGER DEFAULT 0,
    known_total INTEGER DEFAULT 0,
    matched_count INTEGER DEFAULT 0,
    duplicate_count INTEGER DEFAULT 0,
    unknown_count INTEGER DEFAULT 0,
    unmapped_count INTEGER DEFAULT 0,
    missing_count INTEGER DEFAULT 0,
    coverage_summary JSONB,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS ix_genetic_import_jobs_user_id ON genetic_import_jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_genetic_import_jobs_profile_id ON genetic_import_jobs(profile_id);
CREATE INDEX IF NOT EXISTS ix_genetic_import_jobs_status ON genetic_import_jobs(status);
CREATE INDEX IF NOT EXISTS ix_genetic_import_jobs_user_profile ON genetic_import_jobs(user_id, profile_id);
CREATE INDEX IF NOT EXISTS ix_genetic_variants_profile_rsid ON genetic_variants(profile_id, rsid);
