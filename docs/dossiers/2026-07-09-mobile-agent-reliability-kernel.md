# Dossier: Mobile Agent 可靠性内核

| 字段 | 值 |
|---|---|
| slug | `mobile-agent-reliability-kernel` |
| 创建日期 | 2026-07-09 |
| 当前阶段 | S6 部署 |
| 状态 | releasing |
| 负责 | Codex |
| 反馈环 | Mobile Jest / TypeScript / backend pytest / EAS production build / TestFlight |

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
- 发布路由：后端 contract 先部署；本轮虽以 JS/TS 为主，但用户于 2026-07-10 明确要求 TestFlight，因此走 EAS production build + auto-submit，不以 OTA 代替正式测试包。

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
- [x] T8 G3/G4、构建链与发布前自动化闸
- 并发检查：发布在独立集成 worktree `codex/mobile-agent-reliability-kernel` 完成；原始 `main` 工作区的并发 WIP 不纳入暂存或部署。

## S5 · 实现

- 委托：health-harness-orchestrator（Codex 在当前 session 顺序执行；共享状态任务不并行写同一文件）。
- 分支 / commit：当前项目约定直接在 `main`；提交与 push 需在完成 G3/G4 后评估远端差异。
- 已落地：统一 AgentTurn / Composer 状态机、写入回执、账户隔离、请求 ACK 与断流恢复、输入草稿和图片恢复、双语音入口互斥、提交后停听、Today Focus 和来源可见性。
- 第二轮加固：server-side `client_turn_id` 幂等、未最终落盘回复禁止回放、软写失败 fail-closed、跨天卡片回执身份、私有健康图片签名访问、部分图片失败回滚、语音最终文本与 hydration 竞态防护。
- 发布前加固：单个模型响应的完整写计划在任何工具执行前封存；恢复时 `planned / in_flight / uncertain` 一律 fail-closed；会话图片引用、删除和 tombstone 清理使用跨线程/跨进程生命周期锁并在文件锁后读取最新 DB 引用；非持久化 Agent 请求在 HTTP 与 Mobile 消息终态上统一为可重试中断。

## G3 · 测试闸

- Backend 受影响回归：`597 passed`，覆盖 Agent 幂等/恢复、饮食权威写入、私有图片生命周期和用户隔离、迁移、GenUI、医疗记录与工具校验。
- Mobile 全量 Jest：`228 suites / 1587 passed / 1 skipped`；现有 Jest runner 仍需 `--forceExit` 才能返回，作为非阻塞测试基建债跟踪。
- 发布阻断定向回归：Mobile `4 suites / 68 passed`；Backend 饮食与上传 `47 passed`。覆盖账号切换持久化、共享 Voice session、识别并保存事务、legacy 图片 capability 和跨用户读取。
- 静态检查：Mobile `tsc --noEmit`、Backend `ruff` / `py_compile`、`git diff --check` 均通过。
- 构建链：全新 `npm ci` 成功，`expo-modules-autolinking` patch 真实应用；修复了旧 patch 非标准空白上下文导致 `patch-package` 解析失败且被 `|| true` 掩盖的问题。
- 真实 PostgreSQL：主业务连接池保持未占用；turn lock 专用池 `pool_size=8 / max_overflow=0`；跨 worker 全局槽上限 `16`，超限 fail-closed。
- 文档闸：43 份 Dossier 一致性通过；system-map/doc drift 检查通过，代码派生 service roster 更新为 `324`。
- App Store 提交预检：bundle `life.executor.health`、ASC app `6763569720`、EAS production profile 与 auto-submit 脚本通过。
- **裁决：PASS**。锁屏状态下无法完成本轮模拟器截图和真实麦克风验证；真机音频、键盘遮挡和前后台切换仍归入 G6，不以自动化测试代替。

## G4 · 安全闸

- 触发：写路径、用药/补剂记录反馈、麦克风和健康图片隐私。
- 发布复审继续发现并关闭同帧重复提交、账号 scope 延迟解析、双 Voice hook 全局单例竞态、`recognize-and-save` 绕过 guard / 图片 fail-open、client-controlled `image_url`、legacy capability 重签名和旧 user-id 查询缺少隔离等阻断问题。
- 最终独立复审结论：所有前述 Critical/Important 均 CLOSED；canonical owner-scoped 图片仍可签名读取，legacy 饮食图片不再签发 capability 或参与自动删除，旧 user-id 查询仅允许本人或管理员。
- 依赖审计例外：`npm audit --omit=dev` 仍报告旧 Voice/HealthKit Expo config plugin 的 build-time XML 依赖，以及 `react-native-markdown-display` 无上游修复的复杂度告警。EAS 只处理仓库内受控 plist/XML，运行时 Markdown 长度受 Agent 输出上限约束；本轮不以强制降级原生语音或跨 Expo 版本升级换取表面绿灯，后续替换弃用插件并升级 Expo patch line。
- 已知非阻断残余：worker 若在图片原子落盘后、数据库引用提交前被 `SIGKILL`，异常清理来不及执行，可能留下仅当前用户可访问的无引用私有文件；不造成重复写或跨用户损坏，后续应增加按 DB 引用集合清扫的回收任务。
- **裁决：PASS**。

## S6 · 部署

- 自动化与构建链闸已通过；准备提交、推送、通过 `deploy.sh` 部署 backend，再触发 EAS production build + auto-submit。

## G5 · 部署健康闸

- 待部署。

## S7 · 上线验证

- iPhone 17 Pro Simulator 原生构建、安装和启动成功（0 errors，9 warnings）；macOS 当前锁屏，截图、键盘遮挡、前后台恢复和双语音交互仍待解锁后验证。

## G6 · 验证闸

- 待用户真机确认。

## S8 · 沉淀

- 待完成。
