CREATE TABLE community_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    source_type VARCHAR(40) NOT NULL,
    source_id INTEGER NOT NULL,
    snapshot JSON NOT NULL,
    caption TEXT,
    idempotency_key VARCHAR(160) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    CONSTRAINT uq_community_posts_user_idempotency UNIQUE (user_id, idempotency_key)
);
CREATE INDEX ix_community_posts_user_id ON community_posts(user_id);
CREATE INDEX ix_community_posts_status_created ON community_posts(status, created_at);

CREATE TABLE community_reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    reaction VARCHAR(24) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME,
    CONSTRAINT uq_community_reactions_post_user UNIQUE (post_id, user_id)
);
CREATE INDEX ix_community_reactions_post_id ON community_reactions(post_id);
CREATE INDEX ix_community_reactions_user_id ON community_reactions(user_id);

CREATE TABLE community_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    reason VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_community_reports_post_user UNIQUE (post_id, user_id)
);
CREATE INDEX ix_community_reports_post_id ON community_reports(post_id);
CREATE INDEX ix_community_reports_user_id ON community_reports(user_id);
