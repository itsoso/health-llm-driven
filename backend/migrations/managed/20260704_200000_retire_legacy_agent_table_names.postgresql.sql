DO $$
BEGIN
    IF to_regclass('public.openclaw_conversations') IS NOT NULL
       AND to_regclass('public.agent_conversations') IS NULL THEN
        ALTER TABLE openclaw_conversations RENAME TO agent_conversations;
    END IF;

    IF to_regclass('public.openclaw_messages') IS NOT NULL
       AND to_regclass('public.agent_messages') IS NULL THEN
        ALTER TABLE openclaw_messages RENAME TO agent_messages;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'health_trend_reports'
          AND column_name = 'openclaw_batch_id'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'health_trend_reports'
          AND column_name = 'analysis_batch_id'
    ) THEN
        ALTER TABLE health_trend_reports RENAME COLUMN openclaw_batch_id TO analysis_batch_id;
    END IF;

    IF to_regclass('public.agent_conversations') IS NOT NULL THEN
        DROP INDEX IF EXISTS ix_openclaw_conv_user_updated;
        CREATE INDEX IF NOT EXISTS ix_agent_conv_user_updated
            ON agent_conversations(user_id, updated_at);
    END IF;
END $$;
