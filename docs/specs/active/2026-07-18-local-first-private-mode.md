# Feature Spec: 本地优先私有模式与完全本地饮食

> Status: implemented; native release validation
> Owner: Codex
> Updated: 2026-07-19
> Related PRD/PDD: `docs/prd/2026-07-18-local-first-private-mode.md`, `docs/prd/reva-personal-health-os-prd.md`
> Related code: `mobile/hooks/useAppSession.tsx`, `mobile/components/local-mode/`, `mobile/services/localDietRepository.ts`, `mobile/services/egressPolicy.ts`, `mobile/modules/local-health-kernel/`

## 1. Decision

Build an iOS-first local identity and encrypted local health kernel, prove it with a fully offline diet capture loop, and make encrypted sync or cloud inference explicit opt-in capabilities rather than prerequisites.

## 2. Problem

Unauthenticated users currently stop at the login screen. Mobile persists credentials, drafts, preferences and a short-lived React Query cache, but the durable health source of truth remains the authenticated backend. This prevents immediate private use and makes the core experience dependent on network and account availability.

If unchanged, Reva cannot honestly claim local-first privacy, cannot serve users who want to validate value before registration, and cannot preserve basic diet capture during outages.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: add a download-and-use local mode, with an optional fully local small-model diet path
  classification: core product architecture and privacy behavior
  first_user_fit: privacy-sensitive frequent meal logger in the existing 35-55 wedge
  core_loop_step: Capture -> WriteIntent -> ExecutionEvent -> HealthTwin -> Review
  first_class_objects: [WriteIntent, ExecutionEvent, HealthTwin, HealthAgendaItem]
  target_surface: [Mobile, iOS native module, optional sync backend]
  source_of_truth: device-local encrypted store for local identities
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: manual_confirm
  evidence_provenance: model candidate plus local food-table source plus user confirmation
  claim_hedging: photo identity and portion remain estimates until confirmed
  verification_window: immediate write receipt plus airplane-mode and reinstall/restore checks
  success_metric: first confirmed meal without registration or network, with zero prohibited egress
  added_user_burden: one confirmation; device passcode required; one-time no-backup warning; optional encrypted export
  burden_justification: protects correctness, locked-device confidentiality and recoverability
  non_goals: [photo-scale precision, diagnosis, prescribing, full Health OS migration, silent cloud account]
  smallest_end_to_end_slice: launch without account -> record one text meal -> local deterministic nutrition -> confirm -> reopen offline -> see same record
  stale_surface_to_remove_or_archive: mandatory login as the only app entry for new local users
  spec_required: yes
```

G1 verdict: **PASS**. The user approved the local-first option and the fully local diet wedge on 2026-07-18.

## 4. Non-Goals

- Android parity in the first slice.
- Exact calories or grams inferred from an unconstrained image.
- Local diagnosis, medication adjustment or replacement of clinician review.
- Migrating existing cloud accounts automatically.
- E2EE multi-device sync before the local single-device data model is proven.
- Bundling an unlicensed nutrition database or an unbenchmarked large model.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `WriteIntent` | A local draft must be confirmed before a durable local record is written. |
| `ExecutionEvent` | Local confirmation, correction, deletion, export and restore emit local audit events. |
| `HealthTwin` | The first local projection is diet-today totals and provenance; broader twin migration is deferred. |
| `HealthAgendaItem` | Later phases may consume confirmed local facts; the first slice does not introduce autonomous recommendations. |

## 6. User Flow

```text
first launch
  -> choose strict local, local-first or cloud account
  -> verify device passcode protection
  -> create device-local identity
  -> capture text/manual/barcode/photo candidate
  -> local parser and food table produce an attributed draft
  -> user corrects or confirms
  -> encrypted LocalDietRecord + local ExecutionEvent
  -> deterministic daily totals
  -> optional encrypted export, sync or one-shot cloud enhancement
```

Strict-local mode must remain usable with networking disabled before launch.

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Mode choice, capture, correction, confirmation, privacy controls, export/restore | Never require an account for the local slice; never show saved without a local receipt. |
| iOS native module | Key management, protected local storage and Chinese-CLIP/Core ML photo candidates | Require device passcode; no plaintext health payload or query metadata in logs/storage; model failures return explicitly and never fall through to cloud. |
| Backend | Preserve existing cloud users; later accept opaque encrypted sync blobs and explicit inference requests | Must not receive local health data unless the user enables a named capability. |
| Watch/Mac/Web | Deferred | Must not imply local data is synchronized before sync ships. |

## 8. Data Contract

```yaml
apis:
  local repositories replace HTTP for local identities
  future POST /sync/v1/envelopes accepts opaque ciphertext only
  future POST /inference/v1/diet-draft accepts an explicit one-shot payload
events:
  local_identity_created
  local_diet_draft_created
  local_diet_record_confirmed
  local_diet_record_corrected
  local_export_completed
  local_restore_completed
  privacy_egress_blocked
models:
  LocalIdentity
  LocalDietRecord
  LocalExecutionEvent
  LocalSyncOutbox
  LocalFoodItem
  LocalFoodNutrient
plaintext_envelope_fields: [local_id, payload_version, object_version, nonce, ciphertext, authentication_tag]
blind_index_fields: [day_blind_index, meal_type_blind_index, lifecycle_blind_index]
encrypted_domain_fields: [record_date, meal_type, provenance, model_profile, created_at, updated_at]
enums:
  app_mode: strict_local | local_first | cloud_account
  inference_path: deterministic | downloaded_model | explicit_cloud
