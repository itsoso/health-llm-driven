PRAGMA defer_foreign_keys = ON;

CREATE TABLE illness_episodes_nullable_severity (
    id INTEGER NOT NULL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    status VARCHAR(20) NOT NULL,
    severity INTEGER,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
);

INSERT INTO illness_episodes_nullable_severity (
    id, user_id, name, start_date, end_date, status, severity, notes,
    created_at, updated_at
)
SELECT
    id, user_id, name, start_date, end_date, status, severity, notes,
    created_at, updated_at
FROM illness_episodes;

CREATE TABLE illness_updates_nullable_severity_parent (
    id INTEGER NOT NULL PRIMARY KEY,
    episode_id INTEGER NOT NULL REFERENCES illness_episodes_nullable_severity(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    update_date DATE NOT NULL,
    severity INTEGER,
    status VARCHAR(20),
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO illness_updates_nullable_severity_parent (
    id, episode_id, user_id, update_date, severity, status, notes, created_at
)
SELECT
    id, episode_id, user_id, update_date, severity, status, notes, created_at
FROM illness_updates;

DROP TABLE illness_updates;
DROP TABLE illness_episodes;
ALTER TABLE illness_episodes_nullable_severity RENAME TO illness_episodes;
ALTER TABLE illness_updates_nullable_severity_parent RENAME TO illness_updates;

CREATE INDEX ix_illness_episodes_user_id
    ON illness_episodes (user_id);
CREATE INDEX ix_illness_episodes_id
    ON illness_episodes (id);
CREATE INDEX idx_illness_episode_user_status
    ON illness_episodes (user_id, status);
CREATE INDEX ix_illness_updates_episode_id
    ON illness_updates (episode_id);
CREATE INDEX ix_illness_updates_user_id
    ON illness_updates (user_id);
CREATE INDEX ix_illness_updates_id
    ON illness_updates (id);
CREATE INDEX idx_illness_update_episode_date
    ON illness_updates (episode_id, update_date);
