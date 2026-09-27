# Exercise plan authority / evidence boundary repair

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 verification / release preparation |
| Last reviewed | 2026-09-27 |

## G1 Request and admission

裁决: PASS

- Bugfix / engineering maintenance: authenticated self exercise-plan requests
  were rejected as reads of another person's records.
- Objects: HealthProtocol / LeverageAction drafts, SafetyGuardian boundaries.
- Backend is source of truth. No new persistence, API, schema, mobile permission,
  notification, diagnosis, medication advice or autonomous execution surface.
- Restore existing plan-draft behavior; explicitly stated evidence may be read,
  a draft alone does not authorize additional personal-history reads.
- User requested repair and architectural explanation, not a new deployment in
  this turn. Unrelated location-sharing work remains untouched.

## Evidence and cause

- Previous read-only production diagnosis matched the three reported turns to
  `health_query_subject_not_current_user`; no user identities/payloads retained.
- Existing classifier recognizes `advice / plan / analyze`, but the query policy
  interprets the entire sentence using owner/read grammar. A prospective plan
  modifier before 的 is mistaken for an unknown health-data owner.
- Previous weekly-analysis fixes normalized retrospective speech acts only.
  They did not prove prospective plan behavior.
- Changing a keyword alone leaves unresolved query scope. Tool exposure,
  dispatch authorization and completion must share the same task boundary.

## Implementation boundary

- `exercise_plan_scope.py`: immutable role contract separates plan horizon and
  expressly requested evidence. Fully consumes supported exercise draft and
  self-owned basis clauses; unknown modifiers/owners/quotes remain fail closed.
- Pure drafts expose knowledge search only. Basis drafts expose bounded
  `health_query`/`health_query_batch` plus knowledge search. Gateway independently
  enforces authenticated owner equality, exact dimensions/keys, and no writes.
- Explicit report and illness context use existing canonical owned readers.
  Batch adapter preserves single-read semantics rather than adding default
  seven-day history. Existing report coverage and illness row cap are disclosed.
- Missing evidence is proposed through Pi/gateway, including after partial
  reads or knowledge search. Actual read-result goals enter stream and panel
  completion; failed/missing evidence cannot become a completed personal plan.
- Existing clinical/output safety checks are not bypassed. A query result is
  neither clinical clearance nor evidence that old illness is still active.
- New grammar/behavior participates in the runtime authorization digest.

## Verification and review

- RED before implementation: 11 failures / 25 passing controls.
- Initial 45-test repair passed; independent safety review found that a model
  could read one requested dimension then answer without the other. NO-GO was
  honored; deterministic evidence outcomes and partial-read tests were added.
- Current focused suite: 51 passed (SQLite fast lane).
- Independent temporary localhost PostgreSQL database: 14 Pi/gateway/canonical
  reader/persistence trajectories passed. Covers both stream and panel, skipped
  reads, partial/knowledge-first reads, failed adapters, and old-owned vs foreign
  / future illness records. Models are scripted; not a live provider evaluation.
- Neighboring regression: 3,881 cases passed (including focused cases); final
  no-coverage regression command exited 0. Dedicated new-module coverage run
  passed at 94.87% (51 cases, independent coverage file and `--cov-reset`).
- The first coverage invocation inherited the whole-app target and exited 1
  despite passing test assertions (29% whole-app coverage on this subset).
  This is not a whole-project coverage/CI pass. The targeted rerun measures only
  the new module; full release CI remains required.
- Independent safety re-review: GO after adding the missing evidence gate.
  Reviewed module SHA256 `d2ca0f7f5b67dfc85626a89dabf7aa44a0092c98b5682c8fb8c629183d887f1e`;
  executor SHA256 `f1dca620b1ef146d2bad13a7809ad1a8441bd1918aae83df7eb596057a1a02ec`.
  Current working diff reviewed because this turn did not authorize committing.
- System Map regenerated with existing unrelated work preserved; verification
  and `git diff --check` passed. Temporary local PostgreSQL stopped after tests.
- No production validation or release CI claim. Release requires a clean target
  revision, fresh CI-mode integration gate and actual CI for that revision.

## Architectural limit / follow-up

This repairs the observed exercise-planning family, not every natural-language
planning expression. The larger system still has multiple legacy semantic
parsers. Consolidating task role compilation across domains is separate work;
do not let an LLM's inferred owner authorize access or replace tenant isolation.
Future work should distinguish unknown parsing from positive foreign-owner
evidence, without permitting reads when scope is unresolved.

## Release continuation

User requested publication after the repair. Backend-only release: no mobile or
shared runtime changes, so an identical OTA is not published. Stage only this
repair, its tests and dossier; generate the map from the staged source so the
unrelated uncommitted AMap router/service are not included. Verify exact-commit
safety review, CI-mode tests, live synthetic model gate and actual main CI
before running the governed backend deployment. Reuse the clean release
checkout; retain all other working-tree changes.

### Candidate verification

- Fixed runtime commit: `6abb655d82f678769618b40d1800bd6e4f3bc3c7`.
- Independent fixed-commit safety review: GO; all eight files reviewed.
- Clean-checkout CI-mode shard runner: 3,881 passed, exit 0. PostgreSQL
  rerun: 51 passed, including 14 real Pi/reader/persistence trajectories;
  temporary database was stopped after verification.
- Live synthetic synthesis gate passed: invariants 12/12, health-agent core
  50/50, orchestrator 5/5 (average 0.94), trajectory contracts 12/12 and
  goldens 9/9. This is not a live-model exercise-plan end-to-end claim.
- CI run `36327206956` detected missing structured dossier status and G1
  admission fields. Production was not changed; this documentation follow-up
  supplies those fields and must pass a new exact-revision CI before deployment.
