# Feature Spec: 饮食打卡极致体验

> Status: active
> Owner: Codex
> Updated: 2026-08-01
> Related PRD/PDD: `docs/prd/2026-07-11-diet-capture-excellence.md`
> Related code: `backend/app/api/diet.py`, `backend/app/services/ai/food_recognition.py`, `mobile/app/diet.tsx`

## 1. Decision

Build one explainable, idempotent meal-capture pipeline and a privacy-safe 3:4 image share artifact. A user-originated chat food photo may be saved automatically only when structured vision evidence is high-confidence and the user's local time is within a normal meal window; every other candidate remains an editable, current-page confirmation.

This feature is an Agent Native, Mobile First capture path. Camera, library, text and voice are input modalities for the same Xiaoba conversation chain, not separate product silos. A valid implementation must leave the Agent with enough confirmed context to explain the meal, answer follow-up questions, update daily progress and propose the next action.

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
  autonomy_tier: constrained_auto_for_qualified_chat_food_photo_else_manual_confirm
  evidence_provenance: per-food source and confidence
  claim_hedging: reviewed tables calibrate nutrient density, while photo portions remain visual estimates until user confirmation
  verification_window: immediate write receipt plus 7-day p50/p95 observation
  success_metric: correctable drafts, no duplicate writes, measured latency, successful image share
  added_user_burden: zero for qualified high-confidence meal photos; one confirmation or correction action otherwise
  burden_justification: removes routine logging friction without treating low-confidence, out-of-window or analytic images as health facts
  non_goals: [diagnosis, prescription, automatic social posting, unbounded keyword-driven auto-save, scale-grade precision]
  smallest_end_to_end_slice: one chat photo -> contextual policy -> verified DietRecord receipt or current-page draft -> photo-backed history
  stale_surface_to_remove_or_archive: opaque merged draft and text-only diet sharing
  spec_required: yes
```

## 4. Non-Goals

- No automatic save outside the qualified chat-photo policy or automatic social post.
- No WeChat private SDK.
- No first-version automatic QR or barcode detection; privacy redaction is an explicit local user action.
- No medical diagnosis or exact calorie claim from an unconstrained image.
- No broad sleep/workout redesign in this feature.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | Qualified chat food photos can form a constrained, server-verified write; every other photo remains a manual confirmation. |
| `ExecutionEvent` | Confirm/correct/share stages become measurable events. |
| `HealthTwin` | Consumes only confirmed DietRecord facts. |

## 6. User Flow

```text
camera/library/text/voice -> candidate foods -> deterministic calibration
  -> qualified chat food photo + local meal window + high confidence -> verified DietRecord receipt
  -> every other food candidate -> visible draft -> user corrects or confirms -> idempotent DietRecord receipt
  -> optional privacy-safe image render -> system share sheet
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Capture, explain, correct, confirm and share | Never show persisted success without record id; no standalone analysis path detached from Xiaoba; a confirmed meal with an owner-accessible photo opens a local 3:4 editor with crop, 90-degree rotation and opaque privacy redaction before full poster preview; preview, save and system share reuse one rendered URI |
| Agent Conversation | Preserve context, follow up, compare against today/yesterday and suggest next action | Must consume confirmed DietRecord facts or pending draft context, not unconfirmed guesses as truth |
| Backend | Sanitize, calibrate, persist and measure | Owner isolation and idempotency required |
| Watch/Rokid | Reuse structured draft later | No automatic write |

## 8. Data Contract

```yaml
apis:
  - POST /diet/recognize returns canonical foods, totals, provenance and photo draft reference
  - POST /diet/records accepts Idempotency-Key and owner-bound photo draft reference
  - GET /diet/photo-drafts/{token}/status validates a restored owner-bound pending draft
  - GET /diet/records returns ordered `photo_assets` and `image_urls`; legacy `image_url` remains the cover compatibility field
events:
  - diet_photo_recognition_terminal
  - diet_photo_confirmation_terminal
  - diet_share_terminal
models: existing DietRecord; owner-scoped DietPhotoDraft; authoritative owner-scoped DietPhotoAsset; user-scoped compact SecureStore snapshot
fields:
  - FoodItem.food_id
  - FoodItem.source
  - FoodItem.calibration_names
  - FoodItem.portion_basis
  - FoodItem.portion_confidence
  - FoodRecognitionResponse.total_fiber
  - diet_photo_recognition_terminal.client_prepare_ms
  - diet_photo_recognition_terminal.payload_bytes
  - diet_photo_confirmation_terminal.corrected
  - DietPhotoAsset.storage_key (canonical private path only, never a signed URL)
  - DietPhotoAsset.origin_message_id + ordinal (chat-image idempotency)
backward_compatibility: legacy base64 create remains during rollout
migrations:
  - backend/migrations/managed/20260711_200000_create_diet_photo_drafts.postgresql.sql
  - backend/migrations/managed/20260711_201000_add_food_calibration_names.postgresql.sql
  - backend/migrations/managed/20260719_180000_create_diet_photo_assets.postgresql.sql
```

## 9. Safety, Privacy, And Medical Boundary

Diet images and nutrition are sensitive health data. Every image path and draft token is owner-scoped. `DietPhotoAsset.storage_key` stores only a canonical private path; short-lived signed URLs are made only at response time and are stripped from durable conversation metadata. Recognition model content and food names are excluded from service logs. Low-confidence or unweighted results remain labeled estimates; a reviewed-table nutrient match never promotes a visual portion into a measured value. The system never diagnoses, prescribes, or claims scale-grade precision. Sharing requires explicit user action and omits identity, conditions, medication and genetics by default.

