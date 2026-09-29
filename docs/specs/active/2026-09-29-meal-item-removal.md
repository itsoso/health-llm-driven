# Source-bound meal item correction

> Status: implementing
> Updated: 2026-09-29
> Related: R5/R10, existing diet photo correction/editor/recalculation contracts

## Decision and admission

Bugfix for a user asking to remove an uneaten item from the recently saved photo
meal. Objects: existing WriteIntent and ExecutionEvent; Mobile is the execution
surface, authenticated backend records the truth. Privacy-sensitive health edit,
manual_confirm, no medical claim or autonomy elevation. One existing editor
confirmation is justified to verify replacement food/portions before re-estimation.
Success means a source-bound proposed edit, then existing revision-checked save;
never a whole-meal deletion or a new meal. Verification is immediate.

## Contract / smallest slice

Closed original-utterance item-removal requests enter a deterministic proposal
before model tools. Resolve the most recent meal card in a bounded conversation
window through its owner-scoped consumed photo draft and original user message,
or the unique attached food asset left by confirmed REST save after draft deletion.
Card/model IDs alone never grant authority. Require a fresh source and current
record owned by the authenticated user. Failed intervening turns may be skipped;
a newer unrelated turn or unsupported meal target must not select an older meal.
Use only an unambiguous complete food item in the current description; preserve
all remaining descriptions and portions. Missing/ambiguous/empty remainder asks
the user to use the meal editor, without a misleading permission error.

The existing record_quality adjust_record card carries proposed_food_items and
current revision. Existing Mobile UI, recalculate and compare-and-swap save remain
authoritative. No schema/API change, new permissions, native code or generic
read-policy relaxation. No live user records are modified by deployment.
History delivery preserves a pending proposal only against the same owned record
snapshot and revision; changed or unverifiable proposals become explicitly
unavailable with no edit action. Command snapshots retain original precision.

## Safety / non-goals

Negations, quotes, hypothetical/third-party instructions, extra clauses, whole
meal deletion and bulk edits are not accepted by this closed parser. No model
inference of IDs or direct arithmetic subtraction of estimated nutrients.
No write receipt or success claim before existing confirmed save. No clinical
advice, GPS/native WIP, historical bulk correction or generic semantic rewrite.

## Acceptance / verification / rollout

RED/GREEN at helper and real stream entry; synthetic fixtures only. Check owner,
conversation, source, freshness, consumed/pending state, unique matching item,
unchanged original, replay and zero model/tool calls. PostgreSQL integration,
existing editor/recalculation regressions, CI-mode suite, LLM change gate,
fixed-commit independent safety GO, exact-main CI and backend health precede
deployment. OTA only if Mobile runtime changes. Rollback code, never user data.

## Changelog

2026-09-29: accepted bounded photo-meal component correction using existing editor.
