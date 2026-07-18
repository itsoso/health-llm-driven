# Local-First Private Mode Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver an iOS-first, no-registration, airplane-mode diet capture loop backed by encrypted local storage, with optional on-device intelligence and no implicit cloud egress.

**Architecture:** Add an `AppSession` mode above the existing auth state, introduce repository interfaces so local and remote diet paths do not branch inside UI, and implement a Swift-backed Local Health Kernel for encryption, protected storage and on-device capability probes. The guaranteed path is deterministic/manual; Apple system models, Vision and optional downloaded models enrich drafts but never become the nutrition source of truth.

**Tech Stack:** Expo 55, React Native 0.83, TypeScript, Swift Expo module, CryptoKit, SQLite, Keychain/SecureStore, Apple Foundation Models, Vision/Core ML, Jest, Swift Testing/XCTest, EAS/TestFlight.

---

## Delivery rules

- Execute from a clean worktree based on current `origin/main`; do not use the dirty main workspace.
- Follow strict TDD for every behavior change.
- Keep existing cloud-account users on the current path until a separate migration is approved.
- New native modules and `app.json` changes require a new iOS build; they cannot ship by OTA alone.
- Do not begin Task 2 until Task 1 evidence is recorded in the dossier and G2 is explicitly approved.
- Do not begin sync work until the single-device slice passes G6.

### Task 1: Run G2 feasibility and privacy spikes

**Files:**
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthCapabilityProbe.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthCapabilityProbeTests.swift`
- Create: `docs/evals/local-diet/on-device-eval-contract.json`
- Create: `docs/evals/local-diet/README.md`
- Modify: `docs/dossiers/2026-07-18-local-first-private-mode.md`

**Step 1: Write the failing native capability tests**

Test that the probe returns explicit profiles for system-language-model availability, multimodal availability, Vision availability, OS version and device class. It must return an unavailable reason rather than throwing when Apple Intelligence is disabled.

**Step 2: Run the focused native test and confirm RED**

Run the module test command selected by the spike harness. Expected: FAIL because `LocalHealthCapabilityProbe` does not exist.

**Step 3: Implement the smallest availability-only probe**

Use `#available` guards so the app continues to compile for the current iOS 16 deployment target. Do not perform inference yet.

**Step 4: Define the eval contract**

The JSON contract must capture input modality, expected food identities, allowed aliases, quantity ambiguity, non-food status, correction count, latency, peak memory, thermal state, model profile and OS version. Do not commit private user photos; use licensed or synthetic fixtures.

**Step 5: Run the probe on representative real devices**

Record availability, cold/warm latency and peak memory in the dossier. Expected: an explicit supported-device matrix, not a universal-support claim.

**Step 6: Adjudicate G2**

Security-review the storage/recovery threat model and record the nutrition-data licensing status. If either remains blocked, stop before production implementation.

**Step 7: Commit**

```bash
git add mobile/modules/local-health-kernel docs/evals/local-diet docs/dossiers/2026-07-18-local-first-private-mode.md
git commit -m "test(local-mode): establish on-device feasibility gates"
```

### Task 2: Introduce app session modes without changing cloud users

**Files:**
- Create: `mobile/hooks/useAppSession.tsx`
- Create: `mobile/hooks/__tests__/useAppSession.test.tsx`
- Create: `mobile/services/localIdentity.ts`
- Create: `mobile/services/__tests__/localIdentity.test.ts`
- Modify: `mobile/app/_layout.tsx`
- Modify: `mobile/app/login.tsx`
- Test: `mobile/app/__tests__/localMode.test.tsx`

**Step 1: Write failing tests**

Cover fresh install, “立即开始”, existing token, explicit logout, and local-mode relaunch. Assert that an existing authenticated user still enters `cloud_account` and that a fresh local identity enters the app without calling login APIs.

**Step 2: Verify RED**

```bash
cd mobile
npm test -- --runInBand hooks/__tests__/useAppSession.test.tsx services/__tests__/localIdentity.test.ts app/__tests__/localMode.test.tsx
```

Expected: FAIL because `AppSessionProvider` and local identity storage do not exist.

**Step 3: Implement the typed session contract**

```ts
export type AppMode = 'strict_local' | 'local_first' | 'cloud_account';

export interface AppSession {
  mode: AppMode;
  localIdentityId: string | null;
  cloudUser: User | null;
  canUseCloudInference: boolean;
  canSync: boolean;
}
```

Persist only a random local identifier and mode choice in protected storage. Do not create a server user.

**Step 4: Update the root gate and onboarding**

`AppContent` must render the application shell for valid local sessions and preserve the existing authenticated branch exactly. Non-migrated routes must use a capability boundary rather than silently redirecting to login.

**Step 5: Verify GREEN**

