-- SQLite 等价(测试库)。
CREATE TABLE IF NOT EXISTS bedroom_environment_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    room_id VARCHAR(64) NOT NULL DEFAULT 'bedroom',
    captured_at TIMESTAMP NOT NULL,
    co2_ppm REAL,
    pm25 REAL,
    temperature_c REAL,
    humidity_percent REAL,
    tvoc REAL,
    illuminance_lux REAL,
    occupancy BOOLEAN,
    bed_presence BOOLEAN,
    sources TEXT,
    confidence VARCHAR(16) NOT NULL DEFAULT 'medium',
    stale BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_bedroom_env_user_room_ts UNIQUE (user_id, room_id, captured_at)
);
CREATE INDEX IF NOT EXISTS ix_bedroom_env_user_room_ts
    ON bedroom_environment_snapshots (user_id, room_id, captured_at);
