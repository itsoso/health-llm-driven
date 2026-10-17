# 健康提醒历史无法进入确认修复

| 字段 | 值 |
|---|---|
| 创建日期 | 2026-10-17 |
| 当前阶段 | S5 实现与验证 |
| 状态 | building |
| 范围 | 行为协议通知到既有今日行动确认页的导航恢复 |

## G1 · 修复准入

- **裁决**: PASS。按 `docs/specs/reva-product-governance-spec.md` 恢复现有提醒到行动确认的闭环，不新增对象、API、表结构或自动完成权限。
- Router 为 quick_fix + safety overlay；使用 System Map 零跳查询并回到通知生产者、历史 API、移动端路由和行动完成源码。

## 根因与修复

- 行为协议提醒携带 `AGENDA_ACTION` 和 `complete_ref`，但 `deeplink_for("protocol")` 未映射目标；推送历史 `LogRow` 在没有 deep_link 时 disabled，因此文案要求确认而整行无法点击。
- 新通知映射到已有 `/agenda`；历史 API 对结构化 kind=protocol/category=AGENDA_ACTION 的 reminder 补只读导航投影，使已发旧通知也可打开今日行动。保留现有 deep_link/deeplink，不按标题猜类型，不改写历史记录。
- `/agenda` 明示今日行动并读取认证用户的当前状态；只有选择当前行动的完成按钮才调用原 `/agenda/complete`。历史引用不自动执行、不用旧日期补记今天，不新增推送出口或锁屏载荷。
- Mobile 仅新增既有页面点击测试，运行代码不变；不发布空 OTA。

## 验证进展

- RED：4 failed / 32 passed，复现生产者缺链、旧历史不可导航和既有链接兼容。
- GREEN：后端通知深链、历史、扫描器、餐后步行、协议、议程 77 passed；移动端历史、议程、路由、通知确认动作 57 passed。
- 端到端合成测试覆盖历史读取→今日行动 pending→本人明确 POST 完成→状态 completed；读不写，跨用户 404，重复确认只有一条 ExerciseRecord/HealthProtocolEvent。
- PostgreSQL 合成 API 往返 9 passed，包含通知隔离、读取不写入、明确完成写 ExerciseRecord 与重复确认幂等。首次启动测试集群未带专用端口导致连接拒绝，修正隔离测试集群端口后通过；未接触生产数据库。
- iPhone 17 模拟器启动后停在未登录页面，未录入真实账号或替用户确认行动；模拟器实际点击验收未完成，组件交互与 PostgreSQL 往返分别通过，不将两者冒充模拟器验收。
- System Map 检查通过；实现没有新增生成图结构。独立安全审查及精确 SHA 发布验证待完成。
- 未替用户确认截图中的运动或其他健康事项。
