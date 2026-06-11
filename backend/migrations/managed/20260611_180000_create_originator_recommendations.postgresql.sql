-- 原研药推荐状态表。记录系统对某用户某药的原研药建议及采纳情况。
-- 用于对话中基于在用药推荐原研药,且采纳/忽略后抑制重复推荐。
-- 注 runner 按裸分号切分语句,注释里不能出现分号。
CREATE TABLE IF NOT EXISTS originator_recommendations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    generic_name VARCHAR(100) NOT NULL,
    brand VARCHAR(120),
    manufacturer VARCHAR(160),
    status VARCHAR(20) NOT NULL DEFAULT 'suggested',
    source VARCHAR(20) DEFAULT 'chat',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_orig_rec_user_generic
    ON originator_recommendations (user_id, generic_name);
