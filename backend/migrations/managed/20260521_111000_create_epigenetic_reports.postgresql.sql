CREATE TABLE IF NOT EXISTS epigenetic_reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    vendor VARCHAR(120) NOT NULL,
    sample_date DATE NOT NULL,
    clock_type VARCHAR(120) NOT NULL,
    biological_age DOUBLE PRECISION,
    pace_of_aging DOUBLE PRECISION,
    confidence VARCHAR(20) NOT NULL DEFAULT 'low',
    raw_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_epigenetic_reports_user_sample_date
    ON epigenetic_reports(user_id, sample_date);

CREATE INDEX IF NOT EXISTS idx_epigenetic_reports_user_clock
    ON epigenetic_reports(user_id, clock_type);
