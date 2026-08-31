# Feature Spec: Mobile 回答依据说明组件

> Status: approved
> Owner: Codex
> Updated: 2026-08-31
> Related PRD/PDD: `docs/prd/reva-personal-health-os-prd.md` §3 原则⑫、§4 HealthProblem / HealthTwin evidence
> Related code: `mobile/components/chat/ChatBubble.tsx`, `mobile/components/chat/AttributionChips.tsx`, `mobile/utils/chatTransparency.ts`

## 1. Decision

把完成态的“依据与过程”升级为可核对的回答审计卡：首层展示本轮真实观察值、用途与数据限制，来源和技术执行记录按需展开。

## 2. Problem

第一阶段已经把工程遥测收进二级详情，但首层仍只拿到来源字符串和通用进度步骤，只能生成“参考了 N 项信息 / 查询健康数据 / 检查健康数据 / 整理回答”。这些内容描述系统做过什么，却没有说明查到了什么、数据新不新、哪些数据不足。更严重的是，普通路径的旧 `sources_used` 会枚举用户已填充的数据表，不能证明本轮实际使用，容易把“可用上下文”误呈现成“本轮依据”。

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: 优化回答依据与过程的 UI 和内容
  classification: product_change
  first_user_fit: 需要快速理解健康建议依据的 Mobile 用户
  core_loop_step: personal data -> HealthTwin/SafetyGuardian context -> answer -> evidence review -> safer action
  first_class_objects: [HealthTwin, SafetyGuardian]
  target_surface: Backend + Mobile
  source_of_truth: current-turn tool results and selected Health Evidence packet
  safety_level: medical_boundary
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: every primary evidence row must derive from an executed tool result or selected Health Evidence item
  claim_hedging: n/a
  verification_window: same-turn Jest, TypeScript and iOS Simulator review
  success_metric: the first expanded section contains concrete observations and limitations; no generic process step appears in the primary layer; raw diagnostics require a second explicit expansion
  added_user_burden: zero
  burden_justification: n/a
  non_goals: no answer text, model routing, query semantics, write path, share, auth or medical-claim change
  smallest_end_to_end_slice: executed evidence -> deterministic answer_evidence.v1 -> persisted/done contract -> Mobile audit card
  stale_surface_to_remove_or_archive: populated-but-unused source chips and generic completed process steps in the primary layer
  spec_required: yes
```

## 4. Product Direction

- Tone: refined clinical notebook — calm, legible and evidence-led, without dashboard chrome.
- Memorable interaction: the expanded view answers three human questions first: “看到了什么？”、“这项数据用来判断什么？”、“哪些数据不足，系统怎么处理？”.
- Collapsed state remains one compact rail so the reply stays dominant.
- Color communicates meaning: green means completed, amber means unavailable/partial; medication or risk source colors remain unchanged.

## 5. Non-Goals

- 不修改回答正文、医疗引用卡或医学结论。
- 不生成、保存或展示 chain-of-thought。
- 不改变模型选择、工具执行、费用计算或埋点。
- 不修改 Mac/Web/Watch；本轮新增 Backend→Mobile 的只读 `answer_evidence.v1` 契约。
- 不在本任务内发布 OTA。

## 6. Product Object Mapping

| Object | Change |
|---|---|
| `HealthTwin` | 更清楚地展示本次回答使用的数据来源与缺失状态，不改变 Twin 内容。 |
| `SafetyGuardian` | 保留安全/失败来源的可见性，缺失或不可用步骤不能显示为绿色成功。 |

## 7. User Flow

```text
Agent 本轮真实工具结果 / Health Evidence packet
  -> 后端确定性编译 answer_evidence.v1（零额外 LLM）
  -> 完成事件 + message.meta 持久化
  -> Mobile 校验并归一化契约
  -> AnswerEvidencePanel 默认显示“回答依据 · N项”
  -> 用户展开
      -> 本次判断摘要
      -> 关键依据（观察值 / 用途 / 来源 / 新鲜度）
      -> 数据限制（缺失 / 失败 / 冲突 / 保守处理）
      -> 来源（仅本轮实际使用）
      -> 技术详情（二次按需展开）
  -> 用户收起，继续阅读主回答或分享
```

## 8. Surface And Data Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Backend | 从本轮真实结果编译、持久化并下发审计投影 | `answer_evidence.v1`；不得消费任意模型散文 |
| Mobile | 校验后渐进披露依据、限制、来源和技术遥测 | 新客户端优先 `answerEvidence`；旧消息安全回退 |

```yaml
apis: conversation history meta adds answer_evidence
events: done adds answer_evidence
models: unchanged
fields: answer_evidence.v1 (additive)
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
- 数值只允许来自结构化工具结果或本轮已选 PersonalEvidenceItem 的标量字段；对象、数组和任意模型散文不进入审计卡。
- 普通路径不得通过 SQL 枚举所有已填充表生成“参考数据”；`available context` 与 `used evidence` 必须分离。
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

Given 用户有补剂库、目标或化验数据，但本轮未查询也未选入 Health Evidence
When 回答完成
Then 这些可用数据不得出现在“本轮依据”中

Given 本轮批量查询得到 HRV 58ms 和睡眠趋势 -5
When 用户展开回答依据
Then 显示具体观察值、窗口/用途和真实来源，不显示“查询/检查/整理”三条通用步骤

Given 本轮查询结果缺失、过期、冲突或失败
When 用户展开回答依据
Then 单独显示数据限制和保守处理，且不得把缺失推断为正常

Given 历史消息重新加载或健康证据失效
When 客户端恢复消息
Then 只恢复当前策略允许的 answer_evidence；失效数据不得从旧 meta 重新出现
```

## 11. Implementation Plan

1. 先用后端单测锁定“只收本轮结果、标量白名单、缺失/冲突限制、无额外 LLM”。
2. 新增 `answer_evidence.v1` 确定性编译器，复用既有 GenUI 结构化结果与 Health Evidence packet。
3. 将契约加入 done 与 message.meta，并在受控历史投影中保留或清理。
4. Mobile 新增严格归一化类型；完成事件与历史恢复保持一致。
5. `AnswerEvidencePanel` 首层改为关键依据与数据限制；旧 `thinkingSteps` 仅进入技术详情。
6. 运行后端/Mobile 定向测试、TypeScript、治理闸与三档模拟器验收。

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
| 2026-08-31 | Correct scope to a truthful cross-end answer evidence contract | 用户反馈首层仍是通用流水线，且源码证明旧来源不等于本轮实际使用 |
