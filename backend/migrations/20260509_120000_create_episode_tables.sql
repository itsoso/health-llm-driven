-- Agent-Native v3 — Episode 闭环核心 4 表
-- 九对象模型的 Episode / ActionGraph / Feedback / Outcome 落库.
-- Protocol 走 YAML registry (backend/protocols/), 不入库.

-- ─── health_episodes ───────────────────────────────────
CREATE TABLE IF NOT EXISTS health_episodes (
    id                 SERIAL PRIMARY KEY,
    user_id            INTEGER NOT NULL REFERENCES users(id),
    episode_type       VARCHAR(32) NOT NULL,
    source_type        VARCHAR(40),
    source_id          INTEGER,

    occurred_at        TIMESTAMP WITH TIME ZONE NOT NULL,
    opened_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    closed_at          TIMESTAMP WITH TIME ZONE,

    status             VARCHAR(16) NOT NULL DEFAULT 'open',
    risk_level         VARCHAR(4)  NOT NULL DEFAULT 'L0',
    risk_flags         JSONB,

    protocol_slug      VARCHAR(80),
    protocol_version   VARCHAR(20),

    context_snapshot   JSONB,
    baseline_snapshot  JSONB,
    headline           TEXT,

    created_at         TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at         TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_episode_user_occurred ON health_episodes (user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_episode_user_status   ON health_episodes (user_id, status);
CREATE INDEX IF NOT EXISTS idx_episode_user_type     ON health_episodes (user_id, episode_type);
CREATE INDEX IF NOT EXISTS idx_episode_protocol      ON health_episodes (protocol_slug);


-- ─── episode_actions (ActionGraph 节点) ────────────────
CREATE TABLE IF NOT EXISTS episode_actions (
    id                  SERIAL PRIMARY KEY,
    episode_id          INTEGER NOT NULL REFERENCES health_episodes(id) ON DELETE CASCADE,
    sequence            INTEGER NOT NULL DEFAULT 0,

    title               TEXT NOT NULL,
    body                TEXT,
    icon                VARCHAR(40),

    action_type         VARCHAR(40) NOT NULL,
    template_id         VARCHAR(80),
    evidence_id         VARCHAR(80),

    time_window_start   TIMESTAMP WITH TIME ZONE,
    time_window_end     TIMESTAMP WITH TIME ZONE,
    condition_expr      VARCHAR(200),

    completion_check    JSONB,
    risk_condition      JSONB,

    status              VARCHAR(16) NOT NULL DEFAULT 'pending',
    completed_at        TIMESTAMP WITH TIME ZONE,
    skipped_at          TIMESTAMP WITH TIME ZONE,
    skip_reason         VARCHAR(40),

    push_sent_at        TIMESTAMP WITH TIME ZONE,
    push_dedup_key      VARCHAR(120),

    created_at          TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at          TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_action_episode_seq     ON episode_actions (episode_id, sequence);
CREATE INDEX IF NOT EXISTS idx_action_status_window   ON episode_actions (status, time_window_start);


-- ─── episode_feedbacks ─────────────────────────────────
CREATE TABLE IF NOT EXISTS episode_feedbacks (
    id           SERIAL PRIMARY KEY,
    episode_id   INTEGER NOT NULL REFERENCES health_episodes(id) ON DELETE CASCADE,
    action_id    INTEGER REFERENCES episode_actions(id) ON DELETE SET NULL,

    kind         VARCHAR(40) NOT NULL,
    payload      JSONB,
    source       VARCHAR(20) NOT NULL DEFAULT 'mobile',

    created_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_feedback_episode_created ON episode_feedbacks (episode_id, created_at DESC);


-- ─── episode_outcomes ──────────────────────────────────
CREATE TABLE IF NOT EXISTS episode_outcomes (
    id                 SERIAL PRIMARY KEY,
    episode_id         INTEGER NOT NULL UNIQUE REFERENCES health_episodes(id) ON DELETE CASCADE,

    actions_total      INTEGER NOT NULL DEFAULT 0,
    actions_done       INTEGER NOT NULL DEFAULT 0,
    actions_skipped    INTEGER NOT NULL DEFAULT 0,
    completion_rate    REAL,

    metrics_delta      JSONB,
    summary            TEXT,
    notes              JSONB,

    created_at         TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at         TIMESTAMP WITH TIME ZONE
);
