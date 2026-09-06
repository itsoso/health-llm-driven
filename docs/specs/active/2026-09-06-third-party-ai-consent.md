# Feature Spec: Third-party AI consent before data sharing

Status: implementation. Owner: Mobile/backend release. Updated: 2026-09-06.
Parent dossier: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`.

## Decision and admission

Require explicit, versioned, account-scoped permission before sharing personal
health context, messages, images or audio with third-party AI. This repairs the
Apple 5.1.2(i) privacy gap found during the 2026-09-06 review.

RequirementAdmission: privacy maintenance of the HealthTwin / ExecutionEvent
data-use boundary; Mobile owns disclosure and user action, backend owns durable
permission and enforcement. Existing users are not grandfathered into consent.
The user authorized remediation of all review blockers. A single initial
decision and a settings withdrawal entry are justified by sensitive-data use.
This does not change medical advice, prescriptions or health-record precision.

## Flow and contract

Before an AI action, read `GET /auth/ai-consent`. Response:

```typescript
type AIConsent = {
  subject_id: number;
  policy_version: string;
  accepted: boolean;
  accepted_at: string | null;
  recipients: { id: string; name: string; purpose: string }[];
  data_types: string[];
  purpose: string;
};
```

Display the server's recipient, purpose and data categories. Offer explicit
acceptance or declining; do not preselect agreement. Persist through
`PUT /auth/ai-consent` with `{accepted: boolean, policy_version: string}`; the
response uses the same shape. A failed save must not enable transmission.
Web cookie requests bind the disclosed `subject_id` in `X-Reva-AI-Subject`
through consent writes and subsequent AI requests. The backend compares this
assertion with the authenticated actor; it never uses it to choose a target.
A changed cookie or missing assertion fails closed, preventing cross-tab
account changes from granting or sending another account's draft.
Settings exposes the same disclosure and withdrawal. Declining preserves the
draft and access to non-AI records, privacy and account deletion.

Backend reuses a protected key in `UserProfile.privacy_settings`, updates it
under a per-user transaction lock and records an audit event. Ordinary profile
updates cannot forge or erase the protected value. No new table is planned.
Unknown/missing/revoked/stale permission blocks transmission, including old
clients and background jobs. Unknown destinations fail closed; only accurately
disclosed service hosts may receive payloads. Generic public or anonymous jobs
are not implicitly exempted. No patient payload appears in consent logs.

## Acceptance and verification

- New and existing accounts without current permission make zero external AI
  calls. Text, images, speech transcription, TTS and AIGC all check permission.
- Realtime audio rechecks before each upstream audio frame and finish event;
  withdrawal stops subsequent transmission. Already transmitted data cannot be
  retroactively recalled, and disclosure must explain that limit.
- Auto-send cannot bypass the UI or server gate. Account switches cannot reuse
  another user's permission. Database failures deny rather than assume consent.
- Decline/cancel preserves the original draft; withdrawal is only reported
  successful after durable server acknowledgement.
- Verify unit/API tests, PostgreSQL ownership/locking semantics, Mobile Jest
  and TypeScript, full project CI-mode gate, independent safety review, then
  production source and exact iOS candidate. Simulator evidence and old Build
  261 evidence cannot replace new candidate physical-iPhone acceptance.

## Rollout and rollback

Deploy backend permission APIs/enforcement before the new iOS candidate. Old
clients may receive a clear authorization-required error until upgraded; do not
restore unauthorized transmission as a compatibility fallback. Keep existing
records readable. Freeze production OTA through exact-candidate review. Rollback
must preserve the consent privacy boundary and persisted audit history.

## Remaining release evidence

After implementation, complete exact-build screenshots, reviewer login, medical
citations, optional permission refusal, sharing, voice, record correction and
deletion checks; verify ASC privacy declarations/contact/version selection.
Record unavailable external evidence as pending, never synthesize it.

Source: https://developer.apple.com/app-store/review/guidelines/#data-use-and-sharing