## 10. AI Behavior

Vision may propose food identity, display quantity, identity confidence and portion confidence. It must not include UI text, medication or supplements as food, invent exact values when uncertain, or directly write records. A typed semantic-intent boundary, not raw text keyword/regular-expression matching, classifies a photo as implicit capture, explicit capture or analysis-only. Deterministic sanitation bounds fields, values and item count before reviewed-table calibration; calibration runs only on matched names with explicit convertible weight and preserves `portion_basis=vision_estimate`. The policy permits automatic persistence only for user chat uploads recognized as food at or above the threshold, within user-local breakfast/lunch/dinner windows, and clear of a source-message/image-ordinal duplicate. All other food candidates require confirmation.

## 11. Acceptance Criteria

```gherkin
Given a recognized chicken breast with quantity "200g" and a reviewed table match
When the draft is built
Then macros use the reviewed 200g values, expose the table source and still label the 200g portion as a visual estimate

Given a model returns medication, supplements, duplicate foods or invalid negative nutrients
When deterministic sanitation runs
Then non-food and duplicate items are removed, invalid values become unknown and no model content appears in service logs

Given a provider timeout or rate limit occurs before foods are returned
When the API sanitizes the failure response
Then the actionable retry error is preserved and is not replaced with a false no-food message

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

Given a confirmed meal has an owner-accessible photo
When the user opens the Xiaohongshu share composer
Then the original meal photo is loaded into a local 3:4 editor before poster preview

Given the meal photo is absent or cannot be loaded
When the user requests an image share
Then no image poster is generated and the UI offers retry or share text

Given the user adds a privacy-redaction stroke
When the 1080x1440 PNG is generated
Then the exported pixels contain the opaque redaction and the original DietRecord photo is unchanged

Given a 4032x3024 camera image on a binary with expo-image-manipulator
When the camera returns the local image URI
Then the app resizes the longest edge to 1568px, encodes JPEG at q0.7 and sends only the resulting Base64

Given recognition events include completed, failed and cancelled attempts
When the observation dashboard computes latency
Then p50/p95 use completed events only while attempts, failures and cancellations remain separately visible

Given the camera is unavailable or a meal photo already exists
When the user selects one image from the diet photo library action
Then it uses the same bounded preparation, recognition, recoverable draft and manual-confirm pipeline as the camera

Given the user opens the image-only system photo picker
When Mobile starts library selection
Then it does not request broad photo-library access before the user explicitly selects one image

Given a backend-sanitized photo candidate contains a food name such as "橙子片"
When Mobile opens the photo draft
Then the generic character "片" is not reclassified as medication while text, voice and external drafts keep the Mobile intake guard

Given any diet entry starts from camera, library, text or voice on Mobile
When the user confirms or asks a follow-up
Then the Agent conversation can reference the pending draft or confirmed DietRecord, and Mobile does not create a second detached analysis or record source

Given a user sends a high-confidence food photo to Xiaoba at 12:30 in their configured local timezone
When the contextual policy receives implicit-capture intent and a clear source-message/image-ordinal key
Then exactly one DietRecord and one attached DietPhotoAsset are created and the chat emits a verified record receipt

Given the same food photo is sent at 03:30, has low confidence, is non-food, or asks only for analysis
When the contextual policy evaluates it
Then the food candidate is either an editable current-page confirmation or no write candidate, and no automatic DietRecord is created

Given a chat photo is persisted as an automatic record or a confirmed draft
When the user opens diet history on Mobile or Web, or sees the current confirmation in Mac chat
Then its owner-scoped photo is available through a read-time signed URL, while no signed URL is stored in the database or durable conversation cache

Given photo selection, recognition, correction, confirmation or saving is active
When the diet screen renders capture controls
Then the floating add action is hidden so content stays visible and a second capture cannot start concurrently
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

Deploy backend additive response fields and the photo-asset migration before clients. Preserve legacy create payload and `image_url` cover compatibility until all clients consume `photo_assets`. Rollback removes client use of the new fields while legacy recognize/create remain available; it never copies signed URLs into stored data.

## 14. Open Questions

- Non-blocking: which second visual template should be A/B tested after the first 3:4 card ships?
- Non-blocking: whether to add a licensed external nutrition database after correction-rate evidence.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-11 | Initial active spec | Begin P0 accuracy and explainability implementation |
| 2026-07-12 | Bound camera payload and correct latency semantics | Prevent raw-photo memory/network cost and misleading p50/p95 |
| 2026-07-12 | Separate nutrient calibration from portion truth | Prevent table matches and model confidence from implying measured-photo precision |
| 2026-07-12 | Add a single-photo library path and idle-only capture controls | Make fallback actionable without duplicate pipelines or overlapping concurrent capture UI |
| 2026-07-19 | Add constrained contextual chat-photo auto capture and `DietPhotoAsset` ledger | Remove routine meal logging friction without turning analysis, low-confidence or out-of-window images into silent health writes |
| 2026-08-01 | Require an editable meal photo for the Xiaohongshu poster | Replace the metric-only fallback with local crop, rotation, opaque redaction and one-render preview/save/share reuse |
