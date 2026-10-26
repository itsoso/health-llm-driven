# 病症痊愈确认上下文续接

| 字段 | 值 |
|---|---|
| slug | illness-recovery-continuation |
| 状态 | parked |
| 当前阶段 | 本地实现验证与独立安全评审；发布等待主干整合 |
| 反馈环 | backend |

## G1 准入

PASS。修复截图中的已有病症状态更新流程：先前要求确认两条记录和痊愈日期，用户回复“都好了”后不应当作无授权个人记录查询。新增有界人工确认续接，规格见 `docs/specs/illness-recovery-continuation.md`。Router quick_fix + safety overlay，未使用 superpowers。

## 根因与修复

独立回合本人病症恢复路径已有唯一目标保护；跨回合工具列表快照不能跨回合继承，actionable references 亦没有病症恢复状态。“都好了”本身缺少病症名、日期和读取授权，因而落入拒绝路径。放宽全局授权或让模型推断全部本人病症都好了会扩大写范围。

新增确定性续接：有限旧候选仅作查找线索，按当前认证账号、名称、起病日期唯一重新核验；签名绑定来源、会话、时区和完整行版本。先问缺失日期，再显示确切目标和日期，人工确认后同事务更新与保存回执。保留运行控制闸；禁止自动确认、过期、跨账号和失效版本写入；执行重试核验已落库行和回执。仅记录自述恢复，不增加医疗判断。

## 验证证据

- 初始 RED：新流程缺失，定向20 failed，`/tmp/reva-illness-confirm-red.log`。
- 流入口测试曾检出默认时区字符串不一致；改为复用 profile 的 canonical timezone resolver，修复后通过。
- 补充 RED：确认后取消丢失已执行回执，1 failed / 30 passed / 1 skipped，`/tmp/reva-illness-confirm-boundary-red.log`；将病症 kind 纳入现有取消 CAS 的已执行回执路径。
- 七文件回归：454 passed / 4 skipped / exit 0，`/tmp/reva-illness-confirm-regression.log`。
- 独立临时 PostgreSQL：32 passed / exit 0，`/tmp/reva-illness-confirm-pg.log`；实例已正常停止，`/tmp/reva-illness-confirm-pg-result.json`。并发确认用两个独立连接与 Barrier 同步。
- 定向模块覆盖率87%，31 passed / 1 skipped，`/tmp/reva-illness-confirm-coverage.log` 和 `/tmp/reva-illness-confirm-coverage.json`；SQLite 跳过仅用于 PostgreSQL 的行锁测试。
- 覆盖真实 AgentExecutor 三回合、人工确认要求、完整事务回滚、运行暂停、API IDOR/409、最终回执和已执行取消返回回执。
- System Map：新服务计数生成物已同步；完整检查 PASS，`/tmp/reva-illness-confirm-system-map.log`。
- G4 独立安全评审：待本地固定提交后执行。
- 合成数据、固定时钟；真实 AgentExecutor 使用禁止调用 provider 的断言。未执行真实模型、模拟器或线上健康写入，不宣称线上通过。

## 发布边界

本地 main 与 origin/main 已分叉，且共享工作树存在其他任务改动。遵循 AGENTS.md §7，停止 push/merge/deploy 等外部写入，保留其他提交及 dirty files。既有睡眠语序修复也仍未发布。当前缺少本候选精确远端 CI、CI-mode 和生产验收，不能用旧主干绿色证明本候选可发布；不创建备份或恢复副本。
