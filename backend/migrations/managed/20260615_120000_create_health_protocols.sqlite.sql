-- 健康协议层 P1 (sqlite 变体)
CREATE TABLE IF NOT EXISTS health_protocols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    domain VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    mechanism VARCHAR(30),
    implied_quantity TEXT,
    cadence VARCHAR(20) DEFAULT 'daily',
    time_window VARCHAR(20) DEFAULT 'anytime',
    completion_mode VARCHAR(20) DEFAULT 'one_tap',
    can_default_complete BOOLEAN DEFAULT 0,
    manual_track_allowed BOOLEAN DEFAULT 1,
    status VARCHAR(20) DEFAULT 'active',
    program_id INTEGER,
    source_model VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_health_protocols_user_status ON health_protocols(user_id, status);
CREATE INDEX IF NOT EXISTS ix_health_protocols_user_domain ON health_protocols(user_id, domain);

CREATE TABLE IF NOT EXISTS health_protocol_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    protocol_id INTEGER NOT NULL,
    event_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    track VARCHAR(10) NOT NULL DEFAULT 'protocol',
    value TEXT,
    skip_reason VARCHAR(40),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_hpe_protocol_date ON health_protocol_events(protocol_id, event_date);
CREATE INDEX IF NOT EXISTS ix_hpe_user_date ON health_protocol_events(user_id, event_date);
