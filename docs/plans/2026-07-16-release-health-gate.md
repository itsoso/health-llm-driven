# 小巴发布健康门实施计划

> 日期：2026-07-16
> 对应 PRD：`docs/prd/2026-07-16-release-health-gate.md`
> 状态：实施中

## 1. 范围

在现有 `client_events_stats` 中新增发布健康判定，并由 Admin 观察看板透出。只做服务端聚合和测试，不修改 Mobile 更新行为，不触发自动回滚。

## 2. 实施任务

### Task 1：规格与 Dossier

- [x] 写 PRD、Plan、Dossier；
- [x] 固化阈值、分母、样本不足语义和非目标。

### Task 2：发布健康纯函数

- 文件：`backend/app/services/observability_service.py`；
- 新增常量和 `app_update_release_health(...)`；
- 输入只接收已经聚合的计数，避免把判定逻辑散落在 SQL/路由；
- 输出固定结构，原因可读、无健康正文。
- [x] 完成并覆盖样本不足、健康、暂停和空终态分母。

### Task 3：接入既有看板

- 在 `client_events_stats` 的 `app_update` 中加入 `release_health`；
- 保留现有字段和 API 路径；
- `user_id` 过滤沿用当前 ClientEvent 查询。
- [x] Admin 观察看板沿用既有 `/api/v1/admin/observability/dashboard` 自动透出。

### Task 4：测试

- 先补纯函数边界测试；
- 补 `client_events_stats` 空窗口、健康、暂停三类聚合测试；
- 执行后端相关测试和漂移检查。
- [x] 相关测试 `81 passed`；Ruff、编译、doc drift、Dossier consistency、diff check 通过。

### Task 5：部署与上线验证

- [x] 提交只包含本切片文件，保留并发未跟踪文件；
- [x] 按项目 `deploy.sh -b -y` 部署后端；
- [x] 验证迁移无新增、`/api/v1/health` healthy、Admin 观察看板可返回新字段；
- [x] 回写 Dossier Gate 状态。

部署证据：生产健康度 `60/60 PASS`；skills manifest `22 = 22`；生产 `client_events_stats` 返回
`release_health.status=observe`、`launches=3`、`emergency_launches=0`、`terminal_failures=0`。

## 3. Gate

- G1：产品治理准入，已通过；
- G2：只读聚合、无自动外部副作用，已通过；
- G3：单测和静态检查通过后通过；
- G4：管理员权限沿用既有看板，数据内容白名单，无健康正文；
- G5：生产健康检查通过后通过；
- G6：以生产看板 JSON 结构和空窗口返回为上线验证证据。
