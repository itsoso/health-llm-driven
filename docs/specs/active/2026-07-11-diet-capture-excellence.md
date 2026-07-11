# Feature Spec: 饮食打卡极致体验

> Status: active
> Owner: Codex
> Updated: 2026-07-11
> Related PRD/PDD: `docs/prd/2026-07-11-diet-capture-excellence.md`
> Related code: `backend/app/api/diet.py`, `backend/app/services/ai/food_recognition.py`, `mobile/app/diet.tsx`

## 1. Decision

Build one explainable, manual-confirm, idempotent meal capture pipeline and a privacy-safe 3:4 image share artifact.

## 2. Problem

Photo recognition currently exposes a merged summary and model-estimated macros without applying the existing reviewed food table. The same photo payload can be transferred twice, production has no usable recognition latency samples, and social sharing is plain text rather than a desirable image artifact.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: make diet capture best-in-class and shareable to WeChat/Xiaohongshu
  classification: core capture and review behavior
  first_user_fit: frequent mobile meal logger
  core_loop_step: Capture -> Confirm -> Today/Review -> Share
  first_class_objects: [WriteIntent, ExecutionEvent, HealthTwin]
  target_surface: [Mobile, Backend]
  source_of_truth: confirmed DietRecord plus reviewed food nutrition table
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: manual_confirm
  evidence_provenance: per-food source and confidence
  claim_hedging: nutrition values remain estimates unless table-calibrated for explicit weight
  verification_window: immediate write receipt plus 7-day p50/p95 observation
  success_metric: correctable drafts, no duplicate writes, measured latency, successful image share
  added_user_burden: one confirmation or correction action
  burden_justification: prevents incorrect health facts from being silently persisted
  non_goals: [diagnosis, prescription, automatic social posting, scale-grade precision]
  smallest_end_to_end_slice: one photo -> calibrated draft -> manual confirm -> DietRecord id
  stale_surface_to_remove_or_archive: opaque merged draft and text-only diet sharing
  spec_required: yes
```

## 4. Non-Goals

- No automatic record save or automatic social post.
- No WeChat private SDK.
- No medical diagnosis or exact calorie claim from an unconstrained image.
- No broad sleep/workout redesign in this feature.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | Manual confirmation remains the write boundary. |
| `ExecutionEvent` | Confirm/correct/share stages become measurable events. |
| `HealthTwin` | Consumes only confirmed DietRecord facts. |

## 6. User Flow

```text
photo/text/voice -> candidate foods -> deterministic calibration -> visible draft
  -> user corrects or confirms -> idempotent DietRecord receipt
  -> optional privacy-safe image render -> system share sheet
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Capture, explain, correct, confirm and share | Never show persisted success without record id |
| Backend | Sanitize, calibrate, persist and measure | Owner isolation and idempotency required |
| Watch/Rokid | Reuse structured draft later | No automatic write |

## 8. Data Contract

```yaml
apis:
  - POST /diet/recognize returns canonical foods, totals, provenance and photo draft reference
  - POST /diet/records accepts Idempotency-Key and owner-bound photo draft reference
events:
  - diet_capture_stage
  - diet_capture_corrected
  - diet_share_opened
models: existing DietRecord; photo draft storage selected in Task 3
fields:
  - FoodItem.food_id
  - FoodItem.source
  - FoodRecognitionResponse.total_fiber
backward_compatibility: legacy base64 create remains during rollout
migration: only if durable photo draft storage is required after spike
```

## 9. Safety, Privacy, And Medical Boundary

Diet images and nutrition are sensitive health data. Every image path and draft token is owner-scoped. Low-confidence or unweighted results remain labeled estimates. The system never diagnoses, prescribes, or claims scale-grade precision. Sharing requires explicit user action and omits identity, conditions, medication and genetics by default.

## 10. AI Behavior

Vision may propose food identity, display quantity and visual confidence. It must not include UI text as food, invent exact values when uncertain, or directly write records. Deterministic sanitation runs first; reviewed table calibration runs only on matched names with explicit convertible weight; the user confirms last.

## 11. Acceptance Criteria

```gherkin
Given a recognized chicken breast with quantity "200g" and a reviewed table match
When the draft is built
Then macros use the reviewed 200g values and expose the table source

Given an image whose only detected text is a UI nutrition card
When recognition finishes
Then no DietRecord draft is offered

Given a user confirms the same draft twice after a timeout
When both requests carry the same idempotency key
Then exactly one DietRecord exists and both responses identify it

Given a confirmed meal
When the user taps share
Then a 3:4 privacy-safe image opens in the iOS system share sheet
```

## 12. Verification Plan

```bash
PYTHONPATH=backend pytest backend/tests/test_food_recognition_sanitizer.py backend/tests/test_food_nutrition_lookup.py backend/tests/test_diet.py -q
cd mobile && npm test -- --runTestsByPath app/__tests__/dietCapture.test.tsx --runInBand
cd mobile && npx tsc --noEmit
python scripts/check_doc_drift.py
python backend/scripts/check_dossier_consistency.py
git diff --check
```

## 13. Rollout And Rollback

Deploy backend additive response fields before Mobile. Preserve legacy create payload until the new TestFlight adoption is sufficient. Rollback removes Mobile use of provenance/photo draft while legacy recognize/create remain available.

## 14. Open Questions

- Non-blocking: which second visual template should be A/B tested after the first 3:4 card ships?
- Non-blocking: whether to add a licensed external nutrition database after correction-rate evidence.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-11 | Initial active spec | Begin P0 accuracy and explainability implementation |
