# Reva Phase 1B Chat 卡片 Action 契约实施 Dossier

> 状态:2026-06-27 Codex 隔离分支增量。对应规划: `docs/plans/2026-06-27-reva-mobile-watch-healthkit-experience-plan.md` 的 Phase 1B。

## 1. 本轮目标

把 Chat 中的动态 UI 卡片从「展示结果」推进到「可执行对象」的地基:

1. 后端 SSE `done.cards` / 历史 `message.meta.cards` 可以携带 `actions`。
2. Mobile 恢复实时和历史卡片时保留 `cardActions`。
3. `ChatBubble` 在卡片本体下方渲染动作按钮。
4. 动作执行只走白名单 dispatcher,不允许后端下发任意 endpoint 后由客户端直接 POST。

## 2. 支持的 action

- `complete_agenda`: 走 `completeAgendaItem(..., { status: 'done' })`,刷新 timeline/agenda/dashboard/twin。
- `skip_agenda`: 走 `completeAgendaItem(..., { status: 'skipped', skipReason })`,刷新 timeline/agenda/dashboard/twin。
- `confirm_write_intent`: 走 `confirmWriteIntent(id)`,刷新 write-intents/timeline/agenda/dashboard。
- `dismiss_write_intent`: 走 `dismissWriteIntent(id)`,刷新 write-intents/timeline/agenda/dashboard。

`endpoint` 字段只作为兼容/审计信息保留,客户端不会用它执行任意请求。

## 3. 安全边界

- 未知 action 返回 `unsupported`,UI 显示“不支持”,不发请求。
- 已知 action 缺少必要 payload 返回 `invalid`,不发请求。
- 写入类动作仍通过既有 WriteIntent / Agenda 手动确认或完成链路,不新增医疗诊断、处方、剂量建议。
- 本轮不做流式交织、不接 watch LLM 自由对话、不改后端安全门。

## 4. 工程落点

- `mobile/components/chat/cards/types.ts`:新增 `CardActionDescriptor`。
- `mobile/components/chat/cards/registry.tsx`:保留服务端卡片 actions。
- `mobile/hooks/useChatEngine.ts`:实时和历史卡片恢复时写入 `UIMessage.cardActions`。
- `mobile/services/chatCardActions.ts`:白名单 action dispatcher。
- `mobile/components/chat/ChatBubble.tsx`:渲染卡片 action 按钮并调用 dispatcher。

## 5. 下一步

- 后端 `done.cards` 开始在可执行卡片上生成 `actions`。
- Card action success 后可把按钮翻态为“已完成/已确认”,而不是只 toast。
- Phase 2 再做 token 流中的卡片交织,避免本轮扩大编排面。
