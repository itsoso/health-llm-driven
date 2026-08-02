# Dossier: Runtime 写入熔断恢复与作用域修复

| 字段 | 值 |
|---|---|
| slug | `runtime-write-circuit-recovery` |
| 创建日期 | 2026-08-01 |
| 当前阶段 | S6 部署准备 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Backend deploy + Mac/Mobile/Web targeted verification |

## Correct Course

- [x] Correction Block
  - 触发: producer review 发现已确认历史 reconciliation owner 会污染新 scope，且已解决但未 ack 的 Run 仍会被计入。
  - 旧基线: 按所有 `status=reconciliation_required` 历史 Run 取 owner。
  - 新基线: generation-ack 当前事件 window ∩ 仍为 reconciliation-required 的 Run；事件账本不一致全局 fail-closed。
  - 回退阶段: S4 / S5。
  - 需重跑 Gate: G3 + G4。
  - 用户确认:☑（不改变已确认的分阶段恢复边界，仅收紧 owner scope）

## S0 · 用户需求（逐字）

> 这个基本能力都没了 思考这个设计和实现 哪里出了问题 如何修复
>
> 确认
>
> 允许
>
> 使用 qwen-max-3.7 评测

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
  - [x] T1 裸饮食短句的 deterministic goal + 餐次推断。
  - [x] T2 pre-dispatch Runtime block 一次终止 + typed outcome。
  - [x] T3 单 reconciliation 用户级隔离 + 阈值升级全局。
  - [x] T4 receipt/pending 驱动草稿压制。
  - [x] T5 Mac/Mobile/Web 失败轮显示“尝试调用 Skill”。
  - [x] T6 集成测试、静态检查、提交前 producer review。
  - [ ] T7 exact-generation 恢复、部署、生产原句验证。
- 并发检查: `git fetch origin main` + open PR checked；无相同作用域 PR。隔离 worktree 基于 `7b277ed0f`。☑

## S5 · 实现

- 分支: `codex/runtime-write-circuit-recovery`
- 实现结果:
  - 两条锚点短句均编译为单一 `simple_health_record(diet/create)`；无餐次时复用本地小时推断。
  - `runtime_control_unavailable + dispatch_started=false` 成为单次 deterministic error terminal，不再进入后续 LLM 轮次。
  - 当前未确认 reconciliation window 仅隔离仍未解决的 owner；已确认历史 owner 与已解决 Run 不污染新 scope；达到配置的 distinct-user 阈值才升级全局暂停；事件账本不一致时保持全局 fail-closed；所有放行仍创建 managed Run。
  - intake 卡片压制只接受 verified receipt / server-owned pending intent，不再采信 `tools_used` 尝试事实。
  - Mac/Mobile/Web 错误或中断回合显示“尝试调用 Skill”；Web 历史与 live SSE 均贯通 `completion_status`。
- commits: `8c72d16c6`、`3055833b1`、`90501427c`、`9453a33f0`；并发主干 `acc910fd9` 同步修正 fruit trajectory golden/scorer。

## G3 · 测试闸

- Backend 集成闸: 297 passed / 3 skipped；skip 为 SQLite 环境不执行的 PostgreSQL row-lock 用例。
- Client: Mobile targeted 17 passed + TypeScript PASS；Web targeted 25 passed + TypeScript PASS；Mac ChatTranscriptHTML 51 passed。
- 静态/治理: Ruff `F821,F822,E9` PASS；doc drift PASS；dossier consistency PASS；`git diff --check` PASS。
- LLM live-change 首次 main CI `30705987231`: 按预期因未设置一次性确认变量在发送真实模型前 BLOCK；未带红部署。
- 用户明确批准目的地与模型后，TokenPlan `qwen3.7-max` live gate PASS：invariants `12/12`、health_agent_core `50/50`、orchestrator `5/5`（avg `0.94`、0 regression）、trajectory contract `12/12`、golden `9/9`；原始聚合 JSON 仅保存在本机 `/tmp/runtime-write-circuit-live-eval-20260801.json`，无生产健康正文入库。备用 OpenAI endpoint 在本次命令中指向本机不可用端口，未发生第二外部目的地 fallback。
- 并发主干 golden 修复复核：`test_agent_trajectory_scorer.py` + `test_llm_synthesis_regression_gate.py` 共 57 passed；offline gate PASS。
- main CI 真实色: 设置一次性确认变量后的新 run 待复核，成功后必须立即删除变量。
- **裁决**: 本地 + live LLM PASS；远端 CI 待一次性确认闭环。

## G4 · 安全闸

- 触发: health write path, Runtime control, retry semantics, owner isolation。
- producer review:
  - 未决 owner fail-closed；未命中 scope 的暂停原因仍全局 fail-closed。
  - scoped admission 只查询 generation/ack 与 content-free reconciliation event/status/owner；历史已确认 owner 与已解决 Run 被排除，账本不一致全局 fail-closed，且放行必须经 coordinator 创建 managed Run。
  - 不 replay、不自动 retry、不改未决健康记录；只有 verified receipt 可声明持久化成功。
  - `tools_used` 保持尝试事实，UI 由终态降级表述；错误回合不开放社交分享。
- reviewer: independent producer review；Critical 0、Important 0（历史 scope 与 unknown 透明度问题均已修复并回归）。
- 上线兼容 Gate: 必须先验证 production content-free event count 与 durable generation 一致；不一致则按设计继续全局 fail-closed，不得宣称 scoped recovery。
- **裁决**: PASS

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
