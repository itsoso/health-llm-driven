---
name: ios-app-review-gate
description: "Use when preparing, auditing, or debugging 阿衡 iOS App Store review, TestFlight-to-submission readiness, App Review rejection fixes, reviewer account access, screenshot privacy, HealthKit/privacy/medical/payment redlines, or release-pack preflight."
---

# iOS App Review Gate

Use this skill as the final App Store review gate for `mobile/`. It converts App Review risk into explicit checks before a build is submitted.

## Workflow

1. Read `docs/system-map/INDEX.md`, `docs/release/app-store/submission-pack.md`, and `docs/release/app-store/adapted-review-checklist.md`.
2. Confirm scope:
   - Pure JS/TS/mobile UI changes can ship by OTA, but App Store submission still needs this gate.
   - Native/plugin/Info.plist/HealthKit/Watch changes also need `mobile-testflight-release`.
3. Run the no-secret gate:
   ```bash
   python3 scripts/check_app_store_release_pack.py
   python3 scripts/check_ios_app_store_submission.py
   ```
4. For final submission only, require human materials:
   ```bash
   python3 scripts/check_app_store_release_pack.py \
     --final-submit \
     --screenshot-dir design/screenshots/app-store/<build-id>-ready
   python3 scripts/check_ios_app_store_submission.py --require-asc-credentials
   ```
5. Visually inspect screenshots. Sanitized screenshots from private QA are not ready until `prepare_app_store_screenshots.py --confirm-sanitized-reviewed` has been run after human review.
6. Verify reviewer access: demo credentials replaced, login succeeds, seeded data exists, and the reviewer can reach every flow named in Review Notes without MFA, risk-control blocks, or blank pages.

## Redlines

Read `references/app-review-redlines.md` when changing visible copy, dynamic cards, action routing, auth, payments, HealthKit, permissions, screenshots, or Review Notes.

High-confidence automated redlines live in `scripts/check_app_store_release_pack.py`. Do not weaken a rule just to pass a release; either remove the review risk from the product surface or narrow the scanner only when it is catching non-user-visible implementation code.

## Dynamic UI Inventory

For Agent Native / DynamicView work, compare the actual executable surface with Review Notes:

- `mobile/app/**` routes and deep links.
- Dynamic cards, action registries, and feature flags.
- HealthKit, camera, microphone, notification, and location permission paths.
- Any generated content that can mention diagnosis, prescription, dosage, payment, or incentives.

If a reviewer can trigger a user-visible flow, the flow must be disclosed or safely reachable during review.

## Stop Conditions

Stop before submission when:

- Demo account cannot be verified end-to-end.
- A listed route/action opens a blank page or wrong surface.
- The app contains placeholder/Beta/temporary visible copy.
- iOS-visible UI mentions Android or third-party app stores.
- Any virtual-good/payment/redeem-code language appears without an IAP decision.
- Health guidance implies diagnosis, treatment, prescription, or dosage adjustment.
- Permission denial dead-ends the whole app instead of the specific feature.

This skill is based on an internal Kuaishou checklist adapted for 阿衡. Treat that checklist as operational experience, not Apple policy; verify current policy against Apple documentation when changing hard gates.
