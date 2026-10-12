-- Preserve the existing application contract: legacy naive values mean UTC.
-- Do not infer or subtract a historical Shanghai offset. Successful future syncs
-- write an aware instant into the corrected type, independent of session timezone.
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';
DO $migration$
DECLARE column_type text;
BEGIN
    SELECT data_type INTO column_type
    FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'garmin_credentials'
      AND column_name = 'last_sync_at';
    IF column_type = 'timestamp without time zone' THEN
        ALTER TABLE public.garmin_credentials
            ALTER COLUMN last_sync_at TYPE TIMESTAMPTZ
            USING last_sync_at AT TIME ZONE 'UTC';
    ELSIF column_type IS DISTINCT FROM 'timestamp with time zone' THEN
        RAISE EXCEPTION 'garmin sync timestamp column has an unsupported type';
    END IF;
END
$migration$;
