# Garmin compound query and attachment release

- Status: implementing; controller: health-harness-orchestrator; overlay: safety-gate.
- Trace: `docs/_generated/harness-runs/9a1dc5f7c4a7.jsonl`.
- User authorized fixes, backend deployment and production OTA. Baseline main `2f6cf0192` has green CI `34709530529`.
- Work takes place in the pre-existing clean main clone, preserving unrelated dirty root changes. Only the prior ChatInputBar attachment redesign is imported from root.

## Scope and acceptance

Restore existing owned reads and sync actions, without expanding to other people, historical sync windows, cancellation, quoted instructions or implicit synchronization. Accept the reported sleep + sync-status question and explicit imperative paraphrase. Last-night sleep uses wake-day attribution in the authenticated user's timezone.

The credential status endpoint can report binding, invalid credentials/MFA, enabled state, errors and last successful sync time. It cannot attest completion of a particular queued job. Preserve that uncertainty; neither data coverage nor an older success timestamp proves that the just-requested task finished. Read status without submitting another job or disclosing credentials.

Mobile: release the previously implemented inline attachment tray, with no title row or modal scrim, retaining all four existing actions and dismiss controls. Simulator is the default verification surface; no phone dependency.

## Gates

## Fresh implementation evidence

- Compound read first-red: 4 failed / 5 passed; explicit sync phrase first-red: 4 failed / 22 passed. Fixed regressions: 51 passed on isolated UTF-8 PostgreSQL, including public Pi transport/history, authenticated credential reads, owner isolation and malformed/secret-bearing status projection.
- Wider policy regression: 2206 passed; calendar/read-plan set: 95 passed / 6 PostgreSQL-only skipped (owner test separately passed on PostgreSQL). System Map regenerated and check passed; no schema or public API type changes.
- Mobile initial wider regression: 164 passed and TypeScript passed. Actual simulator Release candidate verified compact four-action tray, no title/scrim, close and keyboard dismissal. Downward swipe did not pass first actual check; repair and fresh candidate verification remain required.
- Production preflight: exact runtime `deab5edcd6f6853c34cd6bbb2f6d94043001b159`; backend, celery-worker and celery-beat active; no release lock. No production mutation yet.

- G3 pending: first-red tests, focused policy and actual execution regressions, PostgreSQL owner isolation, mobile tests/typecheck/simulator, source-bound model gate and CI-mode integration.
- G4 pending: independent fixed-commit safety review.
- G5 pending: exact main CI, clean backend deployment and OTA boundary checks.
- G6 pending: production runtime/health verification and OTA manifest serving. Do not claim device activation without evidence.
