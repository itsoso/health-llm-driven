-- SQLite 等价(测试库)。
CREATE TABLE IF NOT EXISTS ecg_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    classification VARCHAR(64) NOT NULL,
    recorded_at TIMESTAMP,
    afib_event_count INTEGER NOT NULL DEFAULT 0,
    data_source VARCHAR(32) NOT NULL DEFAULT 'apple-watch',
    raw_data TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ecg_user_recorded UNIQUE (user_id, recorded_at)
);
CREATE INDEX IF NOT EXISTS ix_ecg_user_recorded
    ON ecg_observations (user_id, recorded_at);
