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
  - GET /diet/photo-drafts/{token}/status validates a restored owner-bound pending draft
events:
  - diet_photo_recognition_terminal
  - diet_photo_confirmation_terminal
  - diet_share_terminal
models: existing DietRecord; owner-scoped DietPhotoDraft; user-scoped compact SecureStore snapshot
fields:
  - FoodItem.food_id
  - FoodItem.source
  - FoodItem.calibration_names
  - FoodRecognitionResponse.total_fiber
  - diet_photo_recognition_terminal.client_prepare_ms
  - diet_photo_recognition_terminal.payload_bytes
  - diet_photo_confirmation_terminal.corrected
backward_compatibility: legacy base64 create remains during rollout
migrations:
  - backend/migrations/managed/20260711_200000_create_diet_photo_drafts.postgresql.sql
  - backend/migrations/managed/20260711_201000_add_food_calibration_names.postgresql.sql
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

Given confirm and cancel or expiry race for the same photo draft
When the operations execute concurrently
Then a row lock selects exactly one terminal owner and a confirmed record image is never deleted

Given a draft contains an ambiguous alias such as "鸡肉" or "鸡蛋"
When reviewed-table calibration runs
Then the model estimate remains visible for correction and no arbitrary canonical food is claimed

Given a reviewed row has generic canonical name "豆腐" but calibration_names only include "北豆腐" and "老豆腐"
When recognition returns "豆腐 100g"
Then table values do not override the visual estimate

Given the Mobile process terminates while an owner-scoped photo draft is pending
When the same user reopens the diet screen within 24 hours
Then the token is validated as pending before the compact draft is restored without storing or retransmitting image Base64

Given a user changes a recognized food identity but leaves its old macros untouched
When the draft or confirmed record is saved
Then stale macros and AI provenance are cleared while non-nutrition-only edits preserve existing provenance

Given a confirmed meal
When the user taps share
Then an exact 1080x1440 privacy-safe image opens in the iOS system share sheet after its meal image is ready

Given a protected meal image never finishes loading
When five seconds elapse in the share preview
Then the card switches to a complete metric layout and sharing remains available

Given a 4032x3024 camera image on a binary with expo-image-manipulator
When the camera returns the local image URI
Then the app resizes the longest edge to 1568px, encodes JPEG at q0.7 and sends only the resulting Base64

Given recognition events include completed, failed and cancelled attempts
When the observation dashboard computes latency
Then p50/p95 use completed events only while attempts, failures and cancellations remain separately visible
```

## 12. Verification Plan

```bash
PYTHONPATH=backend pytest backend/tests/test_food_recognition_sanitizer.py backend/tests/test_food_nutrition_lookup.py backend/tests/test_diet.py -q
cd mobile && npm test -- --runTestsByPath app/__tests__/dietCapture.test.tsx --runInBand
cd mobile && npm test -- --runTestsByPath hooks/__tests__/useMediaPicker.test.ts hooks/__tests__/useMediaPicker.oldBinary.test.ts services/__tests__/clientEvents.test.ts --runInBand
cd mobile && npx tsc --noEmit
DATABASE_URL=sqlite:///:memory: PYTHONPATH=backend pytest backend/tests/test_client_events.py backend/tests/test_observability_client_events.py -q
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
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
| 2026-07-12 | Bound camera payload and correct latency semantics | Prevent raw-photo memory/network cost and misleading p50/p95 |
