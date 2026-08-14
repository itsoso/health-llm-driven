# iOS 1.3.3 App Store Release Design

> **CURRENT FREEZE OVERRIDE (2026-08-12):** this design's build, candidate query, reviewer-login,
> physical-device, final-submit and ASC steps are not executable. Repo-contained production
> writers/observation and `check_app_store_release_pack.py --final-submit` are frozen. Only static
> local materials, Simulator tests and public unauthenticated HTTPS may be inspected, and none can
> produce G5/G6/submission PASS. Reauthorization requires a new dossier and independent G4.

## Decision

Freeze new product work and create a fresh 1.3.3 production Store Build from a reviewed release commit. Remove the hard-coded prescription path, complete exact-build acceptance, update App Store material, submit by Friday, and keep the production OTA channel frozen until the approved build is publicly verified.

The user approved this “review-first, feature-freeze” design in three checkpoints on 2026-08-05.

## Alternatives Considered

1. **Submit existing Build 240.** Rejected. Its Xcode 26.2 / iOS 26.2 toolchain is compliant, but it embeds source from 2026-07-29 and does not represent current product behavior.
2. **Build 1.3.3 while also clearing broad technical debt.** Rejected for this release. Ninety-two lint warnings are worth a later cleanup, but expanding scope would consume exact-build acceptance time.
3. **Freeze features and close only review blockers.** Chosen. It minimizes change while resolving a real medication-safety contradiction and the stale submission pack.

## Current Evidence

- Mobile baseline: 292 suites / 2,399 tests passed; TypeScript passed; lint had zero errors and 92 warnings.
- Production dependency audit: no high or critical advisories.
- Default App Store release-pack and iOS submission checks pass.
- The strict final-submit gate fails because review credentials/contact, current screenshots, real-device evidence, published App Privacy responses, regulated-device confirmation and App Store Connect credentials are not complete.
- Public privacy policy returns HTTP 200 and production health reports API, database, Redis and Celery healthy.
- Build 240 IPA reports version 1.3.2, build 240, `DTXcode=2620` and `DTPlatformVersion=26.2`.
- The Apple public catalog returns no listing for App ID 6763569720 in the checked US/CN storefronts; App Store Connect remains authoritative for actual release state.

## Scope And Freeze Contract

Allowed in 1.3.3:

- medication-safety and review-completeness fixes;
- crashes, login blockers, data loss and submission blockers;
- exact-build tests, screenshots, metadata and operational evidence.

Deferred to 1.3.4:

- new features and experiments;
- broad lint cleanup or refactors;
- Watch, Rokid, Siri or background-location promotion;
- payment, subscription or new data-source work.

Any newly discovered change must be classified as:

```text
review blocker -> may enter 1.3.3 after focused tests and review
non-blocker     -> defer to 1.3.4
scope changing  -> return to G2 and ask the user
```

## Medication Safety Change

The current `RhinitisCard` performs two unsafe operations: it renders specific prescription drugs and fixed doses for every user, then creates missing medication records automatically. It also catches write failures without user feedback.

The release design removes medication creation and direct medication logging from this card. It retains user-owned observations (nasal wash and sneeze count) and provides a generic route to Medication Management. Medication Management remains the only place to record an already-entered drug through a visible user confirmation path.

This is smaller and safer than trying to infer which existing medication treats rhinitis. It also makes the review-note claim—no prescriptions or dosage changes—true in behavior rather than copy only.

## Reviewer Flow

```text
launch exact Store Build
  -> account/password login using dedicated reviewer account
  -> non-empty fictional home and Agent data
  -> text chat works without optional permissions
  -> optional feature requests its permission only after user action
  -> privacy policy and account deletion are reachable in Settings
  -> HealthKit/Garmin are optional demonstrations, not login prerequisites
  -> medical prompts produce explanation, recording or escalation, never prescription
```

The reviewer account must remain active, password-stable and backed by deterministic fictional data during the entire review. Account deletion remains testable: a submitted request stays pending for the documented processing window, so immediate login is not destroyed during review.

## Permission And Capability Boundary

- Camera, photo library, microphone, location, notification and HealthKit prompts remain action-triggered.
- Denial leaves text conversation and manual entry usable.
- The production capability resolver keeps advanced settings, Rokid, Siri, Watch and background location disabled.
- WeChat/Xiaohongshu actions use the iOS share sheet; absence of either app must not dead-end the reviewer.

