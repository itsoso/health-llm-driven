# Dossier: Chat 动态卡片 action 安全可见性

| 字段 | 值 |
|---|---|
| slug | `chat-card-action-safety` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 继续执行

本切片承接本周计划 P1:Chat + 动态 UI 卡片融合。动态卡片不仅要能显示,还要保证用户看到的 action 是可执行且符合手动确认边界的。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/components/chat/cards/registry.tsx`:卡片 registry、server card 渲染、action button 渲染。
  - `mobile/services/chatCardActions.ts`:写动作执行层,要求 `requires_manual_confirm=true`。
  - `mobile/hooks/useChatEngine.ts`:流式 `card` / `done.cards` 下发进入 UIMessage。
- 缺口:
  - UI 层原先只按 action allowlist 过滤,缺少 `requires_manual_confirm=true` 的写动作仍会显示,点击后才失败。
  - 多卡 `cards_group` 子卡 action 虽已有实现,缺少回归测试。
- 硬边界:
  - 不放宽写动作 endpoint。
  - 不允许模型任意 endpoint 透传。
  - 不让缺少人工确认的写动作出现在 UI。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`WriteIntent`, `HealthAgendaItem`, `ExecutionEvent`, `ProvenanceRecord`
- core_loop_step:Chat card -> 用户手动确认 -> 写入/导航 -> 数据回到健康运行时。
- target_surface / safety_level / autonomy_tier:Mobile Chat / medium(write boundary) / manual_confirm only。
- spec_required(§8.1):否,不新增写入能力;收紧既有 UI action 可见性。
- smallest_end_to_end_slice:过滤 unsafe write action,保留 route.open 和显式 manual-confirm 写动作。
- stale_surface_to_remove:缺人工确认但可见的写入按钮。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:Chat + 动态 UI 卡片、manual_confirm 写入边界、快速记录闭环。
- 不做:不新增后端 action,不改 endpoint allowlist,不自动执行写动作。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-chat-card-action-safety-plan.md`
- 任务:
  1. TDD:证明 unsafe write action 会进入 UI。
  2. 实现 UI 层过滤。
  3. 回归 cards_group 子卡 action。
  4. 跑 registry / useChatEngine / chatCardActions 测试。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 过度过滤会让 route.open 导航按钮消失;测试保留 route.open。
  - 过度过滤会让合法 write_intent.confirm 消失;测试保留 manual-confirm 写动作。
  - 只靠服务层拒绝会产生“看得见但点不了”的坏体验;本批在 UI 层前置过滤。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 增加 unsafe write action 过滤失败测试。
- [x] T2 增加 cards_group 子卡 action 回归测试。
- [x] T3 修改 `normalizeCardActions`。
- [x] T4 跑聚焦测试。
- [x] T5 回写 plan / dossier。

## S5 · 实现

- `mobile/components/chat/cards/registry.tsx`:新增 `isSafeVisibleAction`。
- `mobile/components/chat/cards/__tests__/registry.test.tsx`:覆盖 unsafe write action 过滤和 cards_group 子卡 action。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/cards/__tests__/registry.test.tsx --runInBand`
  - 预期失败:缺少 `requires_manual_confirm=true` 的 `agenda.complete` 仍被保留。
- PASS: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/cards/__tests__/registry.test.tsx services/__tests__/chatCardActions.test.ts hooks/__tests__/useChatEngine.test.ts --runInBand`
  - 3 suites passed,35 tests passed。

## G4 · 安全闸

- 触发?:是,Chat 写动作 UI 边界。
- 裁决:GO。UI 层更严格,服务层 `dispatchChatCardAction` 仍保持 fail-loud,未放宽任何 endpoint 或写权限。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS 行为变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:Chat 中多卡运行时/复盘卡按钮可见;unsafe 写按钮不可见。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续 Chat action 成功后局部刷新/跳转的可见反馈和记录页联动。
