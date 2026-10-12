-- Manual rollback only. Prefer rolling back the application while retaining
-- the compatible timezone-aware column. This restores legacy UTC semantics,
-- not the session-local implicit cast. Keep the original migration ledger;
-- a later forward rollout requires a new reviewed managed migration ID.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $rollback$
DECLARE column_type text;
BEGIN
    SELECT data_type INTO column_type FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'garmin_credentials'
      AND column_name = 'last_sync_at';
    IF column_type = 'timestamp with time zone' THEN
        ALTER TABLE public.garmin_credentials
            ALTER COLUMN last_sync_at TYPE TIMESTAMP WITHOUT TIME ZONE
            USING last_sync_at AT TIME ZONE 'UTC';
    ELSIF column_type IS DISTINCT FROM 'timestamp without time zone' THEN
        RAISE EXCEPTION 'garmin sync timestamp rollback type is unsupported';
    END IF;
END
$rollback$;
