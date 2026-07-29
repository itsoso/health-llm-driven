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

UPDATE agent_run_attempts
SET
    status = 'failed',
    error_code = COALESCE(
        error_code,
        'external_session_merge_active_run'
    ),
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
WHERE run_id IN (
    SELECT run.run_id
    FROM agent_runs AS run
    JOIN reva_external_session_merge_map AS merge_map
      ON merge_map.duplicate_id = run.conversation_id
    WHERE run.status IN ('queued', 'running')
)
  AND status IN ('queued', 'running');

UPDATE agent_runs
SET
    status = 'reconciliation_required',
    retryable = 0,
    error_code = COALESCE(
        error_code,
        'external_session_merge_active_run'
    ),
    finished_at = COALESCE(finished_at, CURRENT_TIMESTAMP)
WHERE conversation_id IN (
    SELECT duplicate_id
    FROM reva_external_session_merge_map
)
  AND status IN ('queued', 'running');

UPDATE agent_messages
SET conversation_id = (
    SELECT merge_map.canonical_id
    FROM reva_external_session_merge_map AS merge_map
    WHERE merge_map.duplicate_id = agent_messages.conversation_id
)
WHERE conversation_id IN (
    SELECT duplicate_id
    FROM reva_external_session_merge_map
);

UPDATE agent_runs
SET input_seq = NULL
WHERE conversation_id IN (
    SELECT duplicate_id
    FROM reva_external_session_merge_map
);

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

UPDATE agent_runs
SET
    conversation_id = (
        SELECT resequence.canonical_id
        FROM reva_external_run_resequence_map AS resequence
        WHERE resequence.run_id = agent_runs.run_id
    ),
    input_seq = (
        SELECT resequence.new_input_seq
        FROM reva_external_run_resequence_map AS resequence
        WHERE resequence.run_id = agent_runs.run_id
    )
WHERE run_id IN (
    SELECT run_id
    FROM reva_external_run_resequence_map
);

UPDATE agent_conversations
SET session_key = NULL
WHERE id IN (
    SELECT duplicate_id
    FROM reva_external_session_merge_map
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_conv_user_session_key
    ON agent_conversations(user_id, session_key)
    WHERE session_key LIKE 'external-%';

DROP TABLE reva_external_run_resequence_map;
DROP TABLE reva_external_session_merge_map;
