# External Agent Record Grants — dossier

| 字段 | 值 |
| --- | --- |
| 状态 | draft |
| 当前阶段 | S3 definition; scope decision pending |

User request: “增加这个Skill，要允许外部授权的Agent修改数据”. User selected: “改造 Reva 服务端，增加外部 Agent 的权限、审计和授权管理”.

Controller: product-pipeline. Overlay: safety-gate. Current stage: S3 definition prepared; G1/G2 human decision pending. Implementation, verification, grant issuance and production release have not occurred.

Spec: [Concrete authorization proposal](../specs/active/2026-10-10-external-agent-record-grants.md).

S1: read-only source and independent discovery completed. Existing API-key writes already work; the local helper's GET limit is separate. Missing granular authorization/expiry/strong audit and possible administrator API-key owner bypass are documented in the spec.

G1 proposal: accepted product fit (WriteIntent, ExecutionEvent, owned capture/correction and Twin feedback), pending human approval of the proposed grant/write-confirmation scope.

G2 proposal: bounded water first slice, positive allowlist, owner-confirmed writes, transactional audit/receipts and PostgreSQL concurrency checks. Pending human decision; no permission expansion before acceptance.

S4/S5 plan: (1) fix owner-only Agent authorization boundaries; (2) grant identity/expiry/revocation binding with managed migration; (3) transactional proposal/confirmation/execute and water total semantics; (4) owner management, both client contracts and runtime Skill; (5) tests and independent safety review. Product-pipeline retains ownership; activate Health Harness only on entering S5.

Environment: main has unrelated concurrent dirty work; it was preserved. Open-PR lookup failed due network connectivity, so no external Git mutation is performed. System Map path selector for deps.py is not indexed; source investigation used actual files. No test suite has been run for this draft, and no implementation success is claimed.

Pending original logging request remains unexecuted because the current local helper has no water write route. The server feature proposal does not imply that a live grant, helper scope or record has changed.
