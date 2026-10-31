# Agent record task contract

| 字段 | 值 |
| --- | --- |
| 状态 | implementation |
| 当前阶段 | G4 committed-diff review and release validation |
| Controller | backend-deploy, safety-gate overlay |

## G1 admission

裁决: PASS

Existing recording reliability fix; preserve Pi, bind explicit self-report facts
to capabilities and persistence evidence. No new diagnosis, treatment or schema
authority. Scope and acceptance: `docs/specs/active/2026-10-31-agent-record-contract.md`.

Baseline: origin/main 8d8475fa52902fd8a31930b7879efe90dac20120.
Scope: implementation, commit and main integration, production backend/Web deployment, applicable Mobile OTA and online verification (explicitly authorized 2026-10-31).
Controller: health-harness-orchestrator; overlay: safety-gate.
Spec: ../specs/active/2026-10-31-agent-record-contract.md.

Evidence: production metadata inspected in prior analysis showed a record request
classified as chat, no tools/receipts, but completed. The repeated request was
blocked as an unrequested query. No personal payload is retained here.

## Implementation

Official Pi is retained. New generic record obligations cannot silently become
successful chat. A registered capability binds the schema, owned user facts,
endpoint, channel policy and event readback proof. Zero-tool model responses may
receive one bounded proposal through the existing gateway; this does not bypass
policy or grant permission to unknown actions.

Nasal washing is the first event contract. PostgreSQL owner locking, immutable
event identities, tombstone undo and legacy endpoint conflict checks prevent
lost updates, duplicate retries and resurrection. Web and Mobile use the same
append contract while preserving manual time and wash/soak behavior. Health
payloads were removed from the touched legacy endpoint's log messages.

## Verification

- RED tests demonstrated missing capability and compound-task false completion.
- Official Pi + authenticated API + isolated PostgreSQL: 57 passed, 1 live case
  separately deselected; includes replay, concurrency, owner isolation, corrupt
  readback, malformed POST receipt, precise undo and legacy overwrite rejection.
- Web: 6 component/service cases passed; Mobile: 8 passed; both typechecks passed.
- Fresh live-provider synthetic-record E2E: 1 passed (12.23 seconds); official
  Pi, authenticated API and isolated PostgreSQL were real. HTTP requests used
  the app test transport and only synthetic users, with no provider mock.
- Fresh repository live LLM regression gate passed with no failed cases.
- System Map generation and drift check passed.
- Expanded backend regressions: 3762 passed, 6 skipped. Legacy suffix-command,
  analysis adjunct, symptom conjunction and supported compound compatibility
  regressions were repaired. Strict multi-target owner/date receipt checks
  reject missing identities rather than filling defaults.
- Supported two-water-record real Pi/PostgreSQL completion and same-turn replay,
  plus partial execution: 2 passed. The partial case was RED before the fix;
  final tokens, stored text, metadata and task outcome agree on partial completion.
- After the final partial-text change, the full affected completion/goal/outcome
  suite passed: 525 tests. Fresh live LLM gate passed again; the local path-based
  live-change gate passed with ephemeral local confirmation. No repository
  variable was modified and no uncommitted change is claimed as revision CI.
- Independent safety and compound-completion review: GO; all raised P1/P2
  findings closed. System Map and `git diff --check` passed.
- Evidence logs: `/tmp/reva-task-contract-{regression-final,pg-final,completion-final,live-record,live-gate,map-final}.log`;
  compound E2E `/tmp/reva-task-contract-multi-partial-green.log`;
  client tests `/tmp/reva-client-record-{web,mobile}-final.log`.

Status: implemented and locally verified. The isolated PostgreSQL test cluster
was shut down after validation. No production acceptance or release claim.

## Boundaries

No production health data was written. No commit, push, deployment or published
revision CI claim. All work is in an isolated worktree at the fetched baseline;
the original shared checkout and its changes are preserved. Client pending
identities survive in-component retries, not app restarts. New event writes
with unknown outcomes remain reconciliation_required; automatic background
reconciliation is not added. Unsupported capabilities cannot be auto-recorded.

## Release continuation

User authorized commit, main integration, production deployment and Web/Mobile
verification on 2026-10-31. Fresh fetch confirms the original baseline remains
current main. Production backend has since reached that same baseline; previously
pending release recovery is not assumed to remain blocked. Exact candidate CI,
independent committed-diff review and current release receipts govern release.
