# Feature Spec: Rokid CustomApp Install For Push-up Pose

> Status: implemented first slice
> Owner: Reva
> Updated: 2026-06-18
> Related PRD/PDD: `docs/plans/2026-06-18-rokid-pushup-real-data-integration.md`
> Related code: `mobile/modules/rokid-bridge`, `mobile/app/rokid-pushup-coach.tsx`, `apps/rokid-pushup-glasses`
>
> **Current release override (2026-08-12):** all OTA/rollback channels and production native/Rokid
> writers are frozen. EAS preview/development is not a trusted isolation boundary. The tracked
> `gradlew`/`gradlew.bat`, release/debug-sign build, Android Studio build, ADB install, physical
> iOS/Rokid bridge connection/install/acceptance are all frozen. There is no reviewed unsigned
> compile/test wrapper, so this spec does not claim local Rokid compile/test is available. Manual
> external Gate is BLOCK pending a new repo-external trust-root dossier and independent G4.

## 1. Decision

Build a Mobile-controlled CXR-L install path for the Rokid push-up glasses APK, so Reva can install or update `life.executor.health.rokid.pushup` without USB/ADB.

## 2. Problem

Rokid Glasses may not expose a usable USB-C / ADB path through the charging case. The current real pose recognition flow requires an Android APK on the glasses before iOS can call `openApp`, so users can be blocked before reaching the Health OS loop.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: install or update Rokid glasses push-up app through Reva iOS CXR-L
  classification: new_product_behavior
  first_user_fit: high-intensity worker using wearables and glasses for low-friction exercise execution
  core_loop_step: Mobile / glasses execution event
  first_class_objects:
    - LeverageAction
    - ExecutionEvent
    - WriteIntent
  target_surface:
    - Mobile
    - Rokid Glasses
  source_of_truth: Reva backend push-up session plus glasses APK package identity
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: CXR-L SDK installApp/queryApp/openApp callbacks plus backend pose/rep ingest
  claim_hedging: n/a
  verification_window: same session
  success_metric: glasses app installed, opened, and posts at least one pose or rep event
  added_user_burden: one explicit install/update tap, or APK file picker fallback
  burden_justification: replaces USB/ADB setup and is required before real glasses recognition
  non_goals:
    - no video upload to Reva
    - no medical diagnosis
    - no autonomous workout prescription change
    - no App Store distribution of the glasses APK as an iOS binary
  smallest_end_to_end_slice: query app -> install bundled/file APK -> re-query -> create session -> open app -> poll events
  stale_surface_to_remove_or_archive: none
  spec_required: yes
```

## 4. Product Object Mapping

| Object | Change |
|---|---|
| `LeverageAction` | "Start 20 push-ups" can now prepare its glasses execution surface. |
| `ExecutionEvent` | Real `pose` / `rep` events remain backend-ingested after app launch. |
| `WriteIntent` | Installing the glasses app is an explicit manual-confirm device write. |

## 5. User Flow

```text
Rokid push-up screen
  -> query glasses package
  -> if missing, install bundled APK or selected APK file through CXR-L
  -> re-query package
  -> create backend push-up session
  -> open glasses CustomApp with session URL
  -> glasses posts pose / rep events
  -> Mobile updates count and saves exercise
```

## 6. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Control install, launch, stop, and event polling. | Calls CXR-L only after Rokid authorization; exposes explicit install/update. |
| Rokid Glasses | Run the Android CustomApp. | Package `life.executor.health.rokid.pushup`, activity `.MainActivity`, posts session events. |
| Backend | Own session and event ingest. | Short session token for writes; JWT for reads. |

## 7. Data Contract

```yaml
apis:
  native_ios:
    - installBundledApp(resourceName, resourceExtension, packageName)
    - installAppFileUri(fileUri, packageName)
    - uninstallApp(packageName)
events: existing rokid_pushup_events
models: no database model change
fields: no backend field change
enums: no enum change
backward_compatibility: existing query/open/stop flows continue to work
migration: native rebuild required; OTA cannot add the bridge methods
```

## 8. Safety, Privacy, And Medical Boundary

This feature touches device control and exercise health data, but does not upload camera video and does not make medical claims. The APK install action is manual-confirm only. The backend still enforces session-token write scope and user-owned reads.

## 9. Acceptance Criteria

```gherkin
Given Reva iOS is authorized with Rokid CXR-L
When the user starts real push-up recognition and the glasses app is missing
Then Reva installs the APK before creating and opening the real pose session

Given the iOS bundle does not contain the APK
When the user taps install/update
Then Reva can install a user-selected APK from iPhone Files

Given the APK is installed
When Reva opens the glasses app with a session URL
Then the glasses app can post pose/rep events to the session ingest endpoint
```

## 10. Verification Plan

```bash
cd mobile
npm test -- --runTestsByPath modules/rokid-bridge/__tests__/rokidBridge.test.ts app/__tests__/rokid-pushup-coach.test.tsx --runInBand

cd ..
git diff --check
```

Future external manual-device Gate (**BLOCKED / DO NOT EXECUTE during the freeze**):

1. Install a native Reva build with `ROKID_IOS_SDK_ENABLED=1`.
2. Complete Rokid authorization in Reva.
3. Open Rokid push-up screen.
4. Tap "安装/更新眼镜端 App"; use bundled APK if present or select APK from Files.
5. Tap "启动眼镜识别".
6. Verify package query, app open, and backend pose/rep events.

## 11. Rollout And Rollback

OTA cannot carry this change because it adds native bridge methods, and every OTA channel is frozen
anyway. Validate JS/UI integration only with local Metro/iOS Simulator; `npm run ios` uses the
Simulator wrapper, callers may not append npm/Expo `--device`, and the wrapper pins an exact
available Simulator UDID. Physical iOS/Rokid connection, install and acceptance are frozen. Do not
archive/export/sign/provision a new build. The Rokid automatic production native entrypoint is
frozen; manual Gate means BLOCK regardless of candidate visibility. The tracked Gradle wrappers,
Android Studio, release/debug-sign builds and ADB/manual install are not development fallbacks.
Without a reviewed unsigned compile/test wrapper, local Rokid compile/test is not an allowed surface.

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-18 | Initial implementation spec | Replace blocked USB/ADB install path with CXR-L install. |
