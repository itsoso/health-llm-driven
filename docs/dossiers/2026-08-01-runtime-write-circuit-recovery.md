# Dossier: Runtime 写入熔断恢复与作用域修复

| 字段 | 值 |
|---|---|
| slug | `runtime-write-circuit-recovery` |
| 创建日期 | 2026-08-01 |
| 当前阶段 | S4 分解 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mac/Mobile/Web targeted verification |

## Correct Course

- [ ] Correction Block
  - 触发:
  - 旧基线:
  - 新基线:
  - 回退阶段:
  - 需重跑 Gate:
  - 用户确认:☐

## S0 · 用户需求（逐字）

> 这个基本能力都没了 思考这个设计和实现 哪里出了问题 如何修复
>
> 确认

- 谁用 / 解决什么 / 现在怎么绕过: 小巴用户自然语言记录饮食；目前被全局熔断，只能等待或去专页手工记录。
- 锚点用户相关性: 饮食捕获是 Health OS 的高频 `WriteIntent -> ExecutionEvent` 入口。

## S1 · Discovery（现状勘察）

- 已有可复用:
  - `backend/app/services/agent_write_outcome.py`: verified/rejected/failed/uncertain 单一分类。
  - `backend/app/services/agent_runtime_rollout.py`: durable singleton circuit 与 generation ack。
  - `backend/app/services/diet_voice_parser.py`: 明确关键词优先、本地小时兜底的餐次推断。
  - `docs/dossiers/2026-07-31-record-write-outcome-reliability.md`: 前一未决写入的回执/重试证据。
- 缺什么:
  - pre-dispatch Runtime block 没有成为 Executor 终态；模型继续改写故障。
  - singleton reconciliation pause 无用户/系统性阈值作用域。
  - 裸“记录吃了…”不能进入 `simple_health_record`。
  - `tools_used` 尝试事实被 UI 表述为完成调用；草稿压制依赖工具名而非回执。
- 生产证据:
  - `run_e272f2a009f44346`: 9 轮，intent=`write/diet/create`，每次写前因 `circuit_paused` 拦截。
  - `run_a36355c055424ad4`: 4 轮，已编译 `diet/snack/一个桃子`，仍被同一 circuit 拦截。
  - rollout state: `paused / reconciliation_detected / generation=5 / acknowledged=4`。
  - production deployed SHA 在已有 `bc48f7288` typed write-outcome 修复之前。
- 硬约束 / 平台·安全边界:
  - missing receipt 不盲重试；无 health payload 进 Runtime telemetry；用户隔离；生产恢复需 exact generation。
- 链接: `docs/plans/2026-08-01-runtime-write-circuit-recovery-design.md`

## G1 · 准入裁决

- first_class_objects: `WriteIntent`, `ExecutionEvent`, `HealthTwin`
- core_loop_step: 执行动作 → execution event → verified receipt / review
- target_surface / safety_level / autonomy_tier: Backend + Mac/Mobile/Web / privacy-sensitive write / unchanged
- spec_required: yes — `docs/specs/runtime-write-circuit-recovery-spec.md`
- smallest_end_to_end_slice: 两条锚点原句 → scoped Runtime → one tool terminal → verified receipt / typed block
- stale_surface_to_remove: typed block 后的通用“补充详情”回复
- **裁决**: PASS —— 属于主循环可靠性修复，不增加医疗结论或自治。
- 用户确认: ☑

## S2 · PRD

- 链接: `docs/specs/runtime-write-circuit-recovery-spec.md`（bugfix 使用 focused feature spec）。
- 边界: 不盲 replay、不改生产健康内容、不放宽 receipt/nutrition、安全暂停仍可全局升级。
- 验收 Gate: exact phrases、one-attempt terminal、scoped/global admission、跨端透明度、prod receipt。
- 未决问题: 无。

## S3 · 规划

- 设计: `docs/plans/2026-08-01-runtime-write-circuit-recovery-design.md`
- 实施: `docs/plans/2026-08-01-runtime-write-circuit-recovery.md`。
- 分阶段 + 反馈环路由: Backend TDD → client wording → integration/safety → circuit ack → backend deploy → prod exact-phrase smoke。
- 长杆: 作用域放行必须保留 managed Runtime，不得退化成 unmanaged write。

## G2 · 可行性 + 安全压测

- 评审方式: ☑ Codex challenge based on production ledger and source trace。
- 硬阻断:
  - 未决用户自身仍 fail-closed；阈值/人工/陈旧 lease/控制面不可用仍全局 fail-closed。
  - unrelated user 只能通过正常 managed Run 放行，不能 bypass Runtime。
  - circuit terminal 必须证明 `dispatch_started=false`。
  - error/reconciliation 不能生成通用重试 action。
- 待拍板分叉: 无；用户已确认分阶段设计。
- **裁决**: PASS —— 用户确认: ☑

## S4 · 研发任务分解

- 跨端 API 契约: additive `turn_outcome.category=service_unavailable`; `tools_used` 保持兼容。
- 任务表:
  - [ ] T1 裸饮食短句的 deterministic goal + 餐次推断。
  - [ ] T2 pre-dispatch Runtime block 一次终止 + typed outcome。
  - [ ] T3 单 reconciliation 用户级隔离 + 阈值升级全局。
  - [ ] T4 receipt/pending 驱动草稿压制。
  - [ ] T5 Mac/Mobile/Web 失败轮显示“尝试调用 Skill”。
  - [ ] T6 集成测试、安全复核、提交推送。
  - [ ] T7 exact-generation 恢复、部署、生产原句验证。
- 并发检查: `git fetch origin main` + open PR checked；无相同作用域 PR。隔离 worktree 基于 `7b277ed0f`。☑

## S5 · 实现

- 分支: `codex/runtime-write-circuit-recovery`
- commits: pending

## G3 · 测试闸

- 集成闸: pending
- main CI 真实色: pending
- Codex capstone: pending
- **裁决**: pending

## G4 · 安全闸

- 触发: health write path, Runtime control, retry semantics, owner isolation。
- 评审: pending
- **裁决**: pending

## S6 · 部署

- 路由: backend-deploy；client release only if changed and required。
- 部署 SHA / 回滚点: pending

## G5 · 部署健康闸

- 健康分 / prod smoke: pending
- **裁决**: pending

## S7 · 上线验证

- 真实路径: 两条用户原句、owner-scoped persisted lookup、Runtime state、startup/error scan。
- 结果: pending

## G6 · 验证闸（人在环）

- prod 对 anchor 用户真成立: pending
- 真机/发布用户确认: pending
- **裁决**: pending

## S8 · 沉淀

- 新坑: circuit scope 与 typed terminal 进入 Runtime design/agent operating docs（如结构变化要求）。
- 文档同步: doc drift 结果决定；计数仅取生成文件。
- 状态: building
