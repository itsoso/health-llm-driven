# Recording reliability: mixed facts, partial recovery, truthful status

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S4 实现 |

Spec: `docs/specs/recording-reliability.md`. Harness trace: `docs/_generated/harness-runs/b3b708925ff4.jsonl`.

## G1 准入
裁决: PASS。用户授权按前次建议先改进记录可靠性。映射 WriteIntent 与 ExecutionEvent；服务对象为需要低负担记健康事实的用户。本批不产生用药方案，不推断剂量强度、主体或历史日期。

## Acceptance contract
- Parse complete explicit current-self intake clauses into separate typed facts, including order and supported oral variants. Reject uncertain quantities, negation, quotations, third-party subjects and unparsed residuals.
- Preserve exact names, quantities and units. Multiple facts never imply permission to add a batch item, infer strength, or widen account/date scope.
- Distinguish all complete, partial definite failure, and uncertain dispatch; success requires verified receipts.
- Explicit recovery retries only proven unwritten facts. Successful siblings must not be dispatched again; uncertain writes require reconciliation and cannot be blindly retried.
- Reply, card and turn status use the same verified outcomes. A partial result must not say all actions were unexecuted.
- Synthetic regression includes real gateway/API persistence, owner isolation, order variation, duplicate/replayed retry, partial failure and missing-receipt paths. No real user health data.

## Delivery plan
1. RED reproduction and typed mixed-intake grammar integration.
2. Source-bound selective recovery and coherent outcome projection.
3. Mobile status regression; exact CI, independent safety review, backend deployment and compatible OTA.
4. Subsequent infrastructure optimization: authenticated credential refresh and attributable release stages; do not mix unreviewed release-infrastructure changes into the health-write repair.

## Evidence
Baseline main/backend 59c64cca666d85f3c7b738a508dd197d4ad6c84e. Existing closed parser supports only one fixed supplement-first phrase. Existing retry refuses any source with a verified receipt. Existing outcome classifier can treat a successful sibling plus definite tool failure as reconciliation. These are investigation targets, not delivered fixes.

## Implementation and incremental verification

- Typed complete-input intake plan and shared capability item matcher: RED reproduced, 2572 scope/capability tests passed (`/tmp/reva-intake-match-green.log`).
- Two legacy single-target paths were overriding correctly typed proposals: simple diet goal canonicalization and deterministic supplement repair. Multi-item plans now bypass these single-target rewrites.
- Turn checkpoints use the same authorized typed identity before and after gateway projection, so inserted default dates cannot leave an orphan in-flight fingerprint. Only explicit no-side-effect evidence permits selective retry; earlier in-flight/uncertain checkpoints remain protected.
- Coverage checks require a verified receipt for each typed item; a model omitting a sibling cannot report whole-turn success.
- Partial retry is source/owner/conversation/plan-bound, skips verified siblings, and rejects unknown outcomes and changed dates/timezones. First slice does not support repeated partial retry chains or attachment sources.
- Synthetic gateway/API stream tests cover original and reversed order, partial failure, omitted item, retry, duplicate client-turn replay, and changed account timezone: 10 passed, 6 inapplicable parameter combinations skipped (`/tmp/reva-reliability-timezone-stream.log`).
- Initial PostgreSQL persistence/retry suite: 57 passed (`/tmp/reva-reliability-pg.log`); expanded final run pending.
- Mobile initial regression: 300 passed, TypeScript passed. Independent review requested a cross-message recover isolation fix; final rerun pending.
- G4 preliminary BLOCK found timezone propagation and cross-turn UI evidence risks. Fixes are in progress/reverification, not final GO.
- Live model gate is required. User was asked to authorize this new batch of synthetic live evaluation; previous batch-specific permission is not reused. No live models or production health data have been accessed in this batch.
- Publication not started; production remains the prior verified revision. CI-mode, exact remote CI, final G4, backend receipt and applicable OTA remain required.

## Integration checkpoint

- Expanded backend regression: 4302 passed, 7 skipped, one failure in the existing symptom rejection reason. Fixed by restricting new partial-write action projection to turns with actual receipts; fresh symptom plus stream rerun: 11 passed, 6 inapplicable combinations skipped.
- Expanded PostgreSQL: 80 passed, 6 skipped (`/tmp/reva-reliability-pg-final.log`). No production database used.
- Mobile cross-message evidence isolation and safe partial retry button: 309 passed and TypeScript passed (`/tmp/reva-mobile-followup-verified.log`).
- Source-bound metadata CAS permits only one retry message to claim a partial source, including different client-turn IDs. The same message can resume only with no unknown write evidence. Dedicated two-session PostgreSQL race test passed (`/tmp/reva-intake-claim-pg.log`).
- Offline LLM invariants, rubric and trajectory gates passed (`/tmp/reva-reliability-offline-llm-gate.json`), zero model calls.
- System Map regenerated and verified. Open PRs inspected; main remains the baseline revision. Unrelated work remains unstaged.

## Safety review closure candidate

- Preliminary review caught two further defects: orphan recovery trusted a model's incomplete write set, and tool-name failure settlement could conceal a durable unknown operation. Both now fail closed unless exhaustive source-bound checkpoint evidence is present.
- Orphan regression: 22 passed, including omitted item, missing/tampered checkpoint, extra unknown operation/receipt and legacy single-item raw fingerprint recovery (`/tmp/reva-intake-orphan-green.log`).
- Settlement negative cases plus real API stream: 15 passed, 6 inapplicable combinations skipped (`/tmp/reva-settlement-green.log`). Independent preliminary reviewer closed the settlement finding; this is not final G4.
- Source claim refresh and CAS now recheck both source and retry message. Dedicated PostgreSQL concurrency/drift cases: 13 passed (`/tmp/reva-intake-claim-fresh-pg.log`).
- Final combined regression and PostgreSQL rerun are in progress. This candidate is not published; new-batch live-model permission remains pending.

## Candidate validation and upstream integration

- Candidate `5fafcd6e437d4a6e4aa08d7ae085d0930dee56dc`: final G4 GO; focused backend 137 passed/7 skipped; PostgreSQL 103 passed/6 skipped; CI-mode 4695 passed/49 skipped, no failures or errors, clean verification checkout.
- User explicitly authorized this batch's synthetic live-model evaluation. Isolated in-memory test database gate passed: orchestrator 5/5 (average rubric score 0.96), invariants 12/12, core 50/50, trajectory contracts/goldens passed. No real health records accessed. Evidence: `/tmp/reva-reliability-5faf-live-result.json` and `/tmp/reva-reliability-5faf-live-gate.json`. This result binds 5faf only.
- Fresh production readback still proves prior 59c64 backend SUCCEEDED/COMMITTED and healthy services. No new deployment or OTA has run.
- Remote main advanced to `b55b443d4351d1ece8974f441bbd10e1e4af5e2d` with Edu SSO and dependency security changes. Integrating locally preserves those commits and regenerates System Map; Edu remains disabled by default and no configuration activation is authorized by this merge.
- Upstream CI 40075861268 failed because OTA tests treated moving main's dependency lock as the old reviewed exception. Tests now use immutable reviewed source for positive admission, and reject the new dependency source; production OTA policy is unchanged. 14 OTA contract tests passed (`/tmp/reva-integrated-ota-green.log`).
- Integrated candidate needs fresh G4, CI-mode, live-model and remote exact-SHA gates. Its dependency changes are outside current OTA permission; do not publish an incompatible update or treat test repair as expanding admission. Native delivery assessment remains pending.
