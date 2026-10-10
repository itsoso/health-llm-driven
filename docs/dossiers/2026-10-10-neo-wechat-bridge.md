# Dossier: independently hosted owner WeChat bridge

| Field | Value |
|---|---|
| slug | neo-wechat-bridge |
| Created | 2026-10-10 |
| 当前阶段 | S5 implementation |
| 状态 | building |
| Branch | codex/neo-wechat-health-bridge |

## User request

> 1、授予读取健康数据的权限 2、期限3650天  其他没问题 开干

Delegated outcome: independent Health-hosted single consumer, private generic Slack
wakeup, separate OAuth MCP, pinned owner private-text replies and owner health reads.
User explicitly authorizes code/tests/review/protected PR/CI/deployment; personally
owned secret entry, QR scan and OAuth consent are handoffs, not implicit agent actions.

## Discovery

Clean origin/main base `fa4703060594472933bca35553c9de05c5016cd6`; dirty original
checkout preserved. Existing Site transports inspected without secrets. Existing
`backend/app/api/remote_health.py` exposes only sleep/diet/exercise read projections.
`remote_health_oauth.py` has 600-second access, 30-day grants and owner website consent.
Health consent needs a dedicated client owner pin and NEW grant duration configuration.
No bridge imports business models, sessions or environment files.

Strict SSH at 05:56–06:00 UTC: production `346035f78b362804df06e1524099f87294286ef6`;
health-backend, celery-worker, celery-beat and backend socket active; business lease
absent; canonical launcher.lock root 0600 with no observed holder. This is a snapshot,
not a reservation. Relay enabled and canonical ls-remote succeeded. Main CI pending.

## G1: PASS

裁决：PASS。

Controlled external R10 surface; HealthTwin observations and ExecutionEvent feedback;
sensitive private data, scoped autonomous replies authorized only to pinned owner.
Spec required. No stale surface removed. User approval above covers this bounded scope.

## G2: PASS (architecture; implementation/production remain gated)

裁决：PASS。

Independent read-only reviewer `boundary_review` confirms split-authority plan fits
approval. Health must enforce pinned Health user at consent and token use. No old grant
expansion, arbitrary RPC relay or identity inferred from incoming WeChat content.

## Artifacts and tasks

- PRD: `docs/prd/2026-10-10-neo-wechat-bridge.md`
- Plan: `docs/plans/2026-10-10-neo-wechat-bridge.md`
- T1 encrypted bounded storage and inbox/outbox.
- T2 independent OAuth and MCP/owner UI.
- T3 separately consented owner-only Health adapter.
- T4 reviewed bounded deploy entry and service containment.
- T5 tests, independent safety review, protected PR/CI and acceptance.

## G3 / G4 / G5 / G6

Pending. No deployment, secret creation, QR request, grant or live signal has occurred.
Final completion requires real closed-Mac/restart receipt and user-owned handoffs.
