# Dossier: Chat Model Switcher And Routing Transparency

| 字段 | 值 |
|---|---|
| slug | `chat-model-switcher-and-routing-transparency` |
| 创建日期 | 2026-07-06 |
| 当前阶段 | S4 研发 |
| 状态 | building |
| 负责 | Claude |
| 反馈环 | 本地 jest/tsc/swift test → PR CI → OTA |

## S0 · 用户需求

> 支持对话中切换模型,继续做模型的性能优化

背景:2026-07-02 上线的 FAST-MODEL 快路由会在"简单记录/查询"回合把无显式选择的请求自动路由到最快可靠工具模型(当前=DeepSeek V4 Flash)。用户在 mobile 端把偏好设为 qwen3.7-max 后,简单查询仍走 DeepSeek(档案级偏好会被快路由接管),且客户端不显示切换原因,用户以为配置没生效。

## G1 · 准入裁决

- first_class_objects:无新增(复用 `UserProfile.llm_model_id`、model registry、`extra_context.model_id` 既有契约)
- core_loop_step:对话输入 → 模型路由(显式选择>快路由>档案偏好)→ 回答 → meta 透明化回显
- target_surface / safety_level / autonomy_tier:Mobile + Mac / 非医疗内容路径(纯路由与展示) / manual(用户显式选择)
- smallest_end_to_end_slice:mobile 选择器选中具体模型时逐条消息带显式 `model_id`(后端绝不覆盖);"系统默认"保留快路由优化;两端把 `fast_route_simple_turn` 渲染成人话。后端零改动。
- 裁决:PASS。

## S2/S3 · 计划

1. mobile:聊天头部已有 `LlmModelPicker`(档案级 PUT)。在 `useChatEngine.sendMessage` 收口注入:当会话选择了具体模型时,把 `model_id` **合并**进已有 extraContext JSON(不能覆盖 Siri/opener 字段;非 JSON 历史串防御处理)。
2. mobile:ChatBubble meta footer 渲染 `fallback_reasons` 中文标签(`fast_route_simple_turn` → 「简单查询·自动用快模型」等),done 事件与历史 meta 双路径。
3. mac:`ChatTranscriptHTML.fallbackReasonLabel` 补 `fast_route_simple_turn` case + 渲染断言测试(Mac 逐条消息显式选择已存在,无行为改动)。
4. 测试:extraContext 合并三态(已有 JSON/空/非 JSON)、reason 标签映射、tsc + jest + swift test。

## G2 · 风险压测

- 不改后端路由/安全逻辑;显式 `model_id` 走既有 `_extract_model_id_from_extra_context` 白名单校验。
- 快路由语义不变:"系统默认"档继续享受延迟优化;显式选择恒不被覆盖(既有后端不变量)。
- extraContext 注入若覆盖已有字段会破坏 Siri/opener 上下文 → 收口单点合并 + 三态测试钉死。
- 裁决:PASS。

## G3 · 测试闸

- mac:`swift test --filter ChatTranscriptHTMLTests` 全绿(含新增 `testMetaFooterRendersFastRouteReasonInChinese`);全量 suite 中 `WearablePanelViewSnapshotTests` 2 例快照失败为环境性假红(基线需特定环境重录,与本改动模块无关,CI 为准)。
- mobile:`npx tsc --noEmit` exit 0;新增/扩展套件 `chatExtraContext.test.ts` + `chatTransparency.test.ts` 14/14 过;`hooks/__tests__ + components/chat/__tests__` 全量 27 套件中 25 过,`useAuth` / `ChatScreenHistoryEntry` 批量跑红、隔离复跑均绿(并发 open-handles 污染假红,与本改动无关)。
- 实现要点修正:mobile 已有 `LlmModelPicker`(档案级 PUT),本次不是新建选择器,而是让"选择器显示什么模型,消息就用什么模型"——选中具体模型时逐条消息带显式 `model_id`(含冷启动从档案恢复的选择),"系统默认"改文案为「系统默认 · 智能路由」并保留快路由。

## 研发任务 / 验证记录

- Run ledger: `docs/_generated/harness-runs/077c11144163.jsonl` (run_id 077c11144163, 本地不提交)
- 后台代理两次起步 stall(watchdog 600s),已改为主线程接管实现;worktree 曾被并发 session `git worktree prune` 清孤儿,重建于 scratchpad。
