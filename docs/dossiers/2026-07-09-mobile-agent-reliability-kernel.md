# Dossier: Mobile Agent 可靠性内核

| 字段 | 值 |
|---|---|
| slug | `mobile-agent-reliability-kernel` |
| 创建日期 | 2026-07-09 |
| 当前阶段 | S4 分解 |
| 状态 | building |
| 负责 | Codex |
| 反馈环 | Mobile Jest / TypeScript / backend pytest / iOS Simulator / Mobile OTA |

## Correct Course

- [ ] Correction Block

## S0 · 用户需求（逐字）

> 思考Mobile Agent上还有哪些优化点

> 形成详细的规划，按照规划和优先级，逐个做完

- 谁用 / 解决什么 / 现在怎么绕过：高频使用 Mobile 小巴记录饮食、用药、补剂、症状并查询健康状态的用户。现状需要反复确认数据库是否写入、重新打开 App 恢复 Markdown 或图片、手动切换语音和键盘状态。
- 锚点用户相关性：直接减少 Mobile Capture 和 Agent 执行闭环中的错误、重复写入和认知负担。

## S1 · Discovery（现状勘察）

- 已有可复用：
  - `mobile/hooks/useChatEngine.ts` 已消费 SSE `status/tool/done/error`，并持久化当前 conversation id 和 pending stream 标记。
  - `mobile/components/chat/cards/types.ts`、`registry.tsx`、`mobile/services/chatCardActions.ts` 已有 allowlist、manual-confirm 和卡片 action 运行态。
  - `backend/app/services/write_intent_service.py` 已有 WriteIntent 原子确认和 `executed_ref`。
  - `backend/app/services/agent_executor.py` 已在 `tool_result` 暴露 `record_type` / `record_data`，并在 `done` 暴露 `message_id`、`completion_status`、性能和 cards。
  - `backend/app/services/agent_executor.py` 已把聊天图片上传后将 URL 写入消息历史；`mobile/hooks/useChatEngine.ts` 已恢复历史图片 URL。
  - `docs/specs/active/2026-07-06-mobile-wechat-voice-composer.md` 已定义左右两条语音入口，不重复发明交互。
- 缺口：
  - 没有统一的 `AgentTurn` 状态；流、前后台恢复、写工具和 UI 各自维护布尔值。
  - 卡片 action 成功反馈没有统一、可持久的资源回执；部分成功只返回通用 `completed`。
  - 输入栏同时维护文字、按住录音、实时听写、disabled、gesture 和提交状态，缺少单一状态机。
  - 未发送的图片和文字草稿只在组件内存中，页面重建会丢失。
  - 每条回复默认展示四个通用动作，可能与已执行的 server card / tool write 重复。
- 硬约束：
  - 写动作继续 `manual_confirm`，不提升自治等级。
  - 没有真实资源标识时不能宣称“已写入”。
  - 不新增任意 endpoint 执行能力，不让 LLM 生成未注册 UI 或写路径。
  - 语音激活必须用户显式触发；后台、提交、错误和中断必须释放 audio session。
  - 先复用现有 API/SSE；第一阶段不新增数据库表和 native dependency。

## G1 · 准入裁决（governance §8 RequirementAdmission）

- first_class_objects：`ExecutionEvent`、`WriteIntent`、`HealthAgendaItem`
- core_loop_step：Mobile Capture / Chat -> 确定性写入或查询 -> 可见执行结果 -> Today/Review
- target_surface / safety_level / autonomy_tier：Mobile Chat + Backend write result / privacy_sensitive + write boundary / manual_confirm
- spec_required：是；改变用户可见状态机、写入反馈和跨端 SSE contract。
- smallest_end_to_end_slice：一轮对话具备可恢复 turn 状态；写动作必须产生 verified receipt；输入栏只有一个合法 audio/input 状态。
- stale_surface_to_remove：每条 Agent 回复固定出现的通用四动作区；重复的局部 pending/disabled 布尔状态。
- **裁决：PASS**。用户已确认按事务型 Agent 方向形成计划并逐项实施。

## S2 · PRD

- 链接：`docs/prd/2026-07-09-mobile-agent-reliability-kernel.md`
- 引用权威：R1（统一执行层）、R5（稳定事实流）、R10（Mobile 主体验）、产品不变量“失败是系统信号”和“写自治需获得”。
- 边界：不做新诊断、处方、自动用药写入、原始音频消息、后台常驻监听或新数据库模型。
- 验收 Gate：见 PRD 与 Feature Spec。
- 未决问题：无阻塞问题。

## S3 · 规划

- 设计：`docs/plans/2026-07-09-mobile-agent-reliability-kernel-design.md`
- 实施：`docs/plans/2026-07-09-mobile-agent-reliability-kernel.md`
- Feature Spec：`docs/specs/active/2026-07-09-mobile-agent-reliability-kernel.md`
- 顺序：P0 AgentTurn -> WriteReceipt -> Composer -> 附件/上下文；P1 密度/启动/等待；P2 人格/记忆/指标。
- 发布路由：后端 contract 先部署，再发布 Mobile OTA；没有 native 改动时不走 EAS/TestFlight。

## G2 · 可行性 + 安全压测

- 评审方式：Codex challenge + 现有 WriteIntent / card-action / voice spec 对照。
- 已焊入规划的硬限制：
  - turn 状态为 additive client contract，不替换后端事实源。
  - receipt 只从确定性 API/tool result 构造，不从自然语言解析“成功”。
  - 没有资源 ID 或 `executed_ref` 时标记未验证，不展示“已写入”。
  - audio 状态机保证 hold recording 与 realtime dictation 互斥。
  - 图片草稿只存 App 私有目录，不写 AsyncStorage base64，不记录敏感内容日志。
- 待拍板分叉：无。OSS/KMS/CDN 是后续基础设施迁移，不阻塞本轮本地持久化与既有上传恢复。
- **裁决：PASS**。用户已授权按优先级逐项实施。

## S4 · 研发任务分解

- [ ] T1 AgentTurn reducer、持久化快照与 `useChatEngine` 集成（OTA）
- [ ] T2 WriteReceipt client contract、卡片 action 资源回执与 fail-closed（OTA）
- [ ] T3 Agent tool_result additive receipt（backend deploy + OTA）
- [ ] T4 Composer reducer、两条语音互斥、AppState cleanup（OTA）
- [ ] T5 输入草稿和未发送图片 App 私有目录恢复（OTA）
- [ ] T6 回复动作收敛、Today Focus 自适应折叠和等待态（OTA）
- [ ] T7 小巴记忆可见性和关键体验埋点（backend deploy + OTA）
- [ ] T8 G3/G4、模拟器视觉与发布闸
- 并发检查：当前 `main...origin/main [ahead 1, behind 108]` 且存在大量并发 WIP；继续当前工作区以保留前置修改，只编辑/提交本 feature 文件，部署必须另用干净主干 worktree。

## S5 · 实现

- 委托：health-harness-orchestrator（Codex 在当前 session 顺序执行；共享状态任务不并行写同一文件）。
- 分支 / commit：当前项目约定直接在 `main`；提交与 push 需在完成 G3/G4 后评估远端差异。

## G3 · 测试闸

- 待执行。

## G4 · 安全闸

- 触发：写路径、用药/补剂记录反馈、麦克风和健康图片隐私。
- 待实现后独立审查。

## S6 · 部署

- 待 G3/G4 通过。

## G5 · 部署健康闸

- 待部署。

## S7 · 上线验证

- 待模拟器与生产 anchor 路径验证。

## G6 · 验证闸

- 待用户真机确认。

## S8 · 沉淀

- 待完成。
