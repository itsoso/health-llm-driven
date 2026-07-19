# Dossier: Mobile Agent 可靠性内核

| 字段 | 值 |
|---|---|
| slug | `mobile-agent-reliability-kernel` |
| 创建日期 | 2026-07-09 |
| 当前阶段 | S5 验证 |
| 状态 | verifying |
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

- [x] T1 AgentTurn reducer、持久化快照与 `useChatEngine` 集成（OTA）
- [x] T2 WriteReceipt client contract、卡片 action 资源回执与 fail-closed（OTA）
- [x] T3 Agent tool_result additive receipt（backend deploy + OTA）
- [x] T4 Composer reducer、两条语音互斥、AppState cleanup（OTA）
- [x] T5 输入草稿和未发送图片 App 私有目录恢复（OTA）
- [x] T6 回复动作收敛、Today Focus 自适应折叠和等待态（OTA）
- [x] T7 小巴记忆可见性和关键体验埋点（backend deploy + OTA）
- [ ] T8 G3/G4、模拟器视觉与发布闸
- 并发检查：当前 `main...origin/main [ahead 2, behind 110]` 且存在大量并发 WIP；继续当前工作区以保留前置修改，只编辑/提交本 feature 文件，部署必须另用干净主干 worktree。

## S5 · 实现

- 委托：health-harness-orchestrator（Codex 在当前 session 顺序执行；共享状态任务不并行写同一文件）。
- 分支 / commit：当前项目约定直接在 `main`；提交与 push 需在完成 G3/G4 后评估远端差异。
- 已落地：统一 AgentTurn / Composer 状态机、写入回执、账户隔离、请求 ACK 与断流恢复、输入草稿和图片恢复、双语音入口互斥、提交后停听、Today Focus 和来源可见性。
- 第二轮加固：server-side `client_turn_id` 幂等、未最终落盘回复禁止回放、软写失败 fail-closed、跨天卡片回执身份、私有健康图片签名访问、部分图片失败回滚、语音最终文本与 hydration 竞态防护。
- 发布前加固：单个模型响应的完整写计划在任何工具执行前封存；恢复时 `planned / in_flight / uncertain` 一律 fail-closed；会话图片引用、删除和 tombstone 清理使用跨线程/跨进程生命周期锁并在文件锁后读取最新 DB 引用；非持久化 Agent 请求在 HTTP 与 Mobile 消息终态上统一为可重试中断。
- 语音与工具恢复加固：服务端语音转写改为 DashScope Qwen ASR 主路径，OpenAI Whisper 仅在独立隐私开关显式启用时备用，并设置供应商/总请求超时；裸写工具文本必须匹配用户明确意图；显式“删除最后一餐”在写 checkpoint 前用未截断查询解析为精确 ID，`list` 永不隐式删除，含混/否定/教学式请求均 fail-closed。
- 2026-07-16 中间失败恢复加固：生产 `run_790af0ae63724445` 先收到一次参数不完整的 `health_manage` 失败事件，随后以 `record_id=829` 重试删除成功并取得 verified receipt；服务端持久化正文与终态均为成功，但 Mobile 曾把中间失败事件提前拼进永久正文。客户端现仅用工具事件更新进度/状态，整轮失败继续由后端终态文本或流级 `error` 呈现，避免“先失败、后成功”同时出现在一条回复中。
- 2026-07-16 北京时间饮食查询加固：生产 `run_2076443f42b949f6` 把“重新列出今天吃的东西”误生成为 `health_manage update`，且后续 `run_47f2d072877a4fc2` 把“今天”错误解析为历史日期 `2026-07-14`。现于两条 Agent 工具执行链的写计划封存前加入只读查询护栏：无明确写命令时，饮食调用确定性降级为 `list`；今天/昨天/前天由服务端按北京时间覆盖模型日期。明确修改或删除仍走原写回执状态机。
- 2026-07-16 日期显示二次加固：用户截图对应的 `run_47f2d072877a4fc2` 生成于首版护栏部署前；除修正工具参数外，现把当日北京时间日期注入 fast/full 系统提示，并在仅供模型消费的饮食查询结果前附加 `Asia/Shanghai + 查询日期`。最终持久化正文中的“北京时间 X月X日”也按该只读查询目标日期确定性校正，避免旧历史标题污染新回复。
- 2026-07-18 P0/P1 重新基线：移除 Mobile 长按 Agent 回复后从自然语言正文推断并调用 `/quick-record` 的旧写入入口；健康写入只通过 Agent 工具或带 capability/receipt 的动态卡片。补齐 `chat_turn_queued` 前后端严格契约，仅保留 surface、channel、队列深度，拒绝正文和资源标识，避免可靠性看板静默丢失或收集健康隐私。