Run the focused tests, then `npx tsc --noEmit`.

**Step 6: Commit**

```bash
git add mobile/hooks/useAppSession.tsx mobile/hooks/__tests__/useAppSession.test.tsx mobile/services/localIdentity.ts mobile/services/__tests__/localIdentity.test.ts mobile/app/_layout.tsx mobile/app/login.tsx mobile/app/__tests__/localMode.test.tsx
git commit -m "feat(mobile): add local-first app sessions"
```

### Task 3: Build the encrypted Local Health Kernel

**Files:**
- Create: `mobile/modules/local-health-kernel/expo-module.config.json`
- Create: `mobile/modules/local-health-kernel/index.ts`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthKernelModule.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthKernel.podspec`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthCrypto.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthStore.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthCryptoTests.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalHealthStoreTests.swift`
- Test: `mobile/modules/local-health-kernel/__tests__/index.test.ts`

**Step 1: Write crypto and lifecycle tests**

Cover AES-GCM round-trip, tamper detection, key absence, device-lock file protection, schema-open failure, transaction rollback and no plaintext content in the database file.

**Step 2: Verify RED**

Run native tests. Expected: FAIL because the module is absent.

**Step 3: Implement the minimal native API**

```ts
export interface LocalHealthKernelApi {
  open(identityId: string): Promise<void>;
  putEncrypted(table: string, id: string, indexes: Record<string, string>, payload: string): Promise<void>;
  getDecrypted(table: string, id: string): Promise<string | null>;
  listDecrypted(table: string, index: string, value: string): Promise<string[]>;
  delete(table: string, id: string): Promise<void>;
  exportEnvelope(recoverySecret: string): Promise<string>;
  restoreEnvelope(uri: string, recoverySecret: string): Promise<void>;
}
```

Use a Keychain-held device key and CryptoKit envelope encryption. Keep health content out of native logs and error descriptions.

**Step 4: Verify GREEN and inspect artifacts**

Run native tests, JS bridge tests and a debug-device inspection proving plaintext meal text is absent from the database file.

**Step 5: Commit**

```bash
git add mobile/modules/local-health-kernel
git commit -m "feat(local-mode): add encrypted local health kernel"
```

### Task 4: Add local diet schema and repository seam

**Files:**
- Create: `mobile/services/dietRepository.ts`
- Create: `mobile/services/localDietRepository.ts`
- Create: `mobile/services/remoteDietRepository.ts`
- Create: `mobile/services/__tests__/localDietRepository.test.ts`
- Create: `mobile/services/__tests__/dietRepository.test.ts`
- Modify: `mobile/services/diet.ts`
- Modify: `mobile/app/diet.tsx`
- Modify: `mobile/hooks/useDietEstimate.ts`

**Step 1: Write failing repository contract tests**

Run the same create/list/update/delete/frequent-food contract against in-memory local and mocked remote implementations. Assert stable client IDs, idempotent confirmation, owner isolation and daily totals.

**Step 2: Verify RED**

```bash
cd mobile
npm test -- --runInBand services/__tests__/localDietRepository.test.ts services/__tests__/dietRepository.test.ts
```

**Step 3: Implement the repository interface**

Keep `mobile/services/diet.ts` as the remote transport. Move UI consumers to a session-selected `DietRepository`; do not add scattered local-mode conditionals.

**Step 4: Implement local records and events**

Store the content payload encrypted. Emit a local append-only execution event in the same transaction as confirmation, correction or deletion.

**Step 5: Verify GREEN**

Run repository tests, existing diet capture tests and TypeScript.

**Step 6: Commit**

```bash
git add mobile/services/dietRepository.ts mobile/services/localDietRepository.ts mobile/services/remoteDietRepository.ts mobile/services/__tests__/localDietRepository.test.ts mobile/services/__tests__/dietRepository.test.ts mobile/services/diet.ts mobile/app/diet.tsx mobile/hooks/useDietEstimate.ts
git commit -m "feat(diet): support local and remote repositories"
```

### Task 5: Package a licensed, versioned local food database

**Files:**
- Create: `mobile/assets/food-nutrition/manifest.json`
- Create: `mobile/assets/food-nutrition/foods.json`
- Create: `mobile/services/localFoodNutrition.ts`
- Create: `mobile/services/__tests__/localFoodNutrition.test.ts`
- Create: `scripts/build_local_food_database.py`
- Create: `backend/tests/test_build_local_food_database.py`
- Modify: `docs/release/app-store/privacy-nutrition-label.draft.json` if required by the final data source

**Step 1: Resolve licensing before adding production rows**

Record source, redistribution terms, version and attribution in the manifest. If licensing is unresolved, use only the existing reviewed seed for tests and keep G2 blocked.

