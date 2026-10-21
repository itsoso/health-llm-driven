# 用药通知查询被授权规则误拦截

| 字段 | 值 |
|---|---|
| 状态 | building |
| 当前阶段 | S6 验证 |

Spec: `docs/specs/active/2026-10-20-medication-reminder-read.md`
Workflow: quick_fix + safety-gate；System Map 按路径查询未索引，已运行全量 check 并阅读实际源码/测试。未使用 superpowers。

## G1 · 准入

- 裁决: PASS
- 修复通知已生成的只读草稿与授权绑定不一致；ExecutionEvent 只读，不新增写入授权。

## 实现与边界

- 整句解析固定客户端语句，日期/时间合法且时区与服务端一致，绑定认证本人。
- 现有 health_query/batch 单日参数与原文本时刻联合限定；执行前校验原快照，禁止身份或文本漂移触发通用重新绑定后读库。
- 查询匹配时段的当前有效计划及真实日志；双 owner join 拒绝损坏外键跨账户。范围外计划/日期/时刻不返回。
- 完成投影核验来源和时刻；计划和服药事实分开，保留“不证明历史通知计划”“无打卡不等于未服用”的边界。不可继承为整日继续查询。
- Mobile 仅补固定语句契约测试，打开通知仍不自动发送或记录服药；无 API/schema 变化。

## 验证

- RED：新增测试 **7 failed / 28 passed**，复现截图的查询拒绝及宽泛分析工具暴露，日志 `/tmp/reva-reminder-scope-red.log`。
- 第一轮实现 **2 failed / 182 passed**：执行入口通用 helper 会在账户/文本变化时重建快照，导致局部身份检查失效；已把提醒只读核验移到该 helper 前，保留原错误日志 `/tmp/reva-reminder-scope-green1.log`。
- 第二轮 **189 passed**，含真实 gateway → scoped adapter → completion → 保存回复。日志 `/tmp/reva-reminder-scope-green2.log`。
- 独立 PostgreSQL UTF8 测试库 **86 passed**（37.99s，退出 0），未处理线程异常按失败；日志 `/tmp/reva-reminder-scope-postgres.log`。测试库已正常停止，未触及生产库。
- Mobile 路由/通知历史/详情 **3 suites / 68 passed**；日志 `/tmp/reva-reminder-scope-mobile.log`。固定 prompt 与后端测试一致，无自动发送字段。
- 最终宽回归 **7518 passed / 1 skipped**（476.90s，退出 0），覆盖授权、gateway、写入范围、只读续查、完成投影与用药详情；日志 `/tmp/reva-reminder-scope-regression.log`。该结果是本地相关回归，不替代精确主干完整 CI/CI-mode。
- System Map / mobile-nav / doc-drift 与任务 diff 检查通过；Dossier 一致性检查通过。

## G4 · 独立安全审查

- 裁决: GO
- reviewer `reminder_read_safety_review` 审查固定实现 `8aa8eb8eff9ec12939d5a7827a3b4f0d9d0cc785`，独立复跑新增 **42 passed**，核对 PostgreSQL 86 结果。
- 覆盖精确解析、模型额外参数、账户/时区/时段隔离、冻结快照、双 owner join、只读权限、完成投影与 continuation；未发现阻断项。
- 仅为此修复的源代码裁决，不代替完整 CI、生产或真实模型验收。

## 发布边界

用户已要求修复后部署。此前远端完整 CI 失败，按 AGENTS §7 暂停外部写入；旧维护 UNKNOWN 回执也未完成合法收尾。当前截图不视为允许绕过这些门禁的回复。未推送、未部署；没有读取真实健康记录或调用真实模型。

### 2026-10-20 · 红灯状态下的修复推送授权

用户随后明确授权：“允许在 CI 红灯时推送这批受审修复，继续完整 CI 排障”。授权覆盖本批已审查的修复及 CI 排障推送，不豁免生产发布门禁或旧维护 UNKNOWN 的收尾。按同一候选执行完整 CI，保留已有失败记录；不重复触发已存在的完整运行。

### 完整 CI 排障证据

- 已推送 `85e1985172c36ea9ef50c2157fb92c508101986e`，自动完整 CI `39357366631`；保留该运行的失败状态，没有取消或重复 dispatch。
- `backend-quality` 依赖审计报告 aiohttp 3.14.3 的三条漏洞。升级 3.14.4 并重新生成哈希锁；其必要依赖 yarl 由 1.24.5 升至 1.25.1，强制保留旧 yarl 的解析明确失败，其他包版本未变化。新锁静态 pip-audit 退出 0 / No known vulnerabilities found。Mac 标准 pip-audit 的临时 ensurepip 子进程 SIGABRT，完整安装审计仍由 Linux CI 验证，不将静态扫描冒充安装验证。
- `ota-runner-startup` 返回 `native_source_unavailable`。现有 fetch depth 256 截断固定原生基线历史（候选到基线 320 个提交）；新增 270 个合成提交测试复现浅克隆，改为 canonical origin 精确 SHA 的完整历史 fetch。未改变发布权限、原生兼容规则、失败码接纳或凭据前置门禁。
- `release-invariants` 精确覆盖检查发现 `test_delayed_medication_summary.py` 未进入 d 分组；向 d-rest 添加 delayed 模式，保留覆盖相等与无重复断言。
- RED：依赖版本与真实 Git fetch 测试 2 failed，目录覆盖测试 1 failed；修复后相关发布/依赖/目录检查 **286 passed**，System Map 与 diff check 通过。日志 `/tmp/reva-oct20-ci-repairs-{red,green2}.log`、`/tmp/reva-oct20-ci-catalog-red.log`、`/tmp/reva-oct20-dependency-audit-static.log`。
- 同次 CI 的 Mobile、前端、Mac、文档、类型漂移、PostgreSQL 检查通过；旧 Mobile cleanup 超时本轮未复现，没有放宽测试超时。
- 已读统一发布会话 `01a120c7-1ba0-75c3-9487-447bd5bfa28f` 的用户 heartbeat `01a13e2f-d3c4-72d2-8f3e-5298c9620577`，原文明确“不备份、不真实模型评测、不查真实健康记录”；后续“全部发布”未撤销。按 deploy.md 只允许为本次完整目标 SHA 设置真实评测 waived，不设置 confirmed，也不豁免离线安全或生产门禁。
- 首轮 CI 修复审查 `ci_repairs_safety_review` 对 `89c6253f5` 判 NO-GO：遗漏同步分组 runner 的精确路径断言（83 passed / 1 failed）。已补入 delayed 模式并保留严格断言；分组/发布契约 **41 passed**。审查另独立验证 OTA/release gate **411 passed**，aiohttp/yarl 全部哈希与官方 PyPI 集合一致。NO-GO 原记录保留，修复交给新的 reviewer。
- 新 aiohttp 3.14.4 / yarl 1.25.1 从隔离目录加载，Withings token 持久化适配测试 **19 passed**；没有外部设备或真实凭据请求。日志 `/tmp/reva-oct20-http-adapters-green.log`。旧候选本地 CI-mode 与远端相同，在目录覆盖项失败（602 passed / 1 failed），不作成功证据；修复候选须新跑。
