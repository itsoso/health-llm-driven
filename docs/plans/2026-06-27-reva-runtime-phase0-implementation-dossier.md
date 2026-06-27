# Reva 滚动 7 天健康运行时编排 Phase 0 实施 Dossier

> 状态:2026-06-27 Codex 隔离分支实现记录。对应规划: `docs/plans/2026-06-27-reva-mobile-watch-healthkit-experience-plan.md` 的 Phase 0A/0B/0C。

## 1. 本轮目标

本轮不做全量视觉重构,先把 Reva 的一级能力「滚动 7 天健康运行时编排」落到 Mobile 第一屏的最小闭环:

1. iPhone 授权后 App 启动/回前台自动同步 HealthKit 近 2 天数据,不再依赖用户手动点同步。
2. 首页出现 `DailyArtifact` 复合工件:今日状态、唯一最重要行动、数据新鲜度、安全边界、最多 3 个证据。
3. 全局预加载 Reva 字体,数字 token 使用 `IBMPlexMono`,ReadinessRing 使用 Reva motion 进行 420ms sweep 动效。

## 2. 产品判断

- `DailyArtifact` 是每日健康运行时的 UI 单元,不是普通 dashboard 卡片。
- 第一屏只突出一个 top action,避免把健康运行时降级成「功能列表」。
- HealthKit 自动同步先采用前台 best-effort,不承诺实时后台投递;后台投递仍留在 EAS/native entitlement 阶段。
- 跳过、完成、问 Reva 的交互先接现有 Today 行动路径;skip reason 的完整埋点留到 Phase 1。

## 3. 工程落点

- `mobile/services/appleHealthAutoSync.ts`:授权、冷却、并发去重、失败不抛出的前台同步服务。
- `mobile/services/healthKitForegroundRefresh.ts`:同步成功后刷新首页运行时 query。
- `mobile/services/dailyArtifact.ts`:把 timeline now item、daily plan fallback、Twin readiness、HealthKit freshness、safety alerts 组装为稳定 presenter。
- `mobile/components/home/DailyArtifactCard.tsx`:首页复合工件卡片。
- `mobile/app/_layout.tsx`:登录后 iOS active lifecycle 触发 HealthKit 前台同步;RootLayout 预加载 Reva 字体。
- `mobile/app/(tabs)/index.tsx`:把 `DailyArtifactCard` 接入首页,暂时保留旧 Hero 作为合并友好的过渡。
- `mobile/components/reva/RevaKit.tsx`:`ReadinessRing` 消费 `revaMotion`。
- `mobile/constants/theme.ts`:legacy 数字 typography 指向 `IBMPlexMono`。

## 4. 安全和隐私边界

- 自动同步只在 iOS、登录后、App active 时触发。
- 未授权 HealthKit 时静默跳过,不弹错误、不打后端。
- 同步服务使用 3 小时冷却和 in-flight 去重,后端仍依赖既有幂等 import。
- 本轮不新增医疗判断、不新增处方/剂量写入、不新增主动推送。
- 服务端分类型 consent 和后台 HealthKit entitlement 仍是后续阶段硬门,不能把本轮前台同步宣传成「实时后台自动同步」。

## 5. 验收口径

- 授权后回前台会触发近 2 天 HealthKit 同步;冷却内不重复导入。
- 同步成功后刷新 `healthkit:lastSync`、dashboard、Twin、timeline、agenda。
- 首页展示一个 `DailyArtifact`:状态、唯一 top action、新鲜度、安全边界、证据。
- 小屏布局仍保持一个主行动,旧 Hero 重复显示同一行动只作为过渡期兼容。
- Reva 数字字体和 readiness ring 动效为全局视觉基线。

## 6. 本轮未做

- Watch 语音和 Action Button。
- Chat 动态 UI 卡片 action 契约。
- HealthKit native 后台投递和 entitlement。
- 服务端 consent enforcement / ProvenanceRecord 补门。
- skip reason 完整埋点和抗习惯化指标聚合。
