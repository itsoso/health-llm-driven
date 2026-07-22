# Dossier: LLM Quota Governance

| 字段 | 值 |
|---|---|
| slug | `llm-quota-governance` |
| 创建日期 | 2026-07-22 |
| 当前阶段 | S6 待部署 |
| 状态 | deploy-ready |
| 负责 | Codex |
| 反馈环 | Backend pytest / Web+Mobile TypeScript / targeted ESLint / deploy / Mobile OTA |

## S0 · 用户需求

> 给管理员不要限量，普通用户限量之后也要给到提示，并且要有运维和监控。

- 区分阿里云 TokenPlan 套餐状态与 Reva 本地用户准入策略。
- 管理员绕过 Reva 个人限额，普通用户继续受控并获得真实、可执行的恢复提示。
- 运维可检查个人策略、水位、拦截次数和原因，且监控账本不得保存健康正文。

## G1 · 准入裁决

- core_loop_step: Agent 请求准入 -> 模型调用 -> 成本与拒绝观测。
- first_class_objects: `LlmUsageLog`, `AdminObservability`。
- safety_level: operational_observability。
- autonomy_tier: no_health_write。
- smallest_end_to_end_slice: 管理员豁免 -> 普通用户结构化拒绝 -> Admin 面板与日检可观测。
- 裁决: **PASS**。这是基础设施可靠性、成本控制和用户错误契约修复。

## G2 · 可行性 + 安全压测

- 管理员只绕过 Reva 的个人月 Token、个人日调用和个人月 Credits 限制；全局熔断继续生效。
- 普通用户的拒绝事件使用固定元数据写入 `llm_usage_logs`，不保存 prompt、回复或健康正文。
- 拒绝事件不计入已分发调用，避免监控记录反过来消耗配额。
- 阿里云控制台是套餐余量最终真值，本地账本只用于 Reva 策略和成本估算。
- 裁决: **PASS**。

## S4 · 研发任务分解

- [x] 管理员个人限额豁免，并覆盖显式身份和数据库回退路径。
- [x] 普通用户月度/每日额度提示和稳定错误码。
- [x] 元数据级拒绝账本和每日临界水位检查。
- [x] Admin 用量面板展示策略、利用率和拒绝原因。
- [x] Mobile 错误兼容与回归测试。

## G3 · 测试闸

- 裁决: **PASS**。
- Backend quota/dashboard/monitoring regression: `47 passed`。
- Mobile chat error regression: `58 passed`。
- Frontend 和 Mobile TypeScript: PASS。
- Frontend 和 Mobile targeted ESLint: PASS。
- Python compile、`git diff --check`: PASS。

## G4 · 安全闸

- 拒绝遥测只包含 user/run/caller、策略原因和恢复时间等运行元数据。
- 不写 prompt、completion、原始错误载荷或健康正文。
- 管理员豁免不绕过全局成本和可用性熔断。
- 裁决: **PASS**。

## G5 · 部署健康闸

- 状态: PENDING。

## G6 · 生产验证

- 状态: PENDING。

## Acceptance

- 一个管理员调用不会被个人月 Token、个人日调用或个人月 Credits 限制拒绝。
- 普通用户被确定性拦截，并看见恢复时间和内容保留说明。
- 本地策略拒绝不会伪装成阿里云套餐耗尽，也不会触发 provider fallback。
- Admin 监控展示每用户策略、利用率和拒绝次数；每日运维检查输出结构化状态。
