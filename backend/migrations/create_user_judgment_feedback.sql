-- 用户对 AI 判断的秒级反馈表 (Trust Loop 闭环)
-- polymorphic: target_type + target_id 指向 insights / anomaly_alerts / action_cards / etc

CREATE TABLE IF NOT EXISTS user_judgment_feedback (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_type VARCHAR(40) NOT NULL,
    target_id INTEGER NOT NULL,
    feedback VARCHAR(20) NOT NULL,
    note TEXT,
    snapshot TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 幂等: 同一 user + target 只能一条 (覆盖更新)
CREATE UNIQUE INDEX IF NOT EXISTS ix_feedback_user_target
    ON user_judgment_feedback (user_id, target_type, target_id);

CREATE INDEX IF NOT EXISTS ix_feedback_user_time
    ON user_judgment_feedback (user_id, created_at);

CREATE INDEX IF NOT EXISTS ix_feedback_user_value
    ON user_judgment_feedback (user_id, feedback);
