# iOS App Review Adapted Checklist

> Purpose: adapt proven App Review operating practices into 小巴's release gate. This is not a generic checklist; it is the repo-level contract for what must be checked before App Store submission.

## Automated Gate

Run before every iOS submission:

```bash
python3 scripts/check_app_store_release_pack.py
```

The gate must fail on high-confidence review risks:

- iOS submission materials or iOS-visible UI copy mentioning Android, Google Play, or other non-iOS platform surfaces.
- Third-party payment, recharge, withdrawal, redeem-code, CDKey, WeChat Pay, or Alipay wording in iOS-visible copy unless a reviewed entitlement and legal basis exist.
- Permission copy that implies notification, location, tracking, microphone, camera, or HealthKit access is mandatory for the whole app.
- Unfinished product copy such as "coming soon", placeholder pages, or construction-state screens.
- Medical copy that sounds like diagnosis, prescription, treatment plan, dosage adjustment, or self-directed medication change.

## Manual Submission Gate

Before upload or submit for review, the release owner must check:

- Review Notes explain what 小巴 does, what it does not do, and where the reviewer can find the main flows.
- Demo account, reviewer path, and any required seed data are reachable without private owner-only state.
- Screenshots contain no private health data, phone numbers, raw identifiers, internal tools, debug overlays, or non-production environment labels.
- HealthKit, notification, microphone, camera, and location permission prompts are contextual and optional unless the user explicitly starts that feature.
- Any paywall, subscription, or purchase copy uses Apple-compliant wording and does not route to external payment.
- Medical boundary is visible: 小巴 provides health records, trend interpretation, and lifestyle suggestions, not diagnosis, emergency triage, prescriptions, or medication-dose decisions.
- The standard binary is iPhone portrait only and does not contain Watch, Rokid, Siri intents or background location capabilities.
- A physical iPhone has passed both voice paths, photo persistence, database write verification, and WeChat/Xiaohongshu share handoff.

## Borrowed Practices

The Kuaishou review checklist is useful for Aheng in four ways:

- Treat review as an operating system, not a last-minute form fill. Submission materials, screenshots, reviewer paths, and feature switches should be managed as release artifacts.
- Scan the whole iOS-visible surface for forbidden cross-platform, payment, permission, unfinished, or unsafe medical wording before review.
- Keep reviewer access boring and deterministic: reviewer notes, demo account, data state, and navigation path must match the submitted binary.
- Convert repeated rejection classes into repo gates or reusable skills instead of keeping them as tribal knowledge.

## 小巴 Mapping

| Review Risk | Aheng Surface | Required Control |
| --- | --- | --- |
| Cross-platform copy leaks | Mobile screens, release docs | Automated redline scan |
| External payment or redeem code | Subscription, account, settings, release docs | Automated redline scan plus manual paywall review |
| Forced permissions | Onboarding, recording, HealthKit, notification prompts | Contextual request only; no app-wide blocking copy |
| Empty or unfinished pages | Settings, detail routes, dynamic cards | No dead-end route in submitted build |
| Unsafe medical claims | 小巴 chat, DynamicView cards, health reports | Medical boundary copy plus deterministic safety rules |
| Reviewer cannot reproduce core flow | Review Notes, demo account, seed data | Final-submit gate and manual reviewer walkthrough |

## Skill Sedimentation

Use `.claude/skills/ios-app-review-gate/SKILL.md` whenever a task involves:

- iOS App Store submission.
- App Review rejection analysis.
- Review Notes or screenshot preparation.
- Privacy nutrition labels, permission prompts, reviewer account access, or medical-boundary copy.
- Any iOS-visible dynamic UI/action card that could introduce review-sensitive wording.

If a new rejection class appears, update both this checklist and `scripts/check_app_store_release_pack.py` when the rule can be detected with high confidence.
