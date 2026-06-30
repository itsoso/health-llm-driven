# Today Primary Action Focus Plan

| 字段 | 值 |
|---|---|
| 日期 | 2026-06-30 |
| Dossier | `docs/dossiers/2026-06-30-today-primary-action-focus.md` |
| 目标 | 让 Mobile 首页 DynamicView 回到“一个今日重点行动”,避免 Daily Artifact 下方再展开第二张 7 天运行时计划大卡 |
| 状态 | implemented-local-gate |

## 背景

用户反馈首页凌乱、行动无法确认和执行、内容重复。现有 DynamicView 已能由后端生成 `daily_artifact` 和 `runtime_agenda`,但 Mobile 首页会把两者连续展开,导致第一屏同时出现“今日最重要行动”和“7 天健康运行时计划”,主次不清。

## 范围

- `DynamicTodayRenderer` 在首页渲染 DynamicView 时,若已存在 `daily_artifact`,则不展开 `runtime_agenda` 大卡。
- 保留 `daily_artifact` 的完成、跳过、问阿衡、查看依据和去执行动作。
- 保留 runtime agenda 的数据合同和卡片注册,后续可在阿衡对话或详情页展示。

## 非目标

- 不改后端 DynamicView 合同。
- 不删除 `runtime_agenda` 卡片。
- 不改 Daily Artifact 完成/跳过写路径。
- 不改 App Store final-submit 人审阻塞项。

## 验收

- 首页 DynamicView 只展示一个主 Daily Artifact。
- 同一视图中不再出现 `7天验证节奏` / `未来节奏` 运行时计划大卡。
- 未知卡片仍安全忽略,不导致首页空白。
- 首页回归测试和 Daily Artifact 卡片测试通过。

## 测试

- `cd mobile && ./node_modules/.bin/jest --runTestsByPath components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand`
- `cd mobile && ./node_modules/.bin/jest --runTestsByPath 'app/(tabs)/__tests__/home.test.tsx' components/home/__tests__/DailyArtifactCard.test.tsx components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand`
