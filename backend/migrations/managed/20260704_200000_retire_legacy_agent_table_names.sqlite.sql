ALTER TABLE openclaw_conversations RENAME TO agent_conversations;
ALTER TABLE openclaw_messages RENAME TO agent_messages;
ALTER TABLE health_trend_reports RENAME COLUMN openclaw_batch_id TO analysis_batch_id;
DROP INDEX IF EXISTS ix_openclaw_conv_user_updated;
CREATE INDEX IF NOT EXISTS ix_agent_conv_user_updated ON agent_conversations(user_id, updated_at);
