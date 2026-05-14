-- chat message meta (2026-05-14)
-- 存性能 + 可解释性数据 - 用户离开页面回来 reload conversation 时, 也能恢复 chat bubble footer.
-- elapsed_ms / llm_ms / llm_rounds / llm_rounds_ms / model / sources_used

ALTER TABLE openclaw_messages ADD COLUMN IF NOT EXISTS meta JSONB;
