-- Application rollback: hide private planning routes, retain personal versions.
CREATE TABLE IF NOT EXISTS life_navigation_workspaces (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    revision INTEGER NOT NULL DEFAULT 0,
    data JSON NOT NULL,
    history JSON NOT NULL,
    updated_at DATETIME NOT NULL
);
