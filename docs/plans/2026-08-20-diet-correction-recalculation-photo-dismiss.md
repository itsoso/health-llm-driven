# Diet Correction Recalculation And Photo Dismiss Implementation Plan

**Goal:** Recalculate nutrition whenever the chat adjustment changes food content, and allow a vertical swipe to dismiss the expanded meal photo.

**Architecture:** Add one owner-scoped backend command that snapshots the record, estimates without holding a row lock, sanitizes/calibrates, then re-locks and CAS-validates before one commit. Mobile uses this command only when food changes and retains the existing PUT for unchanged-food manual edits. The response replaces all nutrition fields, including nulls. The photo gallery recognizes only dominant vertical gestures so horizontal pagination remains intact.

## Task 1: Atomically recalculate a saved record

**Files:**
- Modify: `backend/app/schemas/diet.py`
- Modify: `backend/app/api/diet.py`
- Modify: `backend/app/services/post_record_quality.py`
- Modify: `backend/app/services/agent_executor.py`
- Test: `backend/tests/test_diet.py`
- Test: `backend/tests/test_post_record_quality.py`
- Test: `backend/tests/test_agent_executor_food_vision.py`

1. Add failing API tests proving owner authorization precedes model work; non-food rows and forged totals cannot be persisted; all five fields and truthful provenance are committed; estimation failure produces zero write; a during-estimate concurrent mutation returns 409; same-operation replay is idempotent while key reuse is rejected; alcohol-bearing corrections are blocked before estimation; internal exceptions use generic detail.
2. Run the focused tests and confirm the expected RED.
3. Add `DietRecordNutritionRecalculateRequest` and `POST /diet/records/{id}/recalculate-nutrition`. Require an expected revision and bounded `Idempotency-Key`; bind both plus owner/record/content in a server-side request digest and store only operation/request digests in the existing provenance JSON. Resolve same-request replay before model work and again after locking a concurrent winner. Capture a bounded snapshot, estimate outside a row lock, run sanitizer → calibration → sanitizer, require usable calories/macros, clear unreviewed health tips, then `FOR UPDATE` + `populate_existing` + snapshot/revision comparison before one commit and full response. Reject old/new alcohol-bearing descriptions because this estimator cannot safely update standard-drink units.
4. Include the current record `updated_at` and fiber in the adjustment action seed so Mobile can send a meaningful optimistic-concurrency token and edit all five nutrients.
5. Run the focused tests to GREEN.

## Task 2: Recalculate before saving a changed food description

**Files:**
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/components/chat/cards/RecordQualityCard.tsx`
- Modify: `mobile/components/chat/cards/DietDraftCard.tsx`
- Modify: `mobile/components/chat/cards/registry.tsx`
- Modify: `mobile/types/api.generated.ts`
- Modify: `frontend/src/types/api.generated.ts`
- Test: `mobile/components/chat/cards/__tests__/RecordQualityCard.test.tsx`
- Test: `mobile/components/chat/cards/__tests__/registry.test.tsx`
- Test: `mobile/services/__tests__/diet.test.ts`

1. Add failing tests for one-bowl → two-bowl atomic recalculation, all five response nutrients replacing old values (including null), no ordinary PUT after recalculation failure, direct PUT when only meal type/nutrients change, and a 409 conflict that preserves input but cannot endlessly retry the same stale revision.
2. Run the focused Jest file and confirm RED.
3. Add `recalculateDietRecordNutrition`; compare normalized seed/current food; changed food calls only that command with the seed revision and a stable per-payload operation key. Same-payload retries reuse the key; changing revision/food/meal type generates a new key. Include fiber in the editor/seed and always build the next seed from the complete server response. In both card surfaces, spread explicit nulls from that seed so stale top-level values disappear, and invalidate meal-dependent progress/next-action projections rather than showing values computed from the old record. Keep action lock and retryable input state; on 409, keep the edit visible but require the user to reopen/refresh instead of resending the stale token.
4. Regenerate both Mobile and Frontend OpenAPI types and require `./scripts/generate-api-types.sh --check` to pass.
5. Run the focused file to GREEN.

## Task 3: Add vertical swipe-to-dismiss

**Files:**
- Modify: `mobile/components/chat/cards/DietDraftCard.tsx`
- Test: `mobile/components/chat/cards/__tests__/registry.test.tsx`

1. Add failing tests for dominant vertical swipe close and short/horizontal non-dismissal.
2. Run the focused tests and confirm RED.
3. Add a bounded gesture predicate and gallery responder; preserve horizontal `ScrollView`, `onRequestClose`, and the accessible close button.
4. Run the focused tests to GREEN.

## Task 4: Gates

1. Run Backend and Mobile focused suites, generated API type check, Mobile TypeScript, lint on touched files, Dossier consistency, system-map check, and `git diff --check`.
2. Request an independent safety/privacy review of the fixed diff. BLOCK returns to implementation.
3. Only after G3/G4 pass, stage exactly owned files and commit. Backend deploy must precede Mobile production OTA; production user-path validation remains G5/G6.