## G3 · 测试闸

- Backend 受影响回归：两组不重叠测试共 `581 passed`（核心可靠性/饮食/上传/迁移/client events `272`，来源/GenUI/医疗记录/工具校验 `309`）。
- Mobile 全量 Jest：`220 suites / 1511 tests passed`；现有 Jest runner 仍需 `--forceExit` 才能返回，作为非阻塞测试基建债跟踪。
- 静态检查：Mobile `tsc --noEmit`、Backend `ruff` / `py_compile`、`git diff --check` 均通过。
- 2026-07-14 增量回归：Backend 受影响面 `243 passed`；Mobile 全量 `244 suites / 1720 tests passed`；DashScope 合成音频经真实配置返回非空转写；iPhone 17 Pro Simulator 原生构建 `0 errors` 并完成页面截图验收。
- 2026-07-16 中间工具失败恢复回归：新增失败事件后 verified retry 的 SSE 顺序用例；`chatStream`、`useChatEngine`、`useVoiceConversation` 共 `60 passed`，Mobile TypeScript、受影响文件 ESLint 与 `git diff --check` 通过。
- 2026-07-16 北京时间饮食查询回归：只读误更新、模型旧日期覆盖、“饮食记录”名词消歧、明确写入不误降级及写回执状态机共 `68 passed`。
- 2026-07-16 日期显示二次回归：日期标签校正、模型工具上下文、fast/full 日期基准、工具归一化、写回执与 fast 路由共 `137 passed`。
- 2026-07-18 P0/P1 定向回归：Mobile Chat/埋点 `46 passed`，TypeScript、受影响文件 ESLint、`git diff --check` 通过；后端 `EventIn` 无数据库合约校验通过。完整 `test_client_events.py` 仍需在具备项目 PostgreSQL 角色的环境执行。
- 真实 PostgreSQL：主业务连接池保持未占用；turn lock 专用池 `pool_size=8 / max_overflow=0`；跨 worker 全局槽上限 `16`，超限 fail-closed。
- 文档闸：42 份 Dossier 一致性通过；system-map/doc drift 检查通过。
- **裁决：PASS**。模拟器视觉与真机音频验证归入 T8 / G6，不替代自动化测试结论。

## G4 · 安全闸

- 触发：写路径、用药/补剂记录反馈、麦克风和健康图片隐私。
- 第六至第八轮独立审查提出完整写计划、legacy 图片用户隔离、图片清理 TOCTOU、非持久化 HTTP 状态、Mobile 终态、卡片持久化与图片引用提交竞态等发布阻断问题；均已补回归测试并修复。
- 第九轮独立复审结论：无 Critical、无 Important，未发现 at-most-once、共享图片或中断卡片的同等级绕过，允许发布。
- 已知非阻断残余：worker 若在图片原子落盘后、数据库引用提交前被 `SIGKILL`，异常清理来不及执行，可能留下仅当前用户可访问的无引用私有文件；不造成重复写或跨用户损坏，后续应增加按 DB 引用集合清扫的回收任务。
- **裁决：PASS**。

## S6 · 部署

- 2026-07-16 北京时间饮食查询护栏随 `0da73b2dc` 通过标准 `./deploy.sh -b` 发布。首次尝试被 env 完整性守卫拦截（本地缺少生产已有的 `ORCHESTRATOR_SYNTHESIS_MODEL_ID`）；从生产安全收敛该键到本地配置后重新执行，未使用强制绕过。
- 2026-07-16 日期显示二次加固随 `6fcc9ca86` 通过标准 `./deploy.sh -b` 发布；仅后端逻辑与测试变化，无需 Mobile OTA 或原生包更新。

## G5 · 部署健康闸

- 2026-07-16 部署健康度 `60/60 PASS`，skills manifest 本地/线上 `22/22`；服务器实际提交 `0da73b2dc`，`health-backend` 为 active，内网与公网 `/api/v1/health` 均确认 API、PostgreSQL、Redis、Celery 正常。
- 2026-07-16 二次发布健康度 `60/60 PASS`，skills manifest 本地/线上 `22/22`；服务器实际提交 `6fcc9ca86`，`health-backend` 为 active，内网与公网 `/api/v1/health` 再次确认全部依赖正常。
- **裁决：PASS**。

## S7 · 上线验证

- iPhone 17 Pro Simulator 原生构建、安装和启动成功（0 errors，9 warnings）；macOS 当前锁屏，截图、键盘遮挡、前后台恢复和双语音交互仍待解锁后验证。

## G6 · 验证闸

- 待用户真机确认。

## S8 · 沉淀

- 待完成。
