# Query and response reliability

Status: shipped. Updated: 2026-09-13. Release verification: `docs/dossiers/2026-09-12-query-response-reliability.md`. Evidence: `docs/analysis/2026-09-12-query-response-quality-review.md`.

## Decision and admission

Implement the approved query/response improvement plan as maintenance of the existing HealthTwin, SafetyGuardian, WriteIntent and ExecutionEvent contracts. Current users should receive consistent owned-data reads, grounded advice and accurate task outcomes without learning internal tool names. This strengthens observation, safe interpretation and execution verification. No new medical prescribing authority, account access or autonomous write permission is introduced.

## User flow and contract

Authenticated request -> shared interpreted scope -> permission-checked tool calls -> evidence -> task outcome and answer. Quoted material is data, not a cancellation or grant of authority. Same-day diet reads through equivalent tools must bind the same date and optional meal. A query followed by advice retains both goals. Today's summary initially covers the supported exact-date diet and sleep domains and explicitly identifies this scope; absent data and unqueried domains must not be represented as a full health assessment.

Generation termination remains distinct from task completion. Existing metadata stays backward compatible; authoritative turn_outcome is consumed by clients. Partial execution cannot silently become complete. A blocked sync must say no completion was verified, even if older data exists. A confirmed enqueue proves only that the background job was submitted; it never proves data refreshed. The generic owned Garmin sync capability does not accept model-selected owners, payloads or historical windows. No database schema migration is intended.

Diet correction parses a valid ratio separately from target and serving-basis uncertainty. Only an authenticated, exact existing record may be updated, retaining idempotency and readback. Risk classification precedes fast model selection for personalized supplement/medication advice. Summaries use evidence for their own time scope; no meal receipt can prove full-day intake. Daily summaries require a known non-fast actual provider in every routing mode. Their displayed diet totals, record counts and sleep readings are calculated from verified current-turn rows; identical food names do not merge records. Missing measurements stay unknown. The model receives only fixed numeric facts in system context, never record free text. Optional advice must not repeat numeric observations or treat incomplete records as full-day intake; a failed advice contract preserves facts and reports partial completion.

## Acceptance

- Equivalent tools and paraphrases of today's diet recall agree on owned scope; foreign-user, quoted, hypothetical, future and cancelled requests retain their boundaries.
- Dinner query plus advice and today's summary reach real Pi tool dispatch with exact-day arguments; summary partial/missing data stays explicit. Reaching the meal API cap cannot attest complete recall.
- Pasted “不用再买” does not cancel analysis; actual user cancellation outside quoted content still cancels.
- Valid meal ratio variants work; multiple targets, conflicting fractions, item-level ratios and ambiguous serving basis require precise clarification without a write.
- Actual action outcomes survive stream, persistence and applicable Web/Mobile presentation; failed synchronization never claims this run synced.
- High-risk advice cannot be downgraded to a fast simple-read route, including explicit model selections and staged routing disabled.
- Existing isolation/write safety regressions, PostgreSQL tests, Pi scripted-provider trajectories and required live LLM gate pass before release.

## Rollout and rollback

Use the existing governed backend release from a clean verified revision, exact CI and independent safety GO. Client-only changes use their appropriate release path. Revert the owned change set to roll back; retain existing production data and audit records. Post-deploy validation separately verifies service health, deployed revision and read-only user behavior.
