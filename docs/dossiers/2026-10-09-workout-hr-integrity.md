# Garmin heart-rate ingestion integrity

Status: local implementation; not released. Controller: health-harness-orchestrator; overlay: safety-gate.

## Problem and bounded change

Garmin activity details without supported heart-rate samples previously generated a random warm-up/exercise/cool-down curve and stored it in the same field as device samples. Missing native zone durations were calculated against the individual workout peak (or an arbitrary default), which is not a personal physiological maximum.

Remove both fallback paths and their unused helpers. Store a curve only when the existing parser extracts source samples. Keep Garmin's native activity zone durations; do not infer zones without a validated personal threshold and threshold provenance. Native cadence continues to use steps per minute without doubling.

No schema or response-contract changes, production calls, record backfills, authentication changes, helper rebuilds, sync requests, AI endpoints, push, or deployment. Existing nonempty curves and historical zone values remain untouched. Their provenance cannot be established from the current stored fields; this change does not relabel them as real. Zero zone durations remain the existing compatibility representation of no supplied zone information and must not imply zero physiological exposure.

## Validation

Synthetic regression tests first reproduced the two faulty paths: unsupported samples produced a curve, and valid samples with missing native zones generated peak-based zones (2 failed, 2 passed). Coverage includes unsupported/absent samples, source samples, native zones, historical preservation, native cadence units, and central writer cache invalidation.

Fresh final PostgreSQL run: 14 passed, 7 existing deprecation warnings, 27.04 seconds. Coverage for workout_sync is 29%; the targeted sync branches are exercised, not a claim of full service coverage. Evidence: `/tmp/workout-hr-final.log`, `/tmp/workout-hr-final.xml`, `/tmp/workout-hr-final.coverage`. Tests use a disposable local cluster and synthetic records only. An earlier concurrent coverage-report attempt was interrupted and is not completion evidence. System Map check passed against the isolated checkout. Independent safety review follows the fixed local commit. Router external capabilities (karpathy-guidelines, test-driven-development, verification-before-completion) were not installed as skills in this environment; their surgical-change, RED/GREEN, and fresh-evidence principles are followed without claiming skill execution.

## Production rollout boundary

Before release: obtain independent GO for the fixed commit, run required integration/CI gates for the target revision, and obtain deployment authorization. Deploy this bounded writer fix without historical rewriting. Verify on a consented new activity that missing samples remain missing, source samples remain available, cadence is visible, and native zones survive. Rollback reintroduces fabricated-data risk; use a reviewed corrective revision rather than casually reverting this safety fix.

Historical remediation requires a separate design with explicit provenance, original Garmin evidence, API/client missingness semantics, and consented bounded repair. Do not bulk-delete curves or mark all historical curves as measured.

## Stable local helper identity recommendation

Repeated Keychain prompts may follow a changed executable/signing identity; the observed helper rebuild changed its ad hoc identifier. The exact prompt cause has not been verified. Prefer a stable named and signed helper, keep binary identity stable per release, and use the OS authorization interface for that single helper and single Health credential item if the user chooses persistent trust. Do not permit all applications, disable Keychain locking, copy secrets into environment variables, or change ACLs in this task. No promise of zero prompts after reboot or security events.
