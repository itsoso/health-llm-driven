-- Harness Slice 3: 程序性记忆/配方 — 确定性重放的工具序列。
-- steps = [{"tool", "args_template"}];trigger_phrases 精确匹配;
-- 确认门(typed_only/never_auto)在重放路径原样生效,不在库层放行。
CREATE TABLE IF NOT EXISTS procedure_recipes (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    trigger_phrases JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_from_conversation_id INTEGER,
    use_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_procedure_recipes_user_id
    ON procedure_recipes(user_id);
