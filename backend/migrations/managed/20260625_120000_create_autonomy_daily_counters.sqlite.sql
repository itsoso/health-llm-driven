-- Write 自治层每用户每日执行计数(autonomy_daily_counters)SQLite 变体(CI / 本地)。
-- 测试库由 create_all 直接建表,本迁移仅 prod / 裸库跑。复合主键 (user_id, day)。幂等可重跑。
CREATE TABLE IF NOT EXISTS autonomy_daily_counters (
    user_id INTEGER NOT NULL,
    day DATE NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, day)
);
