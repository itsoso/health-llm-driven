# Feature Spec: Diet Correction Recalculation And Photo Dismiss

> Status: accepted
> Owner: Reva Mobile + Backend
> Updated: 2026-08-20
> Related PRD/PDD: `docs/prd/2026-07-11-diet-capture-excellence.md`, `docs/prd/2026-08-20-diet-correction-recalculation-photo-dismiss.md`
> Related code: `mobile/components/chat/cards/RecordQualityCard.tsx`, `mobile/components/chat/cards/DietDraftCard.tsx`, `backend/app/api/diet.py`

## 1. Decision

When a confirmed diet record's food description changes, Mobile must invoke one owner-scoped server command that recalculates and atomically updates the record; the meal photo gallery also gains vertical swipe-to-dismiss without removing horizontal paging or the close button.

## 2. Requirement Admission

```yaml
RequirementAdmission:
  request: recalculate stored nutrition after a food or portion edit and swipe away an expanded meal photo
  classification: product_change
  first_user_fit: frequent Mobile diet capture users correcting image estimates
  core_loop_step: capture -> corrected DietRecord -> HealthTwin -> next action
  first_class_objects: [ExecutionEvent, HealthTwin]
  target_surface: Mobile chat card with Backend source of truth
  source_of_truth: owner-scoped PostgreSQL diet_records
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: sanitized text nutrition estimate persisted by one confirmed atomic command
  claim_hedging: hedged
  verification_window: immediate save response and card refresh
  success_metric: changed food never retains stale nutrients; swipe close succeeds without horizontal false positives
  added_user_burden: none
  burden_justification: save button remains the only confirmation
  non_goals: measured nutrition, silent background edits, photo storage or sharing changes
  smallest_end_to_end_slice: changed description -> atomic recalculate command -> complete refreshed card; vertical swipe -> close
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 3. Surface And Data Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | detect changed food, show busy/error state, invoke exactly one write command, recognize vertical dismiss | changed food never falls back to ordinary PUT; horizontal gallery paging remains |
| Backend | authenticate, estimate and sanitize, revalidate concurrency, atomically update and return the full record | owner scope; no lock during model work; finite bounded nutrients; safe failure detail |

No database migration is required. Add `POST /diet/records/{id}/recalculate-nutrition` with `food_items`, optional `meal_type`, required `expected_updated_at`, and a required bounded `Idempotency-Key` header. It returns `DietRecordResponse`. The service captures a record snapshot, performs model work without a row lock, sanitizes and calibrates the result, then locks and rejects a changed snapshot with `409` before one commit. A same-key/same-request replay returns the already committed record without rerunning the model; key reuse with another request is rejected. Existing `PUT /diet/records/{id}` remains the path for unchanged-food manual edits only.

## 4. Safety And AI Boundary

- The LLM may propose per-food nutrition from the user-entered description; only deterministic backend code can authorize and commit the write.
- `sanitize_food_recognition_result` must remove non-food/UI items, bound values, and recompute totals from sanitized rows; reviewed-table calibration is followed by a second sanitization.
- Empty/failed estimates and version conflicts are blocking: no partial update and no stale old nutrition.
- Text estimation does not produce validated standard alcohol units. A correction is rejected before model work when the stored description, stored `alcohol_units`, or corrected description indicates alcohol; it must be completed in the full diet editor so the old safety fact is never silently cleared or carried into a different meal.
- Mobile sends the record revision supplied by the adjustment action when available. A `409` is not retryable with that same revision: the editor preserves the user's text and instructs them to reopen/refresh the record.
- The explicit Save action remains `manual_confirm`; the new command performs owner authorization before model invocation and owner/version revalidation before commit.
- The response is authoritative for all five nutrition fields. Mobile must apply explicit `null` values instead of merging only non-null fields.
- Summary/progress/next-action projections computed from the pre-edit record must be invalidated until rebuilt; the card must not mix the new meal with old daily totals or advice.
- Logs must not add meal text or model response bodies.
- Model-authored health tips are not persisted by this correction command. The operation key is stored only as an owner-scoped digest inside the existing provenance receipt and never logged.

## 5. Acceptance Criteria

```gherkin
Given a saved meal with one-bowl nutrients
When the user changes the description to two bowls and presses Save
Then Mobile sends one recalculation command
And Backend persists the new description with recalculated calories, protein, carbs, fat and fiber in one transaction
And Mobile replaces all five displayed fields with the complete response, including explicit nulls

Given the estimate fails or contains no usable nutrients
When the user presses Save
Then the command makes no database change and the editor remains open with a retryable error

Given the saved record changed after the adjustment card was produced
When the user presses Save with the stale record revision
Then Backend returns 409 without a write
And Mobile preserves the user's input, explains that the record must be reopened or refreshed, and does not repeatedly submit the stale revision

Given Mobile retries the same confirmed command after losing the first response
When it sends the same idempotency key and request
Then Backend returns the already committed record without rerunning the estimator
But reusing that key for different content returns 409 without a write

Given the old or corrected meal description indicates alcohol
When the user requests text-based nutrition recalculation
Then Backend rejects it before model work and preserves the original alcohol safety fact

Given the food description is unchanged
When the user edits meal type or a numeric nutrient
Then Mobile saves directly without an estimate request

Given the meal photo gallery is open
When the user performs a qualifying vertical swipe
Then the gallery closes
And a short or horizontal swipe does not close it
And the close button remains available
```

## 6. Verification And Rollout

```bash
cd backend && python3.12 -m pytest tests/test_diet.py -k recalculate_nutrition -q
cd mobile && npm test -- --runInBand components/chat/cards/__tests__/RecordQualityCard.test.tsx components/chat/cards/__tests__/registry.test.tsx
cd mobile && npx tsc --noEmit
./scripts/generate-api-types.sh --check
git diff --check
```

Backend deploy precedes production Mobile OTA. Rollback removes Mobile use of the new command before retiring its backend route; no data migration is involved.

## 7. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-20 | Initial accepted spec | User-observed stale nutrition and modal dismissal defects |
| 2026-08-20 | Replaced client estimate-then-PUT with an atomic server command | Close concurrency, provenance and partial-write gaps found in G2 pressure review |
| 2026-08-20 | Added required revision/idempotency receipts and fail-closed alcohol handling | Make lost-response retries safe and preserve alcohol-related safety facts |
