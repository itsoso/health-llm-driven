# 病症痊愈确认上下文续接

| 字段 | 值 |
|---|---|
| slug | illness-recovery-continuation |
| 状态 | shipped |
| 当前阶段 | S7 后端已部署，终态回执与公网核验通过 |
| 反馈环 | backend |

## G1 准入

裁决：PASS。修复截图中的已有病症状态更新流程：先前要求确认两条记录和痊愈日期，用户回复“都好了”后不应当作无授权个人记录查询。新增有界人工确认续接，规格见 `docs/specs/illness-recovery-continuation.md`。Router quick_fix + safety overlay，未使用 superpowers。

## 根因与修复

独立回合本人病症恢复路径已有唯一目标保护；跨回合工具列表快照不能跨回合继承，actionable references 亦没有病症恢复状态。“都好了”本身缺少病症名、日期和读取授权，因而落入拒绝路径。放宽全局授权或让模型推断全部本人病症都好了会扩大写范围。

新增确定性续接：有限旧候选仅作查找线索，按当前认证账号、名称、起病日期唯一重新核验；签名绑定来源、会话、时区和完整行版本。先问缺失日期，再显示确切目标和日期，人工确认后同事务更新与保存回执。保留运行控制闸；禁止自动确认、过期、跨账号和失效版本写入；执行重试核验已落库行和回执。仅记录自述恢复，不增加医疗判断。

## 首轮本地验证证据（历史）

- 初始 RED：新流程缺失，定向20 failed，`/tmp/reva-illness-confirm-red.log`。
- 流入口测试曾检出默认时区字符串不一致；改为复用 profile 的 canonical timezone resolver，修复后通过。
- 补充 RED：确认后取消丢失已执行回执，1 failed / 30 passed / 1 skipped，`/tmp/reva-illness-confirm-boundary-red.log`；将病症 kind 纳入现有取消 CAS 的已执行回执路径。
- 最终七文件回归：455 passed / 4 skipped / exit 0，`/tmp/reva-illness-confirm-regression-final.log`。
- 最终独立临时 PostgreSQL：33 passed / exit 0，`/tmp/reva-illness-confirm-pg-final.log`；实例已正常停止，`/tmp/reva-illness-confirm-pg-result.json`。并发确认用两个独立连接与 Barrier 同步。
- 定向模块覆盖率87%，31 passed / 1 skipped，`/tmp/reva-illness-confirm-coverage.log` 和 `/tmp/reva-illness-confirm-coverage.json`；SQLite 跳过仅用于 PostgreSQL 的行锁测试。
- 覆盖真实 AgentExecutor 三回合、人工确认要求、完整事务回滚、运行暂停、API IDOR/409、最终回执和已执行取消返回回执。
- System Map：新服务计数生成物已同步；完整检查 PASS，`/tmp/reva-illness-confirm-system-map.log`。
- CI shard 与 Dossier 回归：41 passed / exit 0，`/tmp/reva-illness-confirm-governance.log`；Dossier consistency 全量检查通过。
- G4 独立安全评审：固定提交 `87ee1a912c5c52066b5e8d887143f1031d341015` 获独立 code safety GO。Reviewer 独立跑31 passed / 1 PG-only skipped，再加6项对抗检查（跨会话、日期来源篡改、选择来源篡改、时区改变、取消、执行后版本改变）全部通过；`/tmp/reva-independent-recovery-safety.log`、`/tmp/reva-independent-recovery-adversarial.log`。PostgreSQL 为 producer 执行、reviewer 读证，不冒充独立重跑。
- 后续收窄：无关对话/无上下文的“都好了”应回原流程；新增测试先2 failed后通过，`/tmp/reva-illness-confirm-unrelated-red.log`。最终代码 `1ca9984d742ec04fed916b0cd51044d8914b34ba` 获同一独立 reviewer 再审 GO；独立定向32 passed / 1 PG-only skipped / exit 0，`/tmp/reva-independent-recovery-safety-final.log`。收窄不改变原有身份、签名、日期、预览、事务和运行控制校验；截图的既有确认文本仍满足入口条件。
- 合成数据、固定时钟；真实 AgentExecutor 使用禁止调用 provider 的断言。未执行真实模型、模拟器或线上健康写入，不宣称线上通过。