backward_compatibility:
  existing authenticated users stay on the current remote repositories
  no automatic remote-to-local migration in the first release
migration:
  additive native store; no production PostgreSQL migration in the first slice
```

Local record IDs are client-generated and stable. Health content is application-layer encrypted; equality lookups use HMAC blind indexes derived independently from the record-encryption key. The device root key is stored with `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly`; each export re-encrypts into an envelope protected by a new, separately saved App-generated 256-bit recovery key.

## 9. Safety, Privacy, And Medical Boundary

- Diet data and images are sensitive health content.
- Strict-local mode activates a deny-by-default egress policy for authenticated APIs, Sentry content, analytics, push registration and remote configuration.
- Model output is untrusted input and cannot persist without the same sanitation and manual-confirm boundary as the existing diet pipeline.
- Nutrition values require a local, versioned, licensed source; model-recalled nutrient values remain unknown.
- Photos remain in the private app container and default to deletion after recognition unless the user elects to retain them.
- Export must be encrypted and warn that loss of the recovery secret makes recovery impossible.
- Vault creation must fail closed when the device lacks a system passcode; it must not fall back to a weaker Keychain accessibility class.
- Version 1 restore only targets an empty vault and commits after the entire envelope authenticates and validates.
- Local safety logic may warn about invalid values or missing confirmation, but the first slice makes no diagnosis, prescription or causal claim.

## 10. AI Behavior

Allowed:

- extract food names, quantities, units and meal type from text;
- propose visible food identities from a photo;
- ask one narrow clarification for a missing identity or portion;
- call deterministic local food lookup tools;
- produce a typed candidate with confidence and model profile.

Forbidden:

- directly write a record;
- invent nutrient values when the local table has no match;
- promote visual portion estimates to measured quantities;
- send data to cloud when strict-local mode is active;
- hide model unavailability or silently switch inference paths.

The shipped v1 router is deterministic/history for text and the bundled Chinese-CLIP RN50 int8 image tower for photo candidates, followed by mandatory manual confirmation. Apple's system model is not a dependency because the connected target device reported `device_not_eligible`. Explicit cloud enhancement is permitted only in `local_first`, only after a user action, and is blocked entirely in `strict_local`.

## 11. Acceptance Criteria

```gherkin
Given a fresh install with no network
When the user selects immediate local use and records a text meal
Then a confirmed local receipt persists across app restart without registration

Given a fresh install without a device passcode
When the user selects immediate local use
Then vault creation is refused with setup guidance and no local key, identity or health database is created

Given strict-local mode
When any API, telemetry, push-registration or remote-config path attempts health-data egress
Then the request is blocked and a privacy_egress_blocked event is stored locally

Given every Apple system model is unavailable
When the user says "午饭半碗米饭两个鸡蛋"
Then the deterministic parser returns a typed draft and the local food table supplies attributable nutrients

Given a local meal photo
When Chinese-CLIP returns candidates
Then the app shows at most three identities, deletes the picker copy, and writes nothing until the user confirms a separate draft

Given a meal photo with uncertain portion
When local vision identifies candidate foods
Then portion values remain unknown or visibly estimated until the user confirms them

Given the local food database has no licensed match
When a model proposes a food
Then nutrients remain unknown and the app never fabricates exact totals

Given an existing authenticated user upgrades
When the app launches
Then the existing cloud-account flow remains intact and no implicit migration occurs

Given a local export and its App-generated recovery key
When the user restores on a clean install
Then records and audit events are restored with stable IDs and no duplicate confirmations
```

## 12. Verification Plan

```bash
# Mobile JS behavior
cd mobile
npm test -- --runInBand app/__tests__/localMode.test.tsx services/__tests__/localDietRepository.test.ts services/__tests__/egressPolicy.test.ts
npx tsc --noEmit

# iOS native module
cd mobile/modules/local-health-kernel
swift test

# Native build and real-device checks
cd /Users/liqiuhua/work/personal/health-llm-driven
bash scripts/preflight-eas.sh
# New native capability requires TestFlight/local QR build, not OTA.

# Repo hygiene
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
git diff --check
```

Manual gates include airplane-mode first launch, process restart, device lock/unlock, storage pressure, model unavailable, export/restore, network capture showing zero prohibited requests, and lowest-supported-device memory checks.

## 13. Rollout And Rollback

- Ship the selectable modes in a new iOS binary and start with internal devices.
- Keep Chinese-CLIP behind the manual-candidate boundary; never describe it as automatic meal recognition.
- Keep existing remote repositories as the default for authenticated users.
- A model-quality rollback hides the photo button but preserves text/manual capture and all local records.
- Rollback hides local onboarding for new users but must preserve access/export for users who already created local data.
- Local schema migrations are forward-only and versioned; rollback must never delete local health records.

## 14. Open Questions

Non-blocking for the first slice:

- Establish a broader supported-hardware/performance matrix before expanding beyond the current internal cohort.
- Whether E2EE sync is subscription-only.
- Whether retained meal images use a separate user-configurable storage quota.
- Whether Android gets a separate model/runtime strategy.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-07-18 | Initial draft | User approved local-first mode and a fully local diet wedge. |
| 2026-07-18 | Require device passcode; use per-export App-generated recovery keys; select USDA FoodData Central CC0 | User approved the security trade-offs and official source licensing resolved redistribution. |
| 2026-07-19 | Implement selectable modes, encrypted local diet, bundled Chinese-CLIP manual candidates and local data lifecycle | Target iPhone cannot use the Apple system model; user chose the simpler fully local Chinese-CLIP boundary. |
