-- SQLite 等价(测试库)。
CREATE TABLE IF NOT EXISTS connection_checkins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    checkin_date DATE NOT NULL DEFAULT CURRENT_DATE,
    ucla_score INTEGER,
    has_confidant BOOLEAN,
    in_stable_group BOOLEAN,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_connection_checkin_user_date
    ON connection_checkins (user_id, checkin_date);
