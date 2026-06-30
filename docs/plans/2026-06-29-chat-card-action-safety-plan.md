# 2026-06-29 Chat 动态卡片 action 安全可见性计划

> 目标:Chat 动态 UI 卡片里的写入动作必须显式 `requires_manual_confirm=true` 才展示给用户,避免出现点了才失败的伪按钮。

## 背景

- Chat card registry 已支持后端下发 `actions` 并在卡片下方渲染按钮。
- `dispatchChatCardAction` 服务层会拒绝缺少 `requires_manual_confirm=true` 的写入动作。
- 但 UI 层原先只按 action allowlist 过滤,可能把缺少人工确认的写动作展示给用户,点击后才失败。

## 实施

- `route.open` 可直接展示,因为它只是导航。
- `agenda.complete`、`write_intent.confirm`、`write_intent.dismiss` 等写动作必须带 `requires_manual_confirm=true` 才展示。
- 保留 `cards_group` 子卡 action 的回归测试,确保多卡回复仍能点击子卡按钮。

## 验收

- registry 测试确认 unsafe write action 被过滤。
- registry 测试确认 cards_group 子卡 action 仍可点击。
- `useChatEngine` 测试确认流式 card actions 仍保留。
- `chatCardActions` 测试确认服务层仍 fail-loud。

## 状态

- 当前状态:已实现并通过本地测试。
