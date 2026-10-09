# 环境健康页面 404 修复

| 字段 | 值 |
| --- | --- |
| 状态 | building |
| 当前阶段 | S5 统一整合与发布验证 |

## G1 范围准入

裁决：PASS。修复现有用户路径与数据真实性，复用本人认证和既有记录；不增加自主健康写入或新必填流程。


状态：本地实现与验证完成，未提交、未部署。

## 原因

导航菜单已有 `/environment` 环境健康入口，但 Next.js app 目录缺少该页面。2026-10-09 线上 HTTP GET 实测返回 404。

## 修复

新增受 ProtectedRoute 保护的 `/environment` 页面，复用已有认证 `/environment/weather` 与 `/environment/air-quality` API，按当前用户隔离查询缓存。展示天气、温度、湿度、风速、空气质量及数据来源；加载、失败重试、缺失数据各有明确状态。缺失值不展示为 0，默认兜底源不展示为实测环境。

API 新增 additive `display` 字段，复用 `format_card_numbers` 格式化展示数值；原始返回读数、服务缓存和规则建议不改变精度。前端同步消费 display 类型。本次没有更改健康建议规则、认证或数据库行为。

## 验证

- 新增测试先失败：前端缺少 page 入口，后端缺少 display 字段。
- 前端页面行为测试 3 passed，包含真实零值、来源、缺失与单个接口失败后重试。
- 后端 display 与未知城市诚实性检查 11 passed；合成测试数据，未验证数据库语义。
- `npx tsc --noEmit` exit 0。
- 本地 Next.js GET `/environment` 返回 HTTP 200（登录保护页面入口）。未将该结果当作已登录线上数据验收。
- canonical System Map 重新生成；`./scripts/system-map-check.sh` 全部通过；`git diff --check` 通过。

## 发布边界

共享 main 仍含其他任务改动，尚未从干净 revision 执行 CI-mode 集成闸、精确 SHA CI 与部署。线上页面修复未验收。
