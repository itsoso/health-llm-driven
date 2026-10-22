# Explicit dinner recording through Pi

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S5 验证 |

## G1 准入
裁决: PASS。修复明确餐食新增请求没有产生工具调用时未保存的问题，不新增数据权限或绕过营养估算。

## Evidence and scope

- The screenshot caption compiles to a diet/create goal with all five foods/amounts preserved. The existing diet preplan helper was not connected to the ordinary Pi loop.
- RED: synthetic provider returns no tools, receipt remains empty. First two test invocations had an incorrect model import; corrected fixture then reproduced the behavioral failure.
- Connect the existing preplan only for round-zero, authorized current-turn diet/create, no attachments, no pending/unverified operations, no runtime block or read-only mode. Keep ordinary nutrition enrichment, Pi validation, gateway, persistence and receipt verification.
- Focused SQLite tests: 213 passed. Includes original request and owner-bound retry through real diet API, blocked/runtime/read-only/incomplete-nutrition boundaries. No real models or real health records used.
- System Map passed. PostgreSQL: 213 passed in 33.78s, isolated UTF-8 test database; /tmp/reva-dinner-pg.log.
- Safety review, full CI and production deployment pending. No mobile change.
- Existing local prompt-contract commits 51d7cf09b and 7b3c69f8c are preserved. Their receipt explicitly marks live-evaluation decision pending; this patch does not claim their deployment or waive that gate.
- Screenshot alone does not prove the retry was stuck for its entire timestamp interval. The test verifies original-message recovery and finalization; device UI timing remains unverified.
