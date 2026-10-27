CREATE TABLE IF NOT EXISTS life_exam_attempts (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    id VARCHAR(36) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_id VARCHAR(36) NOT NULL,
    question_id VARCHAR(64) NOT NULL,
    question_version INTEGER NOT NULL,
    choice_index INTEGER NOT NULL,
    correct_index INTEGER NOT NULL,
    correct BOOLEAN NOT NULL,
    elapsed_seconds INTEGER NOT NULL,
    study_date DATE NOT NULL,
    answered_at DATETIME NOT NULL,
    question_snapshot JSON NOT NULL,
    CONSTRAINT uq_life_exam_owner_request UNIQUE (user_id, request_id),
    CONSTRAINT ck_life_exam_version CHECK (question_version >= 1),
    CONSTRAINT ck_life_exam_choices CHECK (choice_index BETWEEN 0 AND 7 AND correct_index BETWEEN 0 AND 7),
    CONSTRAINT ck_life_exam_elapsed CHECK (elapsed_seconds BETWEEN 0 AND 21600),
    CONSTRAINT ck_life_exam_grade CHECK (correct = (choice_index = correct_index))
);
CREATE INDEX IF NOT EXISTS ix_life_exam_owner_question_sequence ON life_exam_attempts(user_id, question_id, sequence);
CREATE INDEX IF NOT EXISTS ix_life_exam_owner_date_sequence ON life_exam_attempts(user_id, study_date, sequence);
