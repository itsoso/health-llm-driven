# Feature Spec: Mobile 回答依据说明组件

> Status: approved
> Owner: Codex
> Updated: 2026-08-31
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` §3 原则⑫、§4 HealthProblem / HealthTwin evidence
> Related code: `mobile/components/chat/ChatBubble.tsx`, `mobile/components/chat/AttributionChips.tsx`, `mobile/utils/chatTransparency.ts`

## 1. Decision

把完成态的“依据与过程”从扁平调试面板改为“回答依据优先、处理摘要其次、技术详情按需”的渐进式说明组件。

## 2. Problem

当前展开面把来源标签、进行时状态、成本、耗时、轮次、模型、Token、工具名和 run trace 放在相近的视觉层级。用户需要自行解释工程指标，且“思考过程”容易被误解为内部推理；完成态仍出现“正在……”也造成时态冲突。如果保持现状，医疗来源虽然存在，却不够突出，透明化反而增加认知负担。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 优化回答依据与过程的 UI 和内容
  classification: product_change
  first_user_fit: 需要快速理解健康建议依据的 Mobile 用户
  core_loop_step: personal data -> HealthTwin/SafetyGuardian context -> answer -> evidence review -> safer action
  first_class_objects: [HealthTwin, SafetyGuardian]
  target_surface: Mobile
  source_of_truth: existing message sourcesUsed/thinkingSteps/llmUsage/perf metadata
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: preserve source labels, medical citations, tool failure and telemetry semantics
  claim_hedging: n/a
  verification_window: same-turn Jest, TypeScript and iOS Simulator review
  success_metric: source evidence is the first expanded section; completed steps use honest completed/warning states; raw diagnostics require a second explicit expansion
  added_user_burden: zero
  burden_justification: n/a
  non_goals: no answer, routing, query, write, share, auth or backend contract change
  smallest_end_to_end_slice: one compact entry -> evidence summary -> sources/process -> optional technical details
  stale_surface_to_remove_or_archive: raw headline at drawer top, completed-state 思考过程 label, flat debug log hierarchy
  spec_required: yes
```

## 4. Product Direction

- Tone: refined clinical notebook — calm, legible and evidence-led, without dashboard chrome.
- Memorable interaction: the expanded view answers two human questions first: “参考了什么？” and “做了什么？”.
- Collapsed state remains one compact rail so the reply stays dominant.
- Color communicates meaning: green means completed, amber means unavailable/partial; medication or risk source colors remain unchanged.

## 5. Non-Goals

- 不修改回答正文、医疗引用卡或来源字符串。
- 不生成、保存或展示 chain-of-thought。
- 不改变模型选择、工具执行、费用计算或埋点。
- 不修改 Mac/Web/Watch，不新增跨端契约。
- 不在本任务内发布 OTA。

## 6. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | 更清楚地展示本次回答使用的数据来源与缺失状态，不改变 Twin 内容。 |
| `SafetyGuardian` | 保留安全/失败来源的可见性，缺失或不可用步骤不能显示为绿色成功。 |

## 7. User Flow

```text
Agent 完成事件（sourcesUsed / thinkingSteps / llmUsage / perf）
  -> ChatBubble 构建既有 AgentTransparencyProfile
  -> AnswerEvidencePanel 默认显示“回答依据 · N项”
  -> 用户展开
      -> 回答依据摘要
      -> 参考的数据（来源 chip，可进入记忆）
      -> 处理摘要（完成 / 不可用状态）
      -> 技术详情（二次按需展开）
  -> 用户收起，继续阅读主回答或分享
```

## 8. Surface And Data Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | 渐进披露来源、处理摘要和技术遥测 | 只消费既有 UIMessage / AgentTransparencyProfile，不改写数据 |
| Backend | 继续提供既有完成事件元数据 | 无接口变化 |

```yaml
apis: unchanged
events: unchanged
models: unchanged
fields: unchanged
enums: unchanged
backward_compatibility: legacy messages with only one metadata family still render the available sections
migration: none
```

## 9. Safety, Privacy And AI Boundary

- 来源证据和医疗引用继续可见；本组件不替代 `MedicalCitations`。
- 完成态步骤只来自既有安全状态事件；只做中文完成时态归一和重复项去除。
- 包含“失败、不可用、缺失、未同步、跳过”等信号的步骤使用警示样式，禁止渲染为成功勾。
- 技术详情仍可访问，但默认不显示模型、Token、run id 和逐轮耗时。
- 不展示 prompt、推理 token 文本、原始健康载荷、认证信息或错误堆栈。
- 记忆来源继续通过既有受控入口打开；权限与用户隔离不变。

## 10. Acceptance Criteria

```gherkin
Given 一条含三个来源、完成步骤和技术遥测的回复
When 用户展开“回答依据”
Then 首屏先显示来源与处理摘要，且不直接显示模型/成本裸串

Given 完成态步骤包含“正在理解你的问题”和“整理回复中”
When 抽屉展开
Then 显示“理解你的问题”和“整理回答”，不再显示进行时文案或“思考过程”标题

Given 步骤包含“记录信息暂时不可用”
When 抽屉展开
Then 该步骤使用警示状态而不是成功勾，且不计入顶部“已完成”数量

Given 工具状态写成“已取得健康数据”但回答结果可能为空
When 抽屉展开
Then 处理摘要使用中性动作“检查健康数据”，不声称已取得结果

Given 用户需要诊断信息
When 展开“技术详情”
Then 仍可看到耗时、轮次、模型、成本、Token、失败、trace、路由和工具信息

Given 消息含用户记忆来源
When 点击该来源
Then 仍进入现有记忆管理页面

Given 回答含依据、分享、复制和技术详情入口
When VoiceOver 浏览这条回答
Then 正文与每个交互入口都是独立可聚焦节点，不被外层消息容器合并
```

## 11. Implementation Plan

1. 新建不超过 500 行的 `AnswerEvidencePanel.tsx`，从超大 `ChatBubble.tsx` 提取现有 utility panel。
2. 先修改邻近 Jest，锁定新标题、完成时态、警示状态和二级技术详情。
3. 实现纯函数 `buildEvidenceProcessItems`，清洗、去重并标注完成/注意状态。
4. 保留现有分享、复制、来源跳转和技术数据完整性。
5. 运行定向测试、TypeScript、ESLint、diff check，再做模拟器视觉验收。

## 12. Verification Plan

```bash
cd mobile
npx jest components/chat/__tests__/ChatBubbleStreaming.test.tsx \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  components/chat/__tests__/ChatBubbleToolsUsed.test.tsx --runInBand
npx tsc --noEmit
npx eslint components/chat/ChatBubble.tsx components/chat/AnswerEvidencePanel.tsx
cd ..
git diff --check
```

模拟器检查：折叠态不抢正文；展开态在一屏内先看到来源与处理摘要；技术详情默认关闭、展开后数据完整；Dynamic Type/中文长标签不截断关键状态。

## 13. Rollout And Rollback

- 纯 JS/TS，若后续获授权可走 production OTA。
- 回滚只需恢复 `ChatBubble` 内旧 utility panel；无数据迁移。
- 发布与上线验证不包含在本次确认中。

## 14. Open Questions

无阻断问题。Mac 的同类透视面板保持现状，另行评估跨端统一。

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-30 | Initial approved Quick Flow spec | 用户确认“用户依据优先、技术信息二级折叠”方向 |
| 2026-08-31 | Add honest warning counts, neutral data-access wording and native accessibility grouping | TDD、独立复审与模拟器 AX 验收发现 |
