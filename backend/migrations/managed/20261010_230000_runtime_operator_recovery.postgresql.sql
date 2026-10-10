ALTER TABLE agent_runtime_rollout_events ADD COLUMN IF NOT EXISTS operator_review JSONB;
ALTER TABLE agent_runtime_rollout_events DROP CONSTRAINT ck_agent_runtime_rollout_events_actor;
ALTER TABLE agent_runtime_rollout_events ADD CONSTRAINT ck_agent_runtime_rollout_events_actor CHECK (actor_kind IN ('system', 'admin', 'operator'));
ALTER TABLE agent_runtime_rollout_events DROP CONSTRAINT ck_agent_runtime_rollout_events_transition;
ALTER TABLE agent_runtime_rollout_events ADD CONSTRAINT ck_agent_runtime_rollout_events_transition CHECK (
(action = 'resume' AND actor_kind IN ('admin', 'operator') AND reason_code = 'manual_resume') OR
(action = 'pause' AND ((actor_kind = 'admin' AND reason_code = 'manual_pause') OR
(actor_kind = 'system' AND reason_code IN ('system_failure_rate', 'reconciliation_detected', 'stale_lease_detected')))));
ALTER TABLE agent_runtime_rollout_events ADD CONSTRAINT ck_agent_runtime_rollout_events_operator_review CHECK (
(actor_kind = 'operator' AND actor_user_id IS NULL AND operator_review IS NOT NULL AND jsonb_typeof(operator_review) = 'object') OR
(actor_kind <> 'operator' AND operator_review IS NULL));
