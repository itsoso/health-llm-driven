# 健康提醒历史无法进入确认修复

| 字段 | 值 |
|---|---|
| 创建日期 | 2026-10-17 |
| 当前阶段 | S7 后端发布与回读完成 |
| 状态 | shipped |
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
- 端到端合成测试覆盖历史读取→今日行动 pending→本人明确 POST 完成→状态 completed；打开不生成完成/依从记录，跨用户 404，重复确认只有一条 ExerciseRecord/HealthProtocolEvent。
- PostgreSQL 合成 API 往返 9 passed，包含通知隔离、读取不生成完成/依从记录、明确完成写 ExerciseRecord 与重复确认幂等。首次启动测试集群未带专用端口导致连接拒绝，修正隔离测试集群端口后通过；未接触生产数据库。
- iPhone 17 模拟器启动后停在未登录页面，未录入真实账号或替用户确认行动；模拟器实际点击验收未完成，组件交互与 PostgreSQL 往返分别通过，不将两者冒充模拟器验收。
- System Map 检查通过；实现没有新增生成图结构。独立安全审查及精确 SHA 发布验证已完成，证据见下。
- 未替用户确认截图中的运动或其他健康事项。

## 发布与验收

- 发布 SHA `e35dee8ba27b92b532fd566198db771d31a00856`；业务安全独立审查 **GO**，29 项独立测试通过。四份固定发布脚本经独立 transport **GO**，按原锁和原回执单次执行，no-backup 轮换成功。
- 本机 CI-mode 完整通过：3,953 passed、84 subtests passed、23 环境/平台限定 skips；JUnit 4,060 项、0 failures/errors。干净 checkout 绑定候选 SHA；Dossier 一致性与测试退出码均为 0。本机 macOS 不冒充 Linux 隔离验收，对应云端检查通过。
- [完整 CI 39027718043](https://github.com/itsoso/health-llm-driven/actions/runs/39027718043)：精确 SHA，32 jobs success。确定性导航映射变更无需真实模型发布闸；机器判定 live_llm_required=false，未使用确认变量或豁免。
- 生产匿名 GitHub API 额度不足时未启动发布，等待额度恢复为 60 后重新核验并推进；未绕过校验、注入管理员 Token 或重复领取发布。
- [后端发布 39030417816](https://github.com/itsoso/health-llm-driven/actions/runs/39030417816)：success；服务器 `SUCCEEDED`，runtime `COMMITTED`，生产源码 SHA 一致且干净，业务租约已释放。backend/worker/beat 均 active/running，NRestarts=0。
- 公开健康接口 HTTP 200，API/database/Redis/Celery 健康；已部署源码的 6 项新通知、旧历史、显式链接、别名、未知类型和错误通知类型映射探针通过。探针不写生产健康记录，不能替代登录账号的 UI 验收。
- 模拟器仍因未登录而未完成真实点击验收；组件交互和隔离 PostgreSQL 完整确认链路已分别通过。用户需重新进入推送历史，点击健康提醒进入今日行动，再明确选择完成；未替用户补记运动。
- 打开通知不产生完成/依从记录；既有 `/agenda/today` 在用户已开启 exercise-chain 时可能物化计划，因此不将整个 GET 笼统描述为无任何数据库副作用。
- 仅后端运行代码变化，Mobile 只有测试变化，不发布空 OTA；用户无需安装新 App。已有 OTA `8711e424` 保留。
- 结构化回执：`docs/reviews/2026-10-17-health-reminder-confirm-entry-release-receipt.json`。证据提交不改变已上线代码。
