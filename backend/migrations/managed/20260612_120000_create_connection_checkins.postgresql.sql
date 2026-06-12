-- 社会连接 check-in(L4 长期韧性层主观问询)。UCLA-3 孤独量表 + 连接结构。
-- 注 runner 按裸分号切分,注释里不能有分号。
CREATE TABLE IF NOT EXISTS connection_checkins (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    checkin_date DATE NOT NULL DEFAULT CURRENT_DATE,
    ucla_score INTEGER,
    has_confidant BOOLEAN,
    in_stable_group BOOLEAN,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_connection_checkin_user_date
    ON connection_checkins (user_id, checkin_date);
