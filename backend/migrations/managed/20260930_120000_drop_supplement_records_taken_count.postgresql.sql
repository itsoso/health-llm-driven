-- Drop the legacy supplement_records.taken_count column.
-- Created by the January 2026 SQLite-to-PostgreSQL copy script with DEFAULT 1. The ORM
-- never mapped it and no application code reads or writes it. Read-only checks on
-- 2026-09-30 found 1 in every row, taken or not, so it carries no intake signal, yet it
-- was mistaken for intake evidence during the 2026-09-30 supplement-taken incident.
-- Deploy only after the frozen September taken backfill is applied or abandoned.
-- Forward compatible: the running release and any code rollback target never touch it.
-- Table risk: small table, catalog-only drop, no rewrite. deploy.sh stops the backend
-- and Celery before migrations, so only an outside session (an idle-in-transaction psql
-- or analytics connection) can hold a lock. lock_timeout turns such a wait into an error
-- instead of an endless hang. The guard aborts if any row differs from 1, so the drop
-- never discards information. A dependent view or constraint also aborts it (no CASCADE).
-- Any failure rolls back atomically and records nothing, but deploy.sh then keeps the
-- services stopped for manual recovery. Before deploying, check pg_stat_activity for
-- open transactions touching supplement_records. After a failure fix the cause and resume.
-- Rollback, run manually as the migration role, keeping the schema_migrations row:
--   ALTER TABLE supplement_records ADD COLUMN IF NOT EXISTS taken_count INTEGER DEFAULT 1
-- PostgreSQL 11+ fills the constant default into existing rows without a rewrite, which
-- restores every row to 1 as the guard verified. Dropping it again needs a new migration.
SET LOCAL lock_timeout = '30s';
LOCK TABLE supplement_records IN ACCESS EXCLUSIVE MODE;
DO $$
DECLARE
    informative_rows bigint;
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_attribute
        WHERE attrelid = 'supplement_records'::regclass
          AND attname = 'taken_count'
          AND NOT attisdropped
    ) THEN
        EXECUTE 'SELECT count(*) FROM supplement_records WHERE taken_count IS DISTINCT FROM 1'
            INTO informative_rows;
        IF informative_rows > 0 THEN
            RAISE EXCEPTION USING MESSAGE =
                'refusing to drop supplement_records.taken_count, '
                || informative_rows || ' row(s) differ from 1';
        END IF;
    END IF;
END $$;
ALTER TABLE supplement_records DROP COLUMN IF EXISTS taken_count;
