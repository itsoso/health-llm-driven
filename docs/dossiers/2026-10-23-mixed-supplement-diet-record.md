# Mixed supplement and beverage recording

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S4 实现 |

## G1 准入
裁决: PASS。修复用户当前轮明确描述的补剂与饮品摄入被拒绝的问题，不扩大主体、时间、剂量或用药权限。

## Scope and reproduced evidence

- Screenshot request combines zinc tablet intake and soy milk intake. Synthetic reproduction classifies write/supplement/create but both health_record proposals are blocked as write_tool_without_write_intent.
- The ownership parser treats the first predicate's object as a subject before the second predicate. Authorized clauses become empty. Supplement target extraction also needs to preserve the exact name rather than include the ingestion verb.
- The existing failure copy incorrectly asks create versus update even when creation intent is explicit. New failing copy regression reproduced, corrected copy suite 192 passed.
- New real Pi/gateway/authenticated API tests reproduce zero SupplementRecord writes before the fix. They must prove separate supplement/diet receipts, partial-failure honesty and same-turn replay without duplicates.
- No production records inspected or changed; no actual model calls. Current source is not deployed. The prior dinner release does not prove this mixed-domain case works.
- G4 independent review, exact CI-mode/GitHub CI, PostgreSQL and production publication pending. No mobile changes planned.

## Implementation and verification

- Added a full-match, closed-vocabulary mixed supplement/drink parser, used by clause authorization, capability exact target binding and executor name grounding. It carries only explicitly supplied quantity/name facts, no dosage strength or clock-based meal inference. Diet uses the existing unspecified-meal storage default snack.
- New scope regression initially failed the positive case; current 24 positive/negative cases pass. Fresh complete scope/capability regression: 2520 passed.
- Real Pi, ToolGateway and authenticated supplement/diet API tests: 2 passed. Two distinct verified writes on success, one verified write plus error on definite sibling failure; same client turn replay creates neither duplicate. Synthetic NFC clock and debounce state are isolated per test.
- PostgreSQL suites: 105 passed (supplement/domain/API); fresh final mixed scope and persistence tests: 26 passed. No real health data or actual model used.
- System Map and dossier consistency checks pass. Executor broader regression pending; independent review and release gates remain pending.

## Independent review correction

- Initial commit 187c1ec8b received NO-GO: a correct top-level supplement target could carry an extra data.items batch through the existing projection. Downstream batch reconstruction still rejects it; no unintended persistence was proven. The capability boundary itself must reject it.
- Added failing malicious-items regression (1 failed / 24 passed), then rejected any items key at either top-level or data for the mixed single-intake grammar. Malicious, empty, null and malformed aliases now covered. Fresh focused suite including real Pi/API persistence: 35 passed.
- Broader executor/receipt/dinner regression on the initial implementation: 353 passed. Final correction only narrows capability authorization; fixed-commit independent re-review remains required.

## Numeric-boundary follow-up

- Adversarial probes after the first review found ambiguous Chinese counts and legacy food comparison removing decimal points (1.5 cups could match 15 cups). A second NO-GO supersedes the earlier GO pending correction.
- Chinese quantities now use canonical positive integer forms. Mixed drink matching independently binds exact Decimal amount, unit and closed drink name, preserving decimal points and allowing equivalent order/half-cup forms. General food parsing is unchanged. Mixed supplement dosage uses the existing punctuation-preserving supplement normalizer before legacy projection.
- RED: eight malformed Chinese count cases failed before correction; eight decimal/corrupted dose cases failed before correction. Corrected focused tests 55 passed; final expanded PostgreSQL scope/API tests 59 passed. Final scope suite and independent re-review pending.
- Earlier local CI-mode candidates are superseded, not publication proof. No push, no production mutation. The current-batch live-evaluation/waiver choice was requested because previous waiver was scoped to the prior released batch and has been cleared.