**Step 2: Write failing deterministic lookup tests**

Cover approved aliases, ambiguous aliases, explicit grams, unsupported household units, missing nutrients, source/version provenance and numeric bounds.

**Step 3: Implement the build script and local lookup**

The build must be deterministic and reject rows without provenance. It must not fetch at app runtime.

**Step 4: Verify**

```bash
python3 -m pytest backend/tests/test_build_local_food_database.py -q
cd mobile
npm test -- --runInBand services/__tests__/localFoodNutrition.test.ts
```

**Step 5: Commit**

```bash
git add mobile/assets/food-nutrition mobile/services/localFoodNutrition.ts mobile/services/__tests__/localFoodNutrition.test.ts scripts/build_local_food_database.py backend/tests/test_build_local_food_database.py docs/release/app-store/privacy-nutrition-label.draft.json
git commit -m "feat(diet): add versioned local nutrition data"
```

### Task 6: Deliver the guaranteed offline capture path

**Files:**
- Create: `mobile/services/localDietDraft.ts`
- Create: `mobile/services/__tests__/localDietDraft.test.ts`
- Modify: `mobile/components/diet/MealForm.tsx`
- Modify: `mobile/app/diet.tsx`
- Modify: `mobile/app/__tests__/dietCapture.test.tsx`

**Step 1: Write failing airplane-mode tests**

Cover manual entry, simple Chinese text tokenization, recent/frequent matching, unknown nutrients, correction, confirmation, restart and daily totals. Assert that no API mock is called.

**Step 2: Verify RED**

Run the focused tests and confirm they fail because the local draft pipeline is missing.

**Step 3: Implement deterministic/manual draft creation**

Reuse existing sanitation and confirmation semantics. Preserve unknown values; never use zero as unknown.

**Step 4: Verify GREEN**

Run diet capture, repository, number-format and TypeScript tests.

**Step 5: Commit**

```bash
git add mobile/services/localDietDraft.ts mobile/services/__tests__/localDietDraft.test.ts mobile/components/diet/MealForm.tsx mobile/app/diet.tsx mobile/app/__tests__/dietCapture.test.tsx
git commit -m "feat(diet): record meals fully offline"
```

### Task 7: Add Apple system-model text extraction

**Files:**
- Create: `mobile/modules/local-health-kernel/ios/LocalDietLanguageModel.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalDietLanguageModelTests.swift`
- Create: `mobile/services/localModelRouter.ts`
- Create: `mobile/services/__tests__/localModelRouter.test.ts`
- Modify: `mobile/services/localDietDraft.ts`

**Step 1: Write failing typed-output and fallback tests**

Cover eligible device, Apple Intelligence disabled, model not ready, invalid output, OS model-profile change and strict-local mode. Expected output is a bounded draft with confidence and model profile.

**Step 2: Implement availability-gated guided generation**

Use Foundation Models only behind runtime availability checks. Give the model a local food lookup tool; do not ask it to recall nutrients.

**Step 3: Verify model behavior offline**

Run deterministic unit tests and the licensed/synthetic eval corpus on real devices. Record correction burden and model profile in the dossier.

**Step 4: Commit**

```bash
git add mobile/modules/local-health-kernel/ios/LocalDietLanguageModel.swift mobile/modules/local-health-kernel/ios/LocalDietLanguageModelTests.swift mobile/services/localModelRouter.ts mobile/services/__tests__/localModelRouter.test.ts mobile/services/localDietDraft.ts
git commit -m "feat(diet): parse meal text with on-device models"
```

### Task 8: Add Vision barcode, OCR and candidate-photo paths

**Files:**
- Create: `mobile/modules/local-health-kernel/ios/LocalDietVision.swift`
- Create: `mobile/modules/local-health-kernel/ios/LocalDietVisionTests.swift`
- Create: `mobile/services/localDietVision.ts`
- Create: `mobile/services/__tests__/localDietVision.test.ts`
- Modify: `mobile/app/diet.tsx`
- Modify: `mobile/app/__tests__/dietCapture.test.tsx`

**Step 1: Write failing tests**

Cover barcode/OCR results, non-food images, multiple candidates, low-confidence portion, private photo lifecycle and model unavailability.

**Step 2: Implement Vision-only candidate extraction**

Return candidates and confidence, never authoritative nutrients. Keep images in the private container and apply the configured deletion policy.

**Step 3: Benchmark before adding a downloaded model**

Compare Vision/history/manual against the candidate model on identity precision, correction burden, latency, peak memory, thermal behavior and app size. Do not ship a model that fails the recorded gate.

**Step 4: Verify and commit**

