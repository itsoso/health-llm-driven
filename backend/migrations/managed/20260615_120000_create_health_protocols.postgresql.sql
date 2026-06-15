-- 健康协议层 P1:HealthProtocol(最佳实践协议)+ HealthProtocolEvent(双轨合流事件流)
CREATE TABLE IF NOT EXISTS health_protocols (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    domain VARCHAR(20) NOT NULL,
    name VARCHAR(200) NOT NULL,
    mechanism VARCHAR(30),
    implied_quantity JSONB,
    cadence VARCHAR(20) DEFAULT 'daily',
    time_window VARCHAR(20) DEFAULT 'anytime',
    completion_mode VARCHAR(20) DEFAULT 'one_tap',
    can_default_complete BOOLEAN DEFAULT FALSE,
    manual_track_allowed BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'active',
    program_id INTEGER,
    source_model VARCHAR(50),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS ix_health_protocols_user_status ON health_protocols(user_id, status);
CREATE INDEX IF NOT EXISTS ix_health_protocols_user_domain ON health_protocols(user_id, domain);

CREATE TABLE IF NOT EXISTS health_protocol_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    protocol_id INTEGER NOT NULL REFERENCES health_protocols(id),
    event_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL,
    track VARCHAR(10) NOT NULL DEFAULT 'protocol',
    value JSONB,
    skip_reason VARCHAR(40),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_hpe_protocol_date ON health_protocol_events(protocol_id, event_date);
CREATE INDEX IF NOT EXISTS ix_hpe_user_date ON health_protocol_events(user_id, event_date);
