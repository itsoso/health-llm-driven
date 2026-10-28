# Photo supplement record clarification

| 字段 | 值 |
|---|---|
| slug | photo-supplement-clarification |
| 当前阶段 | S5 验证 |
| 状态 | building |

## G1 准入

裁决: PASS。修复用户截图中的已有补剂记录请求分流，不新增自动服用写入或推断。

## Scope

User screenshot: a bottle photo with `记录益生菌补剂` received a generic guidance hold. No actual health records or live models were inspected.

## Finding and implementation

The existing deterministic photo supplement parser only supports a closed multi-product/count phrase. Incomplete single-product captions bypassed it and reached general model guidance. Add a separate, non-writing clarification branch for explicit incomplete captions. Ask whether this is an inventory entry or an already-taken event, then request product identity and, for intake, actual amount/unit/time. Never infer ingestion, recipient, or dosage from a label. Preserve the existing complete-request proposal/confirmation path. Persist a `waiting_for_user` outcome rather than claiming success or showing a retryable failure.

The clipped stop-medication message is not resolved by this change. Its exact text and target cannot be recovered reliably from this screenshot; no medication mutation is performed.

## Evidence

- SQLite focused suite: 41 passed (`/tmp/reva-photo-details-tests.log`).
- First test invocation failed during setup because the default local PostgreSQL port was unavailable; not a behavioral red result.
- PostgreSQL focused suite: 91 passed in 88.19 seconds (`/tmp/reva-photo-details-pg.log`).
- System Map gate passed (`/tmp/reva-photo-details-map.log`).
- Independent safety review: GO for b07c98c5099283175850da865a0b700d36eaea8e. Full local CI-mode running; remote main CI 39555135244 running. Deployment pending. No mobile change; no OTA warranted for this patch.

- Additional outcome/preview/guidance regression: 308 passed. Original CI 39555135244 preserved: live-model waiver missing and dossier front-matter missing. Corrected dossier metadata; explicit SHA-scoped live-model waiver follows the existing user restriction, not a claim of live evaluation.

## 2026-10-28 continuation: text-only reference to the preceding photo

The user explicitly requested fixing the new screenshot together with adopting the approved downward-opening guardian icon. Icon assets and simulator evidence are documented in `docs/design/xiaoqihou/guardian-icon.md`.

The screenshot's follow-up `记录以上图片补剂` has no new image attachment. The existing deterministic clarification only ran inside `if images` and did not recognize this wording. It therefore reached generic record-failure handling. The repair admits a bounded set of explicit photo-reference phrases into the existing non-writing clarification, with or without a current attachment. It asks inventory versus actual intake, then product name and actual amount/unit/time as needed. It does not fetch historical photos, infer product identities or ingestion, reuse label doses, or create a pending write. Complete-request preview and consent/owner checks remain unchanged. This is a clarification repair, not automatic recognition of a previous photo or completion of the user's health record.

### Current verification

- Behavioral RED: 7 failed, 52 passed before the fix (`/tmp/xiaoqihou-photo-reference-red.log`).
- Focused SQLite regressions: 130 passed before adding the durable two-turn replay case (`/tmp/xiaoqihou-photo-reference-green.log`).
- PostgreSQL 17, dedicated UTF-8 test database: all 131 focused tests passed in 108.69 seconds (`/tmp/xiaoqihou-photo-reference-pg.log`). Includes persisted `waiting_for_user`, same-turn replay, no health write or pending intent, unchanged preceding photo message, complete-request confirmation, and ownership boundaries. Initial database setup inherited SQL_ASCII and failed before tests; recreated only this run's empty test database as UTF-8.
- Adjacent food-vision, photo routing, turn outcome, meal clarification, mixed supplement/diet, unit clarification, and no-false-write-claim suites: 624 passed, 18 skipped in 132.21 seconds (`/tmp/xiaoqihou-photo-reference-routing.log`). Skips are existing gated cases, not evidence of passing coverage.
- Live synthesis gate attempted in an isolated in-memory synthetic-user database: offline invariants 12/12, health-agent core 50/50, trajectory contracts 12/12, golden traces 9/9 passed. Live orchestrator 0/5: local provider has no configured API credential and default destination was rejected by the disclosure guard (`recipient_not_disclosed`). No guard bypass, production data, or prior waiver used. Live evaluation is NOT passed (`/tmp/xiaoqihou-photo-reference-llm.log`).
- Workflow trace: `docs/_generated/harness-runs/b0492672cab8.jsonl`. Independent safety review pending at this checkpoint.

### Publication boundary

Current local base is `0ff0f34aa2ab510345163bb8ee3c6d3fdc379644`. Existing production release run `40618543912` failed in read-only readiness with `exam closure history is incomplete or invalid` / `Untrusted release receipt`; backend and native publish jobs were skipped. Another active release repair owns this path; this task does not alter its receipts or retry publication. Exact-candidate full CI and live-model gate remain required before publishing this change. The icon changes need a new native build; OTA cannot update the installed launcher icon. This task has not replaced the frozen 282 review candidate, deployed backend changes, or published OTA.
