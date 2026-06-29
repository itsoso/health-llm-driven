# Dossier: Chat / 首页阿衡人格文案收敛

| 字段 | 值 |
|---|---|
| slug | `chat-aheng-persona-label` |
| 创建日期 | 2026-06-29 |
| 当前阶段 | S8 沉淀 |
| 状态 | shipped-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile jest |

## S0 · 用户需求(逐字)

> 继续执行

本切片承接本周计划 P0/P1:发布一致性与核心动线统一。用户已经确定 App / 主名 / AI 人格三位一体为 `阿衡`,因此 Mobile 的首页和 Chat 主路径不应继续显示旧称“健康 Agent”。

## S1 · Discovery(现状勘察)

- 已有可复用:
  - `mobile/components/chat/LlmModelPicker.tsx`:Chat 头部和模型切换入口。
  - `mobile/app/(tabs)/chat.tsx`:Chat 空态、starter chips、对话节选分享。
  - `mobile/components/chat/ChatBubble.tsx`:单条 assistant 回复分享。
  - `mobile/utils/aiShareText.ts` / `mobile/utils/chatShareSelection.ts`:分享正文格式化。
  - `mobile/components/chat/cards/MenuShareCard.tsx`:饮食菜单动态卡片分享。
  - `mobile/components/home/HomeCommandCard.tsx`:首页主卡顶部人格。
- 缺口:
  - Chat 主路径仍有“健康 Agent”残留。
  - 分享出去的文本尾注仍用旧称,即使 App 内入口已改为阿衡。
  - 首页主卡仍用旧称和旧无障碍标签。
- 硬边界:
  - 不做工程符号、route、target、bundle id 大重命名。
  - 不改健康建议、安全判断或写入逻辑。

## G1 · 准入裁决(governance §8 RequirementAdmission)

- first_class_objects:`AssistantPersona`, `DailyArtifact`, `Conversation`, `ProvenanceRecord`
- core_loop_step:首页今日行动 -> Chat 追问/分享 -> 用户执行或记录 -> 回到健康运行时。
- target_surface / safety_level / autonomy_tier:Mobile Home + Chat / low(copy consistency) / read-only UI。
- spec_required(§8.1):否,不新增用户行为或写路径;收敛既有用户可见命名。
- smallest_end_to_end_slice:Chat/Home 旧称可见面全部改为 `阿衡` 并加回归测试。
- stale_surface_to_remove:用户可见“健康 Agent”残留。
- 裁决:PASS。

## S2 · PRD

- 链接:`docs/prd/2026-06-27-code-verified-asis-prd-and-10m-roadmap.md`
- 引用能力:统一产品人格、Chat + 动态 UI 卡片融合、Daily Artifact 主线。
- 不做:不改安全边界、不改模型选择逻辑、不改任何后端接口。

## S3 · 规划

- 链接:`docs/plans/2026-06-29-chat-aheng-persona-label-plan.md`
- 任务:
  1. TDD:把 Chat、分享、首页测试期望改为 `阿衡` 并确认 RED。
  2. 实现文案和分享尾注替换。
  3. 对菜单分享卡导出纯文本 helper,让分享尾注可测。
  4. 跑聚焦测试、TypeScript、dossier/doc drift。

## G2 · 可行性 + 安全压测

- 评审方式:Codex challenge。
- 风险:
  - 大范围技术符号重命名会破坏构建;本批只改用户可见 UI/分享文本。
  - “阿衡”不能替代医学安全边界;本批不改变建议能力或自动执行能力。
  - 分享文本变更要覆盖工具层,否则 App 内外命名不一致。
- 裁决:PASS。

## S4 · 研发任务分解

- [x] T1 更新 Chat / 分享 / 首页测试期望并确认 RED。
- [x] T2 修改 Chat 主页面、模型选择器、分享标题。
- [x] T3 修改分享文本 helper 和菜单分享卡。
- [x] T4 修改首页主卡和 tab 无障碍标签。
- [x] T5 回写 plan / dossier / weekly plan。

## S5 · 实现

- `mobile/components/chat/LlmModelPicker.tsx`:可见人格改为 `阿衡`。
- `mobile/app/(tabs)/chat.tsx`:空态、starter a11y、对话节选分享标题改为 `阿衡`。
- `mobile/components/chat/ChatBubble.tsx`:assistant 回复分享标题改为 `阿衡 · 建议`。
- `mobile/utils/aiShareText.ts` / `mobile/utils/chatShareSelection.ts`:分享正文尾注改为 `阿衡`。
- `mobile/components/chat/cards/MenuShareCard.tsx`:菜单分享尾注改为 `阿衡`,并导出 `buildShareText`。
- `mobile/components/home/HomeCommandCard.tsx`:首页主卡人格和 a11y 改为 `阿衡`。
- `mobile/app/(tabs)/_layout.tsx`:Chat tab a11y 当批改为 `私教,与阿衡对话`;后续 Mobile tab rename 切片继续收敛为 `阿衡,与健康参谋对话`。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/chat.test.tsx' components/chat/__tests__/LlmModelPicker.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx components/chat/cards/__tests__/MenuShareCard.test.tsx utils/__tests__/aiShareText.test.ts utils/__tests__/chatShareSelection.test.ts components/home/__tests__/HomeCommandCard.test.tsx --runInBand`
  - 预期失败:旧称仍显示、分享尾注仍为旧称、`buildShareText` 未导出。
- PASS:同一命令。
  - 7 suites passed,36 tests passed。

## G4 · 安全闸

- 触发?:否。仅用户可见命名与分享文本收敛,不涉及写路径、用药、诊断、基因、化验、CGM、认证或新安全行为。
- 裁决:GO。

## S6 · 部署

- 本批未部署。属于 Mobile JS/TS/UI 文案变更,后续可随二维码包或 OTA 一起发布。

## G5 · 部署健康闸

- 本地测试闸通过。无线上部署。

## S7 · 上线验证

- 待后续真机/模拟器走查:首页主卡、Chat header、Chat 空态、分享面板文案均显示 `阿衡`。

## G6 · 验证闸(人在环)

- 无新增人审阻塞。

## S8 · 沉淀

- 状态 -> **shipped-local-gate**。
- 后续:继续处理 Rokid 专页旧称、Daily Artifact 视觉走查、Chat action 成功后的局部刷新/跳转反馈。
