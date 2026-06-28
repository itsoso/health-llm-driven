# App Store MVP Release Batch 2 Plan

> Continuation of `docs/plans/2026-06-28-app-store-mvp-release-plan.md`.

## Goal

Prepare Reva for an App Store submission next week by turning the release requirements into durable repo assets: metadata, privacy nutrition draft, review notes, screenshot runbook, public privacy page, readiness checker, and local screenshot/build evidence.

## Scope

P0 for this batch:

- Public privacy policy URL: `https://health.executor.life/privacy`.
- App Store Connect metadata draft for Chinese submission.
- Privacy nutrition label draft aligned with HealthKit/AI/account deletion wording.
- Review Notes draft with login, HealthKit explanation, medical boundary, and account deletion path.
- Screenshot runbook for iPhone 6.9-inch and iPad/tablet review assets.
- Deterministic checker that compares release materials with `mobile/app.json` and `mobile/eas.json`.
- Simulator build helper that installs a current iOS build without polluting the main checkout.
- Simulator screenshot helper for core Mobile routes.

Deferred:

- Actually submitting to App Store Connect.
- Waiting for App Store processing.
- Full hard-delete worker for account deletion.
- New native entitlements beyond the existing HealthKit/watch/background modes.

## Tasks

### T1: Public Privacy URL

Files:

- `frontend/src/app/privacy/page.tsx`

Acceptance:

- Page states HealthKit use, account deletion path, AI context boundary, and medical non-diagnostic boundary.
- Page is public and indexable enough for App Store Connect.

### T2: App Store Submission Pack

Files:

- `docs/release/app-store/submission-pack.md`
- `docs/release/app-store/privacy-nutrition-label.draft.json`
- `docs/release/app-store/review-notes.zh-CN.md`
- `docs/release/app-store/screenshot-runbook.md`

Acceptance:

- App metadata does not promise diagnosis, treatment, prescription, or drug dosage adjustment.
- Privacy label draft declares Health/Fitness/Contact/User Content/Identifiers/Diagnostics classes and denies tracking/advertising use.
- Review notes include demo account placeholder, HealthKit permission explanation, account deletion path, and reviewer testing path.

### T3: Release Pack Checker

Files:

- `scripts/check_app_store_release_pack.py`
- `backend/tests/test_app_store_release_pack.py`

Acceptance:

- Fails if required files are missing.
- Fails if HealthKit entitlement, required iOS privacy usage strings, `ascAppId`, privacy URL, or medical boundary text drifts.

### T4: Simulator Screenshot Helper

Files:

- `scripts/sim-build.sh`
- `scripts/mobile-sim-screenshots.sh`

Acceptance:

- Builds and installs the simulator app with `ROKID_IOS_SDK_ENABLED=0` and `ROKID_IOS_SIMULATOR=1`.
- Uses a temporary worktree by default so generated iOS Pods and lockfile churn do not dirty the main checkout.
- Captures core route screenshots from a booted simulator when the app is installed.
- Fails loud with the exact build/install command when the app is missing.

### T5: Validation and Release Evidence

Commands:

- `python3 scripts/check_app_store_release_pack.py`
- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_app_store_release_pack.py -q --no-cov`
- `cd frontend && npm run test -- --run src/app/shared/[shareToken]/sharePrivacy.test.ts`
- `cd frontend && npx tsc --noEmit --pretty false`
- `cd mobile && ./node_modules/.bin/jest --runTestsByPath __tests__/app-config.test.ts --runInBand`
- `cd mobile && ./node_modules/.bin/tsc --noEmit`
- `backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `backend/venv/bin/python scripts/check_doc_drift.py`

## App Store Official References

- Account deletion: https://developer.apple.com/support/offering-account-deletion-in-your-app/
- Screenshot specifications: https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/
- App privacy details: https://developer.apple.com/help/app-store-connect/manage-app-privacy/app-privacy-details/
- App Review Guidelines: https://developer.apple.com/app-store/review/guidelines/
