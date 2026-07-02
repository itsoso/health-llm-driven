# App Review Redlines For 阿衡

This reference adapts the attached Kuaishou App Review checklist to 阿衡. It is an internal operating checklist, not an authoritative Apple policy source.

## Must Be Automated Where Practical

- Reviewer account: credentials are final, login works, seeded data exists, and review flows are reachable.
- Placeholder copy: no visible Beta, temporary, coming soon, under construction, empty-banner, or unfinished-function text.
- iOS-only presentation: no Android, Google Play, APK, or non-iOS platform instructions in iOS-visible UI.
- Payment: no WeChat Pay, Alipay, recharge, cash-out, redeem-code, CDKey, or virtual-good payment path unless the release has an explicit IAP decision.
- Medical boundary: no diagnosis, treatment plan, prescription, dosage adjustment, or self-medication instruction.
- Forced permissions: users must not be required to enable notification, location, tracking, HealthKit, camera, or microphone to use the app as a whole.
- Screenshots: only demo or sanitized data, App Store-ready size, and human-reviewed if sanitized from private QA.

## Manual Review Required

- App Store Review Notes match the actual route/action surface.
- Account deletion path is easy to find and does not require support email as the only path.
- HealthKit and Apple Watch data use is limited to health management, not ads, marketing profiles, resale, or unrelated mining.
- Dynamic UI cards and Agent actions disclose review-relevant functionality and do not hide executable features.
- Permission-denied states preserve the app shell and show a feature-scoped fallback.
- If third-party login is introduced, Sign in with Apple requirements are checked before submission.
- If UGC, lottery, mini apps, H5 games, or plugin marketplaces are introduced, run a separate product/legal review before App Review.

## Current Project Gates

- `scripts/check_app_store_release_pack.py`: release text, privacy, screenshots, demo placeholders, and high-confidence redline scan.
- `scripts/check_ios_app_store_submission.py`: iOS config, HealthKit entitlement, EAS production submit, Watch bundle IDs, encryption, and ASC credentials.
- `docs/release/app-store/screenshot-runbook.md`: screenshot capture, sanitize, prepare, and visual review.
- `docs/release/app-store/review-notes.zh-CN.md`: reviewer steps and boundary disclosure.
