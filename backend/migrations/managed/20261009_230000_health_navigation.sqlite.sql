CREATE TABLE IF NOT EXISTS health_navigation_occurrences (
 id VARCHAR(32) PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), plan_id INTEGER NOT NULL REFERENCES daily_operating_plans(id),
 source VARCHAR(40) NOT NULL DEFAULT 'daily_plan', plan_date DATE NOT NULL, action_key VARCHAR(160) NOT NULL,
 title TEXT NOT NULL, completion_criterion TEXT NOT NULL, safety_state VARCHAR(20) NOT NULL DEFAULT 'unknown', execution_status VARCHAR(20) NOT NULL DEFAULT 'pending',
 revision INTEGER NOT NULL DEFAULT 1, content_hash VARCHAR(64) NOT NULL, source_as_of TIMESTAMP NOT NULL, last_event_id INTEGER REFERENCES intervention_events(id),
 CONSTRAINT uq_health_nav_occurrence UNIQUE(user_id,source,plan_date,action_key));
CREATE INDEX IF NOT EXISTS ix_health_nav_user_date ON health_navigation_occurrences(user_id,plan_date);
CREATE TABLE IF NOT EXISTS health_navigation_operations (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), occurrence_id VARCHAR(32) NOT NULL REFERENCES health_navigation_occurrences(id),
 operation_id VARCHAR(36) NOT NULL, payload_hash VARCHAR(64) NOT NULL, receipt JSON NOT NULL, created_at TIMESTAMP NOT NULL,
 CONSTRAINT uq_health_nav_operation UNIQUE(user_id,operation_id));
CREATE TABLE IF NOT EXISTS health_navigation_days (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), plan_date DATE NOT NULL, source_as_of TIMESTAMP NOT NULL,
 CONSTRAINT uq_health_nav_day UNIQUE(user_id,plan_date));
