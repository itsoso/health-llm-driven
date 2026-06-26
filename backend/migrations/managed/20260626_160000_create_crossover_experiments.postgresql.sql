-- R16 P4: A·B·A·B 交叉实验(重复感知裁决)。
CREATE TABLE IF NOT EXISTS crossover_experiments (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    metric_code VARCHAR(40) NOT NULL,
    direction   VARCHAR(8) DEFAULT 'down',
    status      VARCHAR(16) NOT NULL DEFAULT 'active',
    phases      JSONB,
    verdict     VARCHAR(20),
    confidence  VARCHAR(12),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_crossover_user_status ON crossover_experiments (user_id, status);
