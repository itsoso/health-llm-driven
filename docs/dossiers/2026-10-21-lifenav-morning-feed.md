# LifeNav morning report reader

| 字段 | 值 |
|---|---|
| 状态 | in_progress |
| 当前阶段 | 本地实现与回归通过；待独立安全审查、CI及上线验收 |

## G1 准入

裁决：PASS。按用户明确要求扩展已有 LifeNav 页面，只读展示本人已有晨读。范围、边界和验收见下文。

## Scope and admission

The user requests existing private morning reports inside `/agenda?navigation=week`.
This extends the existing user-authorized LifeNav personal planning surface. Proofroom
remains the report source of truth; Health facts and planning writes stay separate.
The goal is to read the selected date and earlier reports without leaving the planning page.
This is read-only display, not a new health recommendation, AI generation or automatic plan adoption.
No database, collector, credentials, native runtime or reminder changes.

## Contract and user flow

Health authenticates the current self session, forwards only the exact selected JWT to
fixed `https://base.executor.life`, verifies upstream user identity, filters `morning_reading`
and independently verifies detail ownership/source. API keys, managed and family proxy
sessions are denied. Redirects are disabled; responses are bounded and private/no-store.
Only validated plain text enters the browser. Shared account identity is already established
by the existing Health/Proofroom auth integration; this adds no new secret or token minting.

Today and week tabs show a compact morning panel beneath date navigation. A report for the
selected Taipei date opens automatically. Missing dates are explicit; partial pagination
is not represented as a complete search. Historical reports require selection and show
their original dates. Account/date changes abort in-flight reads and reset visible content.
Errors offer retry. No reads modify workspaces or export reports into LifeNav backups.

## Verification

- Tests first: missing service/component failed before implementation; repeated selection
  regression failed before the idempotent selection fix.
- CI-mode incremental backend tests (`DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai`,
  isolated unavailable Redis): 45 passed, 3 skipped (existing optional PostgreSQL cases).
- Frontend full suite: 565 passed, 1 skipped; production build passed; lint 0 errors.
- System Map regenerated and verification passed. Both API clients regenerated from locked
  Python dependencies. No PostgreSQL/schema changes.
- Privacy tests cover exact bearer/cookie relay, bearer precedence, owner mismatch,
  API-key/managed denial, non-morning IDs, redirect/error rejection and response size cap.
- UI tests cover safe text, owner-race discard, explicit historical dates, pagination,
  repeated selection and failure/retry.

## Release acceptance

Independent safety verdict required before push. Exact main CI and trusted release
receipts required before claiming deployment. Live acceptance: open the requested Health
URL, read an actual report inline, check missing-day/history behavior and private headers.
An API type artifact in Mobile does not change native runtime behavior or require OTA.
No production report body or credential is committed as test evidence.
