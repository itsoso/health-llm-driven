-- Additive private GPS storage. Forward repair only; disable capture endpoints
-- before any manual removal. Do not drop retained owner data as code rollback.
CREATE TABLE IF NOT EXISTS daily_journey_requests (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_id VARCHAR(36) NOT NULL,
    session_id VARCHAR(36) NOT NULL UNIQUE,
    PRIMARY KEY (user_id, request_id)
);
CREATE TABLE IF NOT EXISTS daily_journey_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    client_id VARCHAR(36) NOT NULL,
    local_date DATE NOT NULL,
    timezone VARCHAR(64) NOT NULL,
    status VARCHAR(8) NOT NULL,
    version INTEGER NOT NULL,
    segment INTEGER NOT NULL,
    last_state_command VARCHAR(64),
    started_at TIMESTAMP NOT NULL,
    segment_started_at TIMESTAMP NOT NULL,
    segment_ended_at TIMESTAMP,
    deadline_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    retention_days INTEGER NOT NULL,
    point_count INTEGER NOT NULL,
    annotations TEXT NOT NULL,
    CONSTRAINT ck_daily_journey_status CHECK (status IN ('active', 'paused', 'ended')),
    CONSTRAINT ck_daily_journey_retention CHECK (retention_days IN (1, 7)),
    CONSTRAINT ck_daily_journey_version CHECK (version > 0 AND segment > 0),
    CONSTRAINT ck_daily_journey_count CHECK (point_count >= 0 AND point_count <= 10000)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_journey_unfinished_owner ON daily_journey_sessions(user_id) WHERE status IN ('active', 'paused');
CREATE INDEX IF NOT EXISTS ix_daily_journey_owner_day ON daily_journey_sessions(user_id, local_date);
CREATE INDEX IF NOT EXISTS ix_daily_journey_expiry ON daily_journey_sessions(expires_at);
CREATE TABLE IF NOT EXISTS daily_journey_points (
    session_id VARCHAR(36) NOT NULL REFERENCES daily_journey_sessions(id) ON DELETE CASCADE,
    id VARCHAR(36) NOT NULL,
    segment INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (session_id, id),
    CONSTRAINT ck_daily_journey_point_segment CHECK (segment > 0)
);
