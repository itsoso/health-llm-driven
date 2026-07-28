ALTER TABLE medical_exams
    ADD COLUMN IF NOT EXISTS source_fingerprint VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS uq_medical_exams_user_source_fingerprint
    ON medical_exams (user_id, source_fingerprint)
    WHERE source_fingerprint IS NOT NULL;
