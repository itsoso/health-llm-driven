# Dossier: Chat 回复级生成记录刷新闭环

| 字段 | 值 |
|---|---|
| slug | `chat-result-record-refresh` |
| 创建日期 | 2026-07-04 |
| 当前阶段 | S8 沉淀 |
| 状态 | implemented-local-gate |
| 负责 | Codex |
| 反馈环 | TDD / mobile Jest / later OTA |

## S0 · 用户需求

> 按照规划继续执行剩余的部分。

承接本周计划后续顺序中的「Chat card action 成功后的局部刷新/跳转反馈和记录页联动」。代码复核发现卡片级写动作已刷新今日执行面,但回复级「生成记录」成功后只刷新 dashboard/timeline/diet/dynamic-view,没有刷新今日计划和 Daily Artifact。

## G1 · 准入裁决

- first_class_objects:`ExecutionEvent`, `HealthAgendaItem`, `DailyArtifact`, `DietRecord`
- core_loop_step:阿衡回复 -> 生成记录 -> 今日计划/Daily Artifact/记录页同步更新
- target_surface / safety_level / autonomy_tier:Mobile Chat / low UI consistency / manual action
- smallest_end_to_end_slice:回复级生成记录成功后刷新今日执行相关缓存,不自动跳走。
- 裁决:PASS。

## S2/S3 · 计划

1. RED:在 `ChatBubbleStructuredSummary` 加用例,要求生成记录后刷新 `agenda/today` 与 `daily-artifact/me`。
2. GREEN:补齐 `handleCreateRecord` 的 invalidation keys。
3. 回写本周计划状态。

## G2 · 风险压测

- 不新增后端写接口,继续复用 `createRecordFromAssistantReply` 和现有 `quick-record` 合同。
- 不自动跳转,避免用户在阅读回复时被打断;仅在无法自动生成时沿用打开记录页的 fallback。
- 不改变医疗边界、用药、处方或诊断逻辑。
- 裁决:PASS。

## G3 · 测试闸

- RED: `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx --runInBand`
  - 新增用例失败,`agenda/today` 和 `daily-artifact/me` 未被刷新。
- PASS:同一命令。
  - 1 suite passed,16 tests passed。

## G4 · 安全闸

- 只改 React Query 缓存刷新集合和测试。
- 用户数据隔离、认证、写动作 manual-confirm 策略未变化。
- 裁决:GO。

## S8 · 沉淀

- 本周计划新增第十七批实现切片。
- 后续仍保留 Daily Artifact 主屏真机点击动线、App Store production submit 前 final gate、Watch 真机/二维码原生包。
