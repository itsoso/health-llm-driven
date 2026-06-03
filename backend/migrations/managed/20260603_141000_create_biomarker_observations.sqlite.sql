CREATE TABLE IF NOT EXISTS biomarker_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    code VARCHAR(40) NOT NULL,
    domain VARCHAR(24),
    value FLOAT,
    unit VARCHAR(32),
    normalized_value FLOAT NOT NULL,
    normalized_unit VARCHAR(32) NOT NULL,
    ref_low FLOAT,
    ref_high FLOAT,
    flag VARCHAR(12),
    abnormal BOOLEAN DEFAULT 0,
    is_risk BOOLEAN DEFAULT 0,
    confidence VARCHAR(12),
    observed_at TIMESTAMP NOT NULL,
    source_exam_item_id INTEGER REFERENCES medical_exam_items(id) ON DELETE SET NULL,
    source VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_biomarker_obs_user_code_observed ON biomarker_observations(user_id, code, observed_at);
CREATE INDEX IF NOT EXISTS idx_biomarker_obs_user_abnormal ON biomarker_observations(user_id, abnormal);
CREATE INDEX IF NOT EXISTS idx_biomarker_obs_code ON biomarker_observations(code);
