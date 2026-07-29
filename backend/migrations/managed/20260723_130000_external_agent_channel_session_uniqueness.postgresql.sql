CREATE TEMP TABLE reva_external_session_merge_map AS
WITH canonical AS (
    SELECT
        user_id,
        session_key,
        MIN(id) AS canonical_id
    FROM agent_conversations
    WHERE session_key LIKE 'external-%'
    GROUP BY user_id, session_key
    HAVING COUNT(*) > 1
)
SELECT conversation.id AS duplicate_id, canonical.canonical_id
FROM agent_conversations AS conversation
JOIN canonical
  ON canonical.user_id = conversation.user_id
 AND canonical.session_key = conversation.session_key
WHERE conversation.id <> canonical.canonical_id;

UPDATE agent_run_attempts AS attempt
SET
    status = 'failed',
    error_code = COALESCE(
        attempt.error_code,
        'external_session_merge_active_run'
    ),
    finished_at = COALESCE(attempt.finished_at, NOW())
FROM agent_runs AS run
JOIN reva_external_session_merge_map AS merge_map
  ON merge_map.duplicate_id = run.conversation_id
WHERE attempt.run_id = run.run_id
  AND run.status IN ('queued', 'running')
  AND attempt.status IN ('queued', 'running');

UPDATE agent_runs AS run
SET
    status = 'reconciliation_required',
    retryable = FALSE,
    error_code = COALESCE(
        run.error_code,
        'external_session_merge_active_run'
    ),
    finished_at = COALESCE(run.finished_at, NOW())
FROM reva_external_session_merge_map AS merge_map
WHERE run.conversation_id = merge_map.duplicate_id
  AND run.status IN ('queued', 'running');

UPDATE agent_messages AS message
SET conversation_id = merge_map.canonical_id
FROM reva_external_session_merge_map AS merge_map
WHERE message.conversation_id = merge_map.duplicate_id;

UPDATE agent_runs AS run
SET input_seq = NULL
FROM reva_external_session_merge_map AS merge_map
WHERE run.conversation_id = merge_map.duplicate_id;

CREATE TEMP TABLE reva_external_run_resequence_map AS
WITH canonical_max AS (
    SELECT
        merge_map.canonical_id,
        COALESCE(MAX(run.input_seq), 0) AS max_input_seq
    FROM reva_external_session_merge_map AS merge_map
    LEFT JOIN agent_runs AS run
      ON run.conversation_id = merge_map.canonical_id
    GROUP BY merge_map.canonical_id
)
SELECT
    run.run_id,
    merge_map.canonical_id,
    canonical_max.max_input_seq
        + ROW_NUMBER() OVER (
            PARTITION BY merge_map.canonical_id
            ORDER BY run.created_at ASC, run.run_id ASC
        ) AS new_input_seq
FROM agent_runs AS run
JOIN reva_external_session_merge_map AS merge_map
  ON merge_map.duplicate_id = run.conversation_id
JOIN canonical_max
  ON canonical_max.canonical_id = merge_map.canonical_id;

UPDATE agent_runs AS run
SET
    conversation_id = resequence.canonical_id,
    input_seq = resequence.new_input_seq
FROM reva_external_run_resequence_map AS resequence
WHERE run.run_id = resequence.run_id;

UPDATE agent_conversations AS conversation
SET session_key = NULL
FROM reva_external_session_merge_map AS merge_map
WHERE conversation.id = merge_map.duplicate_id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_conv_user_session_key
    ON agent_conversations(user_id, session_key)
    WHERE session_key LIKE 'external-%';

DROP TABLE reva_external_run_resequence_map;
DROP TABLE reva_external_session_merge_map;
