# 仪表盘数据缺失与趋势空白修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 统一整合与发布验证 |

## G1 范围准入

裁决：PASS。修复现有用户路径与数据真实性，复用本人认证和既有记录；不增加自主健康写入或新必填流程。


- 日期：2026-10-09
- 状态：本地修复和定向验证通过；尚未发布、尚未完成线上验收。
- Router：quick_fix；按需使用 system-map 查询 dashboard 页面。
- 用户反馈：`/dashboard` 数据不全，趋势丢失。

## 已确认的原因

1. 线上两个 ResponsiveContainer 有非零尺寸，但没有图表内容。Recharts 2 使用旧 react-is，无法识别 Next App Router 的 React 元素。工作树已有 next.config.js 的两种 bundler alias 修复，本任务保留并验证该改动，不宣称它由本任务新增。
2. React 19 JSX 不再应用函数组件 defaultProps。仅修复 react-is 后，曲线和柱子可以出现，但 XAxis/YAxis 的布局参数和轴绑定仍会缺失。使用实际 JSX 渲染完整页面的测试复现了该问题。
3. 今日设备数据和手动记录是互斥分支，连接 Garmin 后饮水、饮食和最近体重被隐藏。
4. 饮水查询使用不存在的 `/water/records/me/daily-summary`。实际后端接口为 `/water/records/me/date/{record_date}`。
5. 饮食日汇总是包含 meals_count、total_calories 的对象，页面错误地按数组读取。
6. 手动刷新只覆盖四个查询；React Query 的 refetch 错误状态也未被检查。趋势报告为空或失败时整个区块被隐藏。

## 修复范围

- 保留已有 react-is 兼容配置；显式展开坐标轴默认参数，并给折线、柱子绑定同一组轴 ID。
- Garmin 和手动记录同时展示；使用真实饮水接口和饮食汇总字段。
- 刷新覆盖所有仪表盘查询，检查失败状态，保留上次成功数据并提示重试；同步失败也有提示。
- 数据状态查询按 userId 隔离；趋势加载、失败、暂无报告各有明确状态；未知方向不显示为稳定。
- 保留设备指标的零值，读取失败不伪装成零条记录。
- 未改变后端接口、数据库、鉴权、健康分析生成或任何健康数据写入。

## 验证证据

- 新增页面用例：修复前 6 个失败；覆盖 Garmin 与手动记录共存、饮水路径和饮食汇总契约、读取失败、空报告、未知趋势、完整刷新和刷新失败保留缓存。
- 图表回归：在 Next bundled React 中将实际 page.tsx 编译为自动 JSX，使用合成查询结果和真实 Recharts；验证两个 bundler 配置下的曲线、柱子、四个坐标轴、日期标签、图例和手动记录。认证与查询使用测试替身，不是线上验收。
- `cd frontend && npm test -- src/app/dashboard/page.test.tsx src/app/dashboard/chartRuntime.test.ts src/app/workout/components/chartRuntime.test.ts`：13/13 通过。
- `cd frontend && npx tsc --noEmit`：通过。
- 定向 `git diff --check`：通过。
- 本地浏览器使用独立 loopback 合成数据服务：睡眠图有曲线与两个坐标轴；步数图有柱子与两个坐标轴；均显示日期标签，手动记录与设备数据同时显示。没有向生产写入测试数据。

## 发布断点

本次未 commit、push 或 deploy。共享工作目录期间被其他任务 stash 并同步主干，本次修改已恢复；其他任务和用户改动保持原样。工作树仍包含其他改动，本任务没有干净目标 revision、精确 SHA CI 或部署回执。按 AGENTS.md §7 及发布规范，不能把本地测试通过称为线上已修复。部署后需重新用登录会话验收真实仪表盘。
