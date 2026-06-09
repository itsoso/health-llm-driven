CREATE TABLE IF NOT EXISTS biomarker_observations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    code VARCHAR(40) NOT NULL,
    domain VARCHAR(24),
    value DOUBLE PRECISION,
    unit VARCHAR(32),
    normalized_value DOUBLE PRECISION NOT NULL,
    normalized_unit VARCHAR(32) NOT NULL,
    ref_low DOUBLE PRECISION,
    ref_high DOUBLE PRECISION,
    flag VARCHAR(12),
    abnormal BOOLEAN DEFAULT FALSE,
    is_risk BOOLEAN DEFAULT FALSE,
    confidence VARCHAR(12),
    observed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    source_exam_item_id INTEGER REFERENCES medical_exam_items(id) ON DELETE SET NULL,
    source VARCHAR(20),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_biomarker_obs_user_code_observed ON biomarker_observations(user_id, code, observed_at);
CREATE INDEX IF NOT EXISTS idx_biomarker_obs_user_abnormal ON biomarker_observations(user_id, abnormal);
CREATE INDEX IF NOT EXISTS idx_biomarker_obs_code ON biomarker_observations(code);
