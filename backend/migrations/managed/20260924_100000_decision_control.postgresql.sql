-- Additive and default-off. Code rollback retains the switch and audit history.
CREATE TABLE IF NOT EXISTS decision_controls (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    updated_by INTEGER CHECK (updated_by IS NULL OR updated_by = 3),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO decision_controls (id, enabled, revision) VALUES (1, FALSE, 0)
ON CONFLICT (id) DO NOTHING;
