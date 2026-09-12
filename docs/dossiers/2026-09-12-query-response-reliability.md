# Query response reliability

| 字段 | 值 |
|---|---|
| 状态 | implementing |
| 当前阶段 | S6 verification |
| slug | query-response-reliability |

## G1 需求准入

裁决：PASS。用户批准既有查询、权限与完成状态的可靠性修复；沿用既有健康安全和用户数据边界。

## Engineering delivery

Status: implementing. Controller: health-harness-orchestrator. Overlay: safety-gate.
Trace: `docs/_generated/harness-runs/ca612203e657.jsonl`.
Spec: `docs/specs/active/2026-09-12-query-response-reliability.md`.

User approved the analysis plan and retained prior push/deploy authorization. Scope is consistent query interpretation, quoted-input authority, correction recovery, risk-first routing and honest outcomes. Unrelated Mac shopping/model catalog changes and model-registry tests present at startup are protected.

## Evidence and gates

- Admission: accepted maintenance of current health observation and verified execution contracts; bounded daily summary semantics documented.
- Baseline: 31 owned production requests inspected read-only; sample spans versions. Current pure functions reproduced equivalent-tool conflict, compound query denial and quoted cancellation. Historical two ratio phrases now parse, but reordered variant does not.
- Implementation: shared exact-day read plans, quoted-input and clinician provenance scope, corrected portions, mandatory high-risk provider checks, evidence-backed task outcomes and Web/Mobile presentation are implemented. Meal reads return up to the existing API cap; reaching the cap fails explicitly rather than claiming complete recall. Bound daily reads and sync requests use the ordinary Pi path even when multi-model is requested.
- Synchronization: only an explicit generic owned Garmin sync can enqueue the existing authenticated job. Enqueue acknowledgement explicitly says the data update is unverified; no read result can prove sync completion. Historical-window requests and other owners/devices remain outside this narrow capability. A completed sync conversation acknowledges job submission only; it is not a verified background data-refresh outcome and must not be counted as one.
- First-red evidence caught real execution gaps missed by adapters alone: date/meal mismatch, missing dinner evidence collection, unexecuted panel goals, weak-provider fallback, clinician quote authority, and sync enqueue acknowledgement. Fixed-path checks cover both SSE and durable history.
- Completed checks so far: 4901 policy/gateway/calendar regressions, 2197 quoted/clinical scope regressions, 40 PostgreSQL shared-plan checks plus 2 independent meal-cap PostgreSQL checks, Web 32 and Mobile 179 targeted tests with both type checks. PostgreSQL fixtures are synthetic; no production health data was modified.
- Existing required live gate passed: synthesis invariants 12/12, core contracts 50/50, orchestrator 5/5. New full-Pi real-model trajectories separately exercise actual query dispatch and evidence; final source-bound trajectory verification is pending. Fresh consolidated CI-mode regression passed 1258 tests (8 PostgreSQL-only skips are covered by the separate PostgreSQL runs); final source-specific checks passed 98 (8 PostgreSQL skips), and exact-turn sync/readonly/credential regressions passed 6. Final policy/scope regression passed 5590 tests.
- Independent safety pre-review found and drove fixes for panel goal bypass, high-risk provider downgrade, meal truncation, clinician quote authority and sync source restrictions. Formal review requires the final local commit; no push/deploy is authorized by a preliminary result.
- CI / deployment / production verification: pending. Production remains healthy at the prior revision; no current candidate has been deployed.

## Ownership

- query_semantics: shared query scope, capability policy and policy tests.
- quoted_input: instruction versus quoted-material projection and tests.
- completion_contract: outcome contract and applicable client presentation outside the executor.
- root: executor integration, portion correction, risk routing, full Pi regression, release and verification.
