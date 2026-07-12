# Diet Capture Excellence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a trustworthy, fast, correctable meal capture flow and a premium image-sharing artifact for WeChat and Xiaohongshu.

**Architecture:** Keep vision output probabilistic, then apply deterministic sanitation and reviewed-table calibration before presenting a manual-confirm draft. Persist confirmed records idempotently, remove duplicate image payloads with an owner-scoped server draft, and render confirmed records into a fixed 3:4 share card.

**Tech Stack:** FastAPI, SQLAlchemy/PostgreSQL, pytest, React Native/Expo, TanStack Query, Jest, react-native-view-shot, system Share API.

---

### Task 1: Deterministic food calibration

**Files:**
- Modify: `backend/app/services/food_nutrition_lookup.py`
- Modify: `backend/app/services/ai/food_recognition.py`
- Modify: `backend/app/api/diet.py`
- Modify: `backend/app/schemas/diet.py`
- Test: `backend/tests/test_food_recognition_sanitizer.py`
- Test: `backend/tests/test_food_nutrition_lookup.py`
- Test: `backend/tests/test_diet.py`

1. Add failing tests for embedded Chinese/metric weights, table-authoritative replacement, canonical description and fiber totals.
2. Run the tests and confirm the expected RED failures.
3. Implement quantity parsing and single-request table matching/calibration.
4. Apply calibration in direct Diet API and Agent image path.
5. Run targeted backend tests and commit.

### Task 2: Explainable Mobile draft

**Files:**
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/app/diet.tsx`
- Test: `mobile/app/__tests__/dietCapture.test.tsx`

1. Add failing tests for per-food name, portion, provenance and low-confidence copy.
2. Render structured rows with stable dimensions and one primary confirm action.
3. Keep MealForm as the correction surface and preserve all recognition metadata.
4. Run targeted Jest and TypeScript checks; commit.

### Task 3: Single-upload photo draft and idempotent confirmation

**Files:**
- Modify: `backend/app/api/diet.py`
- Modify: `backend/app/schemas/diet.py`
- Modify: `backend/app/services/private_uploads.py`
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/app/diet.tsx`
- Test: `backend/tests/test_diet.py`
- Test: `backend/tests/test_upload_security.py`
- Test: `mobile/app/__tests__/dietCapture.test.tsx`

1. Define owner-bound expiring photo draft token and cleanup semantics.
2. Add RED tests for cross-user rejection, expiry, one image upload and duplicate confirm.
3. Return a draft reference from recognize; confirm with `Idempotency-Key` and no base64 replay.
4. Add cancel cleanup and recoverable retry state.
5. Run backend/mobile regression and commit.

### Task 4: Premium image share card

**Files:**
- Create: `mobile/components/diet/DietShareCard.tsx`
- Create: `mobile/services/dietShare.ts`
- Modify: `mobile/app/diet.tsx`
- Modify: `mobile/package.json`
- Test: `mobile/components/diet/__tests__/DietShareCard.test.tsx`
- Test: `mobile/services/__tests__/dietShare.test.ts`

1. Add tests for privacy-safe payload, 3:4 layout, long food names and fallback sharing.
2. Add `react-native-view-shot` using the Expo-compatible version.
3. Render 1080x1440 image with a restrained multi-color Reva palette and real meal content.
4. Share the local PNG through the system share sheet; keep text fallback.
5. Verify desktop/mobile view dimensions and commit.

### Task 5: Bounded photo payload and truthful latency

**Files:**
- Create: `mobile/utils/imageUpload.ts`
- Modify: `mobile/hooks/useMediaPicker.ts`
- Modify: `mobile/app/diet.tsx`
- Modify: `mobile/services/clientEvents.ts`
- Modify: `backend/app/api/client_events.py`
- Modify: `backend/app/services/observability_service.py`
- Test: `mobile/app/__tests__/dietCapture.test.tsx`
- Test: `mobile/hooks/__tests__/useMediaPicker.test.ts`
- Test: `mobile/services/__tests__/clientEvents.test.ts`
- Test: `backend/tests/test_client_events.py`
- Test: `backend/tests/test_observability_client_events.py`

1. Add RED tests proving the diet camera does not emit raw 12MP Base64 and emits bounded preparation metrics.
2. Reuse one OTA-safe image helper for chat and diet: longest edge 1568px, JPEG q0.7, no upscale.
3. Start recognition timing after the camera returns and surface a visible image-preparation state.
4. Aggregate p50/p95 from completed events only; expose attempts, failures, cancellations, preparation latency, payload size and privacy-safe correction rate.
5. Run affected Mobile/Backend regressions and commit.

### Task 6: Truthful portion and untrusted-model boundary

**Files:**
- Modify: `backend/app/services/ai/food_recognition.py`
- Modify: `backend/app/schemas/diet.py`
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/types/api.generated.ts`
- Modify: `mobile/app/diet.tsx`
- Test: `backend/tests/test_food_recognition_sanitizer.py`
- Test: `backend/tests/test_food_nutrition_lookup.py`
- Test: `mobile/app/__tests__/dietCapture.test.tsx`

1. Add RED tests for medication/supplement rejection, invalid values, duplicate/model item bounds, portion provenance, operational error preservation and privacy-safe logs.
2. Treat model JSON as untrusted input; whitelist fields, bound values and item count, and recompute totals only from sanitized values.
3. Mark every photo quantity as `vision_estimate` or `unknown`; table calibration must preserve that provenance.
4. Render “表值 × 估算份量” and qualitative identity signals instead of presenting model confidence as a precise probability.
5. Regenerate OpenAPI types and run affected Backend/Mobile regressions before deployment and OTA.

### Task 7: Measurement and release

**Files:**
- Modify: `backend/app/api/diet.py`
- Modify: `mobile/services/clientEvents.ts`
- Modify: `docs/dossiers/2026-07-11-diet-capture-excellence.md`

1. Record privacy-safe stage timings, payload size, confirmation correction flag and share events.
2. Run full affected backend/mobile suites, doc drift and Dossier consistency.
3. Deploy backend, verify health score and production aggregate samples.
4. Build/submit TestFlight because Task 4 adds a native module.
5. Validate build on a physical iPhone with WeChat and Xiaohongshu.
6. Keep camera and single-photo library capture on one state machine; hide capture controls outside idle and verify the real library path in Simulator.
