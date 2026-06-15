-- 智能卧室环境快照(家居传感器点事件)。设计文档 §7。隐私敏感, 不进通用 LLM。
-- 注 runner 按裸分号切分,注释里不能有分号。
CREATE TABLE IF NOT EXISTS bedroom_environment_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    room_id VARCHAR(64) NOT NULL DEFAULT 'bedroom',
    captured_at TIMESTAMPTZ NOT NULL,
    co2_ppm DOUBLE PRECISION,
    pm25 DOUBLE PRECISION,
    temperature_c DOUBLE PRECISION,
    humidity_percent DOUBLE PRECISION,
    tvoc DOUBLE PRECISION,
    illuminance_lux DOUBLE PRECISION,
    occupancy BOOLEAN,
    bed_presence BOOLEAN,
    sources JSONB,
    confidence VARCHAR(16) NOT NULL DEFAULT 'medium',
    stale BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_bedroom_env_user_room_ts UNIQUE (user_id, room_id, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_bedroom_env_user_room_ts
    ON bedroom_environment_snapshots (user_id, room_id, captured_at);
