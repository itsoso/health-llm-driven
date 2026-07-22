# Dossier: AIGC Media Failure Recovery

| 字段 | 值 |
|---|---|
| slug | `aigc-media-failure-recovery` |
| 创建日期 | 2026-07-22 |
| 当前阶段 | G4 发布前评审完成 |
| 状态 | ready_for_deploy |
| 负责 | Codex |
| 反馈环 | Backend pytest / Mobile+Web component tests / production trace / deploy / Mobile OTA |

## S0 · 用户需求

用户确认生成健康饮食短视频后，界面暴露内部 `aigc_confirm_*` 标识，媒体任务只显示
“未完成”且没有可执行的恢复入口；饮食记录成功和媒体生成失败混在同一回复中。

## G1 · 准入裁决

- core_loop_step: Agent 创作草稿 -> 用户确认 -> 外部媒体任务 -> 私有结果。
- first_class_objects: `AIGCMediaConfirmation`, `AIGCMediaJob`。
- safety_level: external_provider_and_cost。
- autonomy_tier: manual_confirm。
- smallest_end_to_end_slice: 隐藏内部回执 -> 分类失败 -> 安全重试 -> 独立任务状态。
- 裁决: **PASS**。这是现有 Agent Native 创作能力的可靠性和错误契约修复。

## G2 · 可行性 + 安全压测

- 生产 trace 证明本次百炼请求返回 HTTP 401，且没有 provider task ID；TokenPlan 文本套餐
  与独立按量 AIGC 媒体凭证无关。
- 只有供应商明确拒绝、没有 task ID 的失败允许用户显式重试。
- `submission_unknown` 和已有 task ID 的失败不得重发，避免重复计费。
- 草稿确认 ID 继续作为内核幂等回执保存，但不得面向用户显示。
- 日志只记录 job ID、kind、稳定错误码和 HTTP 状态，不记录 prompt、媒体 URL 或密钥。
- 裁决: **PASS**。

## S4 · 研发任务分解

- [x] 百炼错误按认证、限流、请求拒绝和服务故障分类。
- [x] 为无 task ID 的终态失败增加所有者隔离、并发安全的显式重试。
- [x] Mobile/Web 失败卡片展示可执行恢复动作。
- [x] Mobile 隐藏 AIGC 草稿的内部写回执。
- [x] Agent 文案不再引用“上方卡片”等易失位置。
- [x] 增加失败率和认证故障的运维日志/监控入口。

## G3 · 测试裁决

- Backend: 77 AIGC/observability tests passed（供应商错误分类、确认/重试幂等、API owner scope、任务恢复、策略与监控聚合）。
- Mobile: 130 tests passed；TypeScript 编译通过；ESLint 0 errors。
- Web: 33 tests passed；TypeScript 编译通过；ESLint 0 errors。
- System map/doc drift 与代码一致；Ruff 通过。
- 裁决: **PASS**。

## G4 · 安全与隐私裁决

- `submission_unknown` 或已有 provider task ID 的任务不可重试，避免重复生成与重复计费。
- 重试沿用原 job/confirmation，并使用 owner filter、advisory lock 和条件更新控制并发。
- 用户投影只暴露稳定错误码和安全文案；监控只汇总状态，不返回 prompt、图片、任务 ID、密钥或供应商响应正文。
- `aigc_confirm_*` 保留在运行时写回执中供审计，但 Mobile 不再将其作为健康数据回执展示。
- 裁决: **PASS**。

## Acceptance

- 401/403 不再显示成笼统的“稍后重试”，而是稳定的授权故障状态。
- 明确拒绝且没有 provider task ID 的任务可由用户点击一次安全重试。
- 提交结果不确定的任务不展示重试按钮。
- 对话中不出现 `aigc_confirm_*`，饮食记录成功状态不被媒体失败覆盖。
- Mobile 和 Web 使用同一后端任务投影与恢复语义。
