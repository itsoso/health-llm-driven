# Medication management page refinement

| 字段 | 值 |
| --- | --- |
| 状态 | defining |
| 当前阶段 | S3 — CI repair before delivery |
| 更新日期 | 2026-10-21 |

## G1 Scope admission

裁决: PASS

Screenshot-driven repair of existing behavior. Scope is bounded to the implementation and regression evidence below; no new health authority, inferred clinical facts, or historical data cleanup.

## G3 Verification

裁决: FAIL

Candidate dfa45494b7 has failed remote backend-quality and docs-quality checks. Repair and fresh exact-revision CI are required before delivery. Local targeted tests do not substitute for those gates.

## Scope

Screenshot-driven refinement of `/medications`: clear header, readable medication name/dose/frequency hierarchy, named reminder/check-in action, secondary management menu, and an actionable load-error state. No new routes, APIs or clinical recommendations. Existing list data is preserved.

The screenshot also contains a query instruction rendered as a drug draft. The page previously accepted any nonempty `name` route parameter and exposed add-and-log. Recognizable query/negative-record instructions now show a review notice, with no confirm button and a mutation guard. Similarly malformed saved entries remain editable but do not offer reminder entry. This is a bounded UI guard, not proof that upstream classification or persisted historical data is corrected.

## Acceptance

- Title centered between fixed44-point controls; tabs have selection semantics.
- Dose/frequency separated; `daily` displays `每日` without inventing intake count.
- Active valid item has labelled `提醒与打卡`; stop action behind More and existing explicit confirmation.
- Query/negative instructions cannot be confirmed as medication drafts; existing valid draft flow unchanged.
- Fetch failure displays retry, not an empty list.
- No personal records, external model evaluation, backups or changes to App Review freeze.

## Verification

New regression tests failed before implementation (three expected failures). Focused page regression passed8 tests after repair; final neighboring suite/type/lint results recorded on completion. Simulator available, but current changed screen has not yet been installed/visually accepted; installed historical synthetic/279 binaries are not evidence for this change.

## Delivery

Independent safety review returned GO. Related tests15, TypeScript and ESLint passed. Exact-SHA CI is not green. The user explicitly lifted the279 pre-submission OTA freeze on2026-10-21; normal publication gates remain and affected submission acceptance must be refreshed before a future submission. No new OTA has been published.