## Submission Material

The exact build owns one material set:

- six 1290×2796 portrait screenshots: home, Agent, diet capture, trends, device connections, privacy/account control;
- no real name, phone, medication, report, device identifier or other private data;
- review notes with direct login, optional-permission behavior, HealthKit/Garmin purpose, deletion path and medical boundary;
- App Privacy responses matching the checked-in declaration and published in App Store Connect;
- truthful age-rating answers, including health/wellness and medical-treatment information where applicable;
- `Regulated Medical Devices: No`; any `Yes` decision stops the release for regulatory review;
- reviewer contact name, email and reachable phone.

## Release State Machine

```text
FROZEN
  -> CODE_READY        focused fix + G3/G4 green
  -> BUILD_READY       EAS Store Build finished + IPA toolchain verified
  -> ACCEPTED          exact-build physical-iPhone evidence + screenshot review
  -> SUBMITTED         final gate green + App Store Connect submission
  -> APPROVED          Apple approval; still manual release
  -> LIVE              manual release + production smoke
  -> VERIFIED          user confirms G6; OTA freeze may be lifted
```

No state may be skipped. A failure moves back to the cheapest upstream state that can correct it.

## Gate Mapping

| Gate | Release evidence | Failure action |
|---|---|---|
| G1 Admission | Approved PRD/spec, existing Health OS objects, medical/privacy boundary | Reframe scope |
| G2 Feasibility | User-approved freeze, Apple requirements, current code/build audit | Return to design |
| G3 Tests | Focused tests, full Mobile, TypeScript, lint, dependency and release gates | Return to implementation |
| G4 Safety | Independent medication/privacy/auth review | BLOCK and remediate |
| G5 Deployment health | Store Build processed, IPA verified, TestFlight/exact-build smoke, backend healthy | Do not submit |
| G6 Live verification | Public App Store version, login/core flow, service health, user confirmation | Pause rollout or hotfix |

## Schedule

### Wednesday, 2026-08-05

- Freeze 1.3.3 and establish a clean release base from `origin/main`.
- Implement the medication-safety slice with tests.
- Add missing final-gate evidence for age rating and exact toolchain.
- Prepare the dedicated review account and fictional data.
- Run G3 and G4.

### Thursday, 2026-08-06

- Build the new production Store Build asynchronously.
- Inspect the IPA version, build number, Xcode and iOS SDK fields.
- Submit to TestFlight processing.
- Run automated and manual physical-iPhone acceptance on that exact build.
- Capture and visually inspect the six screenshots.
- Complete App Store Connect privacy, age rating, regulated-device and review-detail fields.

### Friday, 2026-08-07

- Run the strict final-submit gate with external secrets/evidence.
- Reconcile build ID, commit, screenshots and notes one final time.
- Submit by midday America/New_York if every gate is green.
- Monitor reviewer access and production services.

### Weekend

- Respond to review questions within two hours when awake/available.
- Metadata issue: correct and reply.
- Login/environment issue: restore first, then send evidence.
- Code, privacy or medical issue: stop, create the next build, and resubmit.
- After approval, perform manual release and production G6 verification.

## OTA And Rollback

The `production` OTA channel is frozen from the release commit until public G6 passes. The Store Build must embed the reviewed code and may not rely on OTA on first launch.

- Before submission: a failed build or acceptance run is discarded.
- During review: a code fix produces a new Store Build; do not mutate reviewer behavior through OTA.
- After approval but before manual release: do not release if production health is degraded.
- After public release: use remote configuration only to disable a dangerous surface; use OTA only for a reviewed JS emergency fix, and create a new native build for native/config changes.

## Authoritative Apple References

- [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/)
- [App Review overview](https://developer.apple.com/app-store/review/)
- [Upcoming requirements](https://developer.apple.com/news/upcoming-requirements/)
- [Protecting HealthKit privacy](https://developer.apple.com/documentation/healthkit/protecting-user-privacy)
- [App privacy](https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/)
- [Account deletion](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
- [Screenshots](https://developer.apple.com/help/app-store-connect/manage-app-information/upload-app-previews-and-screenshots/)
- [Regulated medical device status](https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status)
