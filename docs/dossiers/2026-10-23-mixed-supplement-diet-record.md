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
