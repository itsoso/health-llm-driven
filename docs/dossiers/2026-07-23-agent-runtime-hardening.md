# Dossier: Agent Runtime 运行治理与全入口收口

| 字段 | 值 |
|---|---|
| slug | `agent-runtime-hardening` |
| 创建日期 | 2026-07-23 |
| 当前阶段 | S6 部署 |
| 状态 | in_progress |
| 负责 | Codex + 用户 |
| 反馈环 | Runtime contract snapshot + integrity monitoring + cloud entrypoint facade |

## S0 · 用户需求

> 先做3 再做 1 再做2

这里的顺序指：

1. Agent Runtime：状态机、成本控制、监控告警、跨端一致性。
2. App Store 与真机可靠性：后台切换、网络恢复、播放分享、推送、幂等、真机验收。
3. AIGC 体验：内容质量、生成前编辑、视频时长和失败恢复。

## S1 · 现状勘察

- 既有 Runtime 已具备 canonical Run/Attempt/Operation identity、Run Ledger、会话串行化、写入幂等回执、ToolSpec Registry、ToolGateway、租约恢复、取消、事件游标、有界 SSE bridge 和 rollout circuit。
- 生产已经处于 `enforce`，因此本轮不重写 Agent Loop，也不替换 Executor。
- 仍缺少每个 Run 的内容无关执行契约快照，部署后无法直接判断某次 Run 使用了哪版 Runtime/工具/策略合同。
- 监控目前偏重失败率、reconciliation 和 stale lease，尚未直接暴露 recent Run 的身份链接完整性、合同版本分布和异常龄期。
- Siri、微信 Bot、Telegram 和 starter pregen 等入口仍有直接调用 `AgentExecutor` 或直接调用工具的路径，没有全部进入同一个 durable Runtime lifecycle。
- iPhone strict-local 闭环不调用云 Runtime；本轮保持该边界，不改本地协议、HealthKit 数据流或本地写入权威。

## G1 · 准入裁决

```yaml
RequirementAdmission:
  request: harden Agent Runtime before App Store and AIGC optimization
  classification: runtime reliability and operational safety
  core_loop_step: Capture -> Reason -> Tool -> Receipt -> Recover -> Review
  first_class_objects: [ExecutionEvent, WriteIntent]
  target_surface: [Backend Agent Runtime, cloud Agent entrypoints, admin monitoring]
  source_of_truth: PostgreSQL Agent Run Ledger
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: false
  autonomy_tier: preserve_existing
  verification_window: focused regression plus production runtime window
  success_metric: every managed cloud turn has a traceable contract and one durable lifecycle
  added_user_burden: none
  non_goals: [framework migration, microservice split, strict-local upload, raw prompt telemetry]
  smallest_end_to_end_slice: contract snapshot -> run ledger -> monitoring projection -> regression
  stale_surface_to_remove_or_archive: direct ungoverned cloud Executor entrypoints
  spec_required: reuse_and_extend_existing
```

- **裁决：PASS。** 复用已批准的 Agent Runtime Control Plane PRD/Feature Spec。

## S2 / S3 · 设计与计划

- 设计：[`docs/plans/2026-07-23-agent-runtime-hardening-design.md`](../plans/2026-07-23-agent-runtime-hardening-design.md)
- 实施计划：[`docs/plans/2026-07-23-agent-runtime-hardening.md`](../plans/2026-07-23-agent-runtime-hardening.md)

## G2 · 可行性与安全压测

- 新增账本字段只保存版本号与 SHA-256 摘要，不保存 prompt、回复、健康正文、工具参数或结果。
- 迁移字段可空并对新 Run 强制填充，避免旧行或滚动部署阶段不兼容。
- 监控先 observation-only，不以历史合同差异自动暂停生产；只有既有写入不确定、stale lease 和系统失败率继续触发 circuit。
- 全入口收口按入口逐个迁移；每次迁移必须证明相同输入只产生一个用户消息、一个 Run 和至多一次业务副作用。
- strict-local iPhone 明确排除，避免与独立分支的本地闭环产生所有权冲突。
- **裁决：PASS。**

## S4 · 研发任务

- [x] T1 保存 Runtime contract version、Tool Registry digest 和 Capability Policy digest。
- [x] T2 管理员监控返回 recent contract coverage、message linkage 和 age bucket。
- [x] T3 为摘要和监控补 owner/privacy/边界测试。
- [x] T4 建立统一 cloud Runtime Facade，并抽取共享租约心跳。
- [x] T5 迁移 Siri、微信 Bot、Telegram 查询/写入与 voice shortcut。
- [x] T5a 为 Siri、微信和 Telegram 建立每用户每渠道的连续 Agent 会话。
- [x] T5b starter pregen 保持显式排除：它是无用户提交、只读、可丢弃的预生成缓存，不创建 durable Run。
- [x] T6a 完成 Runtime 聚焦回归、真实 PostgreSQL 并发和迁移验证。
- [x] T6a-1 Runtime circuit 暂停/不可用时查询可降级，写工具在派发前
  fail-closed；外部渠道缺少 provider message ID 时拒绝执行。