```bash
git add mobile/modules/local-health-kernel/ios/LocalDietVision.swift mobile/modules/local-health-kernel/ios/LocalDietVisionTests.swift mobile/services/localDietVision.ts mobile/services/__tests__/localDietVision.test.ts mobile/app/diet.tsx mobile/app/__tests__/dietCapture.test.tsx
git commit -m "feat(diet): add private on-device vision capture"
```

### Task 9: Enforce strict-local network policy

**Files:**
- Create: `mobile/services/privacyEgressPolicy.ts`
- Create: `mobile/services/__tests__/privacyEgressPolicy.test.ts`
- Modify: `mobile/services/api.ts`
- Modify: `mobile/applib/sentry.ts`
- Modify: `mobile/hooks/useNotifications.ts`
- Modify: `mobile/services/remoteConfig.ts`
- Modify: `mobile/app/settings.tsx`

**Step 1: Write failing deny-by-default tests**

Assert strict-local blocking for health APIs, Sentry health content, analytics, push registration and remote config. Allow only user-initiated update checks if product/privacy review explicitly approves them.

**Step 2: Implement one choke point**

All network clients must consult the same egress policy. A blocked request emits a local audit event without including health payloads.

**Step 3: Verify with packet capture**

Launch in airplane mode and with networking enabled under strict-local mode. Expected: zero prohibited requests.

**Step 4: Commit**

```bash
git add mobile/services/privacyEgressPolicy.ts mobile/services/__tests__/privacyEgressPolicy.test.ts mobile/services/api.ts mobile/applib/sentry.ts mobile/hooks/useNotifications.ts mobile/services/remoteConfig.ts mobile/app/settings.tsx
git commit -m "security(mobile): enforce strict-local data egress"
```

### Task 10: Add encrypted export, restore and data deletion

**Files:**
- Create: `mobile/app/local-data.tsx`
- Create: `mobile/app/__tests__/local-data.test.tsx`
- Create: `mobile/services/localDataLifecycle.ts`
- Create: `mobile/services/__tests__/localDataLifecycle.test.ts`
- Modify: `mobile/app/_layout.tsx`
- Modify: `mobile/app/settings.tsx`

**Step 1: Write failing lifecycle tests**

Cover export, wrong recovery secret, tampered archive, stable-ID restore, duplicate restore, delete-all and read-only recovery from an unsupported schema.

**Step 2: Implement lifecycle UI and service**

Explain that uninstall without export/sync can permanently lose data. Never copy the device key directly into an export.

**Step 3: Verify on a clean install**

Export, delete app, reinstall, restore and compare record/event IDs and totals.

**Step 4: Commit**

```bash
git add mobile/app/local-data.tsx mobile/app/__tests__/local-data.test.tsx mobile/services/localDataLifecycle.ts mobile/services/__tests__/localDataLifecycle.test.ts mobile/app/_layout.tsx mobile/app/settings.tsx
git commit -m "feat(local-mode): add encrypted data recovery"
```

### Task 11: Run release gates and ship the first native cohort

**Files:**
- Modify: `docs/dossiers/2026-07-18-local-first-private-mode.md`
- Modify: `docs/release/app-store/privacy-nutrition-label.draft.json`
- Modify: `docs/release/app-store/review-notes.zh-CN.md`
- Modify: `docs/system-map/product-map.md`
- Regenerate: `docs/_generated/system-map.json` if the generator-owned structure changes

**Step 1: Run G3**

```bash
cd mobile
npm test -- --runInBand
npx tsc --noEmit
cd ..
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
git diff --check
```

Read actual passed/failed output. Do not pipe tests to `tail`.

**Step 2: Run G4 privacy and safety review**

Review encryption, egress, deletion, recovery, photo retention, logs, model claims and existing-user isolation. Any BLOCK returns to the responsible task.

**Step 3: Build a new iOS binary**

Run the project TestFlight or local QR release path. OTA is insufficient because this plan adds native modules.

**Step 4: Run G5/G6 on real devices**

Validate fresh install, airplane-mode first launch, meal capture, model unavailable, process restart, device lock, export/restore and zero prohibited egress. User confirmation is required before G6 PASS.

**Step 5: Commit release evidence**

```bash
git add docs/dossiers/2026-07-18-local-first-private-mode.md docs/release/app-store/privacy-nutrition-label.draft.json docs/release/app-store/review-notes.zh-CN.md docs/system-map/product-map.md docs/_generated/system-map.json
git commit -m "docs(release): record local-first diet rollout"
```

### Task 12: Plan E2EE sync only after the local slice passes G6

This task is intentionally not implementation-ready. After G6, write a separate PRD/spec covering recovery keys, opaque sync envelopes, device enrollment, conflict resolution, tombstones, account deletion and the explicit boundary between ciphertext sync and plaintext one-shot inference. Do not add sync opportunistically to Tasks 1-11.
