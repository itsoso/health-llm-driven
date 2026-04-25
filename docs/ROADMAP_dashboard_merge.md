# Dashboard 4 页合并 — 待决策

## 现状

| 页面 | 行数 | 主要职责 | 引用方 | 数据源 |
|---|---|---|---|---|
| `/dashboard` | 876 | 综合面板 (健康指标 + Garmin + 趋势) | 主页 + 404 | `dailyHealthApi` / `garminAnalysisApi` / `basicHealthApi` / `healthTrendApi` / `healthScoreApi` |
| `/overview` | 280 | "健康概览" (周度聚合) | Nav 菜单 + AI 助理 | `api.get` (raw) |
| `/daily-insights` | 408 | "今日建议" (AI 生成的个性化建议) | 主页 + Nav + AI 助理 | `dailyRecommendationApi` + `externalRecommendationApi` |
| `/ai-insights` | 534 | "AI 洞察" (Markdown 形式深度分析) | 仅 Nav 菜单 | (待审计) |

**总计 2098 行**, 4 套独立的 React Query keys, 4 套不一致的视觉风格.

## 用户反馈

> "用户根本不知道该去哪个"

确实: `/dashboard` 和 `/overview` 名称重叠, `/daily-insights` 和 `/ai-insights` 名称重叠.

## 推荐方案 (需产品 owner 确认)

### Option A · 一个 page + 4 个 tab (推荐)
```
/dashboard
  ├─ tab: 概览       ← 接 /overview 的内容
  ├─ tab: 数据      ← /dashboard 当前的图表
  ├─ tab: 今日建议   ← /daily-insights
  └─ tab: AI 洞察    ← /ai-insights
```
- 旧路由保留, 用 `redirect` 跳到 `/dashboard?tab=...`
- React Query cache 共享 (跨 tab 不会重复请求)
- 一份导航菜单, 一致视觉

工时: 4-6h. 风险: 中 (用户路径变化).

### Option B · 删两个不主用的, 留两个独立 page
- 删 `/overview` (功能与 /dashboard 重叠 70%)
- 删 `/ai-insights` (功能与 /daily-insights 重叠, /ai-insights 实际访问量未知)
- 留 `/dashboard` (主面板) + `/daily-insights` (建议)

工时: 2h. 风险: 低. 但仍有 2 个 page, 没解决"用户去哪个"的问题.

### Option C · 不动, 加副标题区分
在 4 个页面顶部加 hero 文案明确职责差异. 不删不合并.

工时: 30min. 风险: 0. 仅缓解, 不解决.

## 决策待办

- [ ] 看 7 天访问量统计 (后端 access log), 看 4 个 page 各自 PV
  - 若某个 page < 5% PV, 可直接删
- [ ] 用户调研 / 自用判断: 4 个名字哪个最该是"主"
- [ ] 视觉规范统一 (即使分开, 也应该统一 hero/margin/typography)

## 此次未做

合并是 UX 决策, 需要 PV 数据 + 产品判断. 此次留作 TODO,
直接进入下一项 (慢查询优化 + N+1 修复).

如果产品 owner 选 Option A, 已知子任务清单:
1. 在 `/dashboard/page.tsx` 加 `<Tabs>` (Tailwind/headlessui)
2. 把 3 个旧 page 的内容抽成 `_overview.tsx` `_ai_insights.tsx` `_daily_insights.tsx` 子组件
3. 旧路由改 redirect
4. Nav 菜单合并为一个 "健康面板" 入口
5. e2e 测一遍