- [x] T6a-2 多条 Telegram directive 回放按外部消息身份恢复完整回执；
  重复外部会话迁移时将 messages/runs 一并归并到 canonical conversation。
- [x] T6a-3 重复会话迁移兼容 Runtime 的 active-run 与
  `(conversation_id, input_seq)` 真实唯一约束：冲突活跃 Run/Attempt 先转入
  reconciliation，再无损重排被合并 Run 的 input sequence。
- [x] T6a-4 `/send` 与 `/stream` 接口级测试证明 circuit 暂停信号完整传递到
  Executor；读取继续服务，模型动态选择的写工具在派发前 fail-closed。
- [x] T6b 完成独立安全复审。
- [ ] T6c 提交、部署和生产窗口验证。

## G3 · 测试闸

- SQLite Runtime/Kernel/渠道最终聚焦回归：`370 passed`；额外
  family-health / security 入口回归：`18 passed`。此前更广组合回归为
  `421 passed, 3 skipped`，跳过项仅为 PostgreSQL 行锁专属用例。
- 真实 PostgreSQL 15 并发回归：`9 passed`，包含会话串行化、rollout
  pause/admission 竞态和 late reconciliation。
- 真实 PostgreSQL 旧 schema 迁移验证：
  - contract snapshot 三字段全部创建；
  - 重复 external channel session 保留一条，其余 session key 置空；
  - 重复会话下的 `agent_messages` 与 `agent_runs` 全部迁入 canonical
    conversation；
  - 两个重复会话各自已有 active Run、且 `input_seq` 冲突时，迁移后保留
    3 个 Run 并重排为 `1/2/3`，只保留 canonical active Run；重复 active
    Run/Attempt 转为 `reconciliation_required` / `failed`；
  - partial unique index 创建成功；
  - 两组迁移连续执行两次无错误，第二次零变更。
- Runtime/渠道聚焦组合回归：`291 passed`。
- 新增安全边界 RED→GREEN 用例：`6 passed`，覆盖 circuit write
  fail-closed、外部 delivery ID、directive replay 和 migration merge。
- Ruff（本轮 Runtime/Kernel/渠道文件）：通过。
- Python compileall、`git diff --check`：通过。
- **裁决：PASS。**

## G4 · 安全闸

- 静态约束已落实：
  - Run Ledger 新字段只保存固定版本号与静态合同 SHA-256。
  - 外部消息身份、工具逻辑键和低熵用户标识使用按域隔离的
    HMAC-SHA256，不写 OpenID、Telegram message ID 或健康文本。
  - Runtime 监控只返回聚合计数和版本分布。
  - direct write 统一经过 ToolGateway/operation ledger/verified receipt。
  - Siri 每次调用生成新的 `Idempotency-Key`；微信/Telegram 使用提供方
    message ID 生成内容无关的幂等身份。
  - 同一渠道会话由数据库 partial unique index 强制唯一。
  - Runtime circuit 暂停或存储不可用时，read 工具仍可降级服务，write
    工具在业务派发前返回 `runtime_control_unavailable`，不绕过 operation
    ledger。
  - 微信、Siri、Telegram 外部入口缺少 provider delivery ID 时 fail-closed，
    不再为同一次外部投递生成随机新 Run。
  - Facade 竞态测试证明 duplicate in-flight 不二次派发，dispatch 后取消进入
    reconciliation。
- 第二轮独立安全复审发现 circuit bypass、外部 delivery ID、multi-resource
  replay 和重复会话上下文归并四项缺口；均已按上述测试闭环修复。
- 第三轮独立安全复审发现旧会话合并 SQL 会撞 Runtime 的真实唯一索引；
  已以真实 SQLite/PostgreSQL schema RED→GREEN 修复，并补齐 `/send`、
  `/stream` 暂停态入口测试。
- 最终独立安全复审发现 Telegram 缺少 provider message ID 时日志包含原始
  `chat_id`；已按 RED→GREEN 删除外部标识并增加日志隐私测试。
- 最终复审结论：**GO**，无 P0/P1 阻断项。

## G5 · 部署健康

- 待执行。

## G6 · 上线验证

- 待执行。