## 首轮修复阶段的发布边界（历史，已由下方发布证据解除）

本地 main 与 origin/main 已分叉，且共享工作树存在其他任务改动。遵循 AGENTS.md §7，停止 push/merge/deploy 等外部写入，保留其他提交及 dirty files。既有睡眠语序修复也仍未发布。当前缺少本候选精确远端 CI、CI-mode 和生产验收，不能用旧主干绿色证明本候选可发布；不创建备份或恢复副本。

最新只读核对（2026-10-26）：origin/main 与生产均为 `c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf`，remote CI `40274525250` success；本候选主干仍 ahead 6 / behind 7。该远端版不包含本次续接代码，也不包含睡眠修复。生产 backend、celery-worker、celery-beat active，health HTTP 200；另一个候选的 OTA publish `40281092624` 正在进行。首次服务探针误用了 health-worker/health-beat 名称并报告 inactive，随后按 deploy.sh 核实正确 celery 单元，三项均 active；不将错误单元名解释成服务故障。未干预其他发布。

收尾：最终代码提交 `1ca9984d7`，本任务基线 `25ef987e0`；最终代码核对时 local ahead 7 / behind 7，后续仅补本 Dossier 的评审结果。没有 push/merge/deploy/OTA；发布状态 BLOCK。

## G4 最终候选安全评审

裁决：GO。最终主干候选 `e502d4c483f29d52afca112fa3e925338b4eda12` 在 `512205ab039d6440382f36c8d58cbdb3ae915909` 上仅整合本次睡眠与痊愈续接修复；独立 reviewer 复核最终 diff，66 passed / 1 PostgreSQL-only skipped。生产只读 GitHub App 凭据续期另经独立评审，不扩展 App、仓库或权限。

## G5 后端部署

裁决：PASS。用户明确要求“上线”后，从干净的 main 发布检出整合任务提交，原共享工作树及无关记事本改动保留。精确候选完整 [CI 40294529889](https://github.com/itsoso/health-llm-driven/actions/runs/40294529889) 成功，其中 Linux CI-mode 发布不变量 4710 passed / 47 skipped / 127 subtests passed。本机首轮因临时目录组权限失败；环境专项复测通过，重复全量运行在同路径 Linux 闸通过后取消，未冒充本机全量成功。

- 最终候选独立临时 PostgreSQL：67 passed，实例正常停止。
- 合成数据真实模型回归：invariants 12/12、health_agent_core 50/50、live orchestrator 5/5、trajectory 12/12、goldens 9/9，exit 0；未读取或修改真实健康记录。
- [发布预检 40296636063](https://github.com/itsoso/health-llm-driven/actions/runs/40296636063) 与 [后端部署 40296706489](https://github.com/itsoso/health-llm-driven/actions/runs/40296706489) 均成功。
- 规范 `deploy.sh -b` 完成，持久回执 `SUCCEEDED`；runtime terminal 为 `COMMITTED` / `finalized` / `code-only-no-backup`，业务租约已释放。未创建备份、恢复副本或执行恢复演练。
- 仅后端改动，无 schema 迁移或独立 Mobile OTA 制品；现有客户端无需升级。

## G6 部署后核验

裁决：PASS。2026-10-26 17:11 Asia/Shanghai 独立读回生产 SHA 为 `e502d4c483f29d52afca112fa3e925338b4eda12`，backend / celery-worker / celery-beat 均 active，公网 `/api/v1/health` HTTP 200，未登录 `/api/v1/write-intents` HTTP 401。完整证据见 `docs/reviews/2026-10-26-sleep-recovery-release-receipt.json`。

本结论覆盖后端交付与部署后健康/鉴权验证；没有操作真实用户健康记录，没有执行登录态线上对话或模拟器验收。原截图中的病症不会因部署自动标记痊愈，仍须用户在应用内完成日期及记录确认。
