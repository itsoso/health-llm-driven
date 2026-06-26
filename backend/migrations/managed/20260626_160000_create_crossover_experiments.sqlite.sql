-- R16 P4: A·B·A·B 交叉实验(SQLite:测试 fixture 走 create_all,本文件仅 prod 形态对齐)。
CREATE TABLE IF NOT EXISTS crossover_experiments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    metric_code VARCHAR(40) NOT NULL,
    direction   VARCHAR(8) DEFAULT 'down',
    status      VARCHAR(16) NOT NULL DEFAULT 'active',
    phases      TEXT,
    verdict     VARCHAR(20),
    confidence  VARCHAR(12),
    created_at  TIMESTAMP NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    updated_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_crossover_user_status ON crossover_experiments (user_id, status);
