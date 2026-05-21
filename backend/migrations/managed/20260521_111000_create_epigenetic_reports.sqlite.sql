CREATE TABLE IF NOT EXISTS epigenetic_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    vendor VARCHAR(120) NOT NULL,
    sample_date DATE NOT NULL,
    clock_type VARCHAR(120) NOT NULL,
    biological_age FLOAT,
    pace_of_aging FLOAT,
    confidence VARCHAR(20) NOT NULL DEFAULT 'low',
    raw_summary JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_epigenetic_reports_user_sample_date
    ON epigenetic_reports(user_id, sample_date);

CREATE INDEX IF NOT EXISTS idx_epigenetic_reports_user_clock
    ON epigenetic_reports(user_id, clock_type);
