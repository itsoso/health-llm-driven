-- SQLite 等价(测试库)。无 TIMESTAMPTZ,用 TIMESTAMP。
CREATE TABLE IF NOT EXISTS originator_recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    generic_name VARCHAR(100) NOT NULL,
    brand VARCHAR(120),
    manufacturer VARCHAR(160),
    status VARCHAR(20) NOT NULL DEFAULT 'suggested',
    source VARCHAR(20) DEFAULT 'chat',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orig_rec_user_generic
    ON originator_recommendations (user_id, generic_name);
