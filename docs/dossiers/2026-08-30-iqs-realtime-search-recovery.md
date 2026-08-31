# Dossier: IQS 实时搜索恢复与失败语义修复

| 字段 | 值 |
|---|---|
| slug | `iqs-realtime-search-recovery` |
| 创建日期 | 2026-08-30 |
| 当前阶段 | G6 生产回放通过 |
| 状态 | complete |
| 负责 | Codex |
| 反馈环 | production evidence -> TDD RED -> fail-honest repair -> credential recovery -> backend release -> production replay |

## S0 · 用户需求

> 系统的ISQ搜索的能力好像不支持了，你检查一下。因为刚才最后一次Query，我搜索浙一儿童医院，没有执行这个操作，想办法去解决掉。

注：项目能力名为阿里云 `IQS`；用户所说 `ISQ` 按同一能力处理。

## S1 · Discovery

- 生产对话 `1907` 的用户消息 `9555` 实际内容为“浙一的余杭院区能挂儿童急诊吗？”。
- 该轮 Agent Kernel 正确选择并放行了 `realtime_search`，没有发生意图漏路由或能力策略阻断。
- 生产日志在工具执行边界返回 `InvalidAccessKeyId.Inactive`，证明生产 IQS AccessKey 已被禁用。
- `fetch_realtime_evidence` 的既有 fail-soft 契约把未配置、超时、上游异常和真实零命中都压成空串；显式工具调用因此被记录为 `success=true`，最终回答把鉴权失败误述为“实时检索没有查到确切结果”。
- 一组现有授权凭证已通过同一 IQS SDK 和“浙大一院余杭院区 儿童急诊”查询验证，返回 3 条结果；验证过程未输出凭证值。

## G1 · 准入裁决

- Classification：production incident / bugfix。
- Product object：Agent evidence boundary；不新增用户对象、写能力或自治等级。
- Surface：Backend Agent chat。
- Safety：外部搜索仍只作时效性/通用事实候选证据，不覆盖个人数据、专家裁决或医疗安全门。
- Feature spec：不需要；属于既有 IQS 能力的配置恢复和错误语义修复。
- **裁决**：PASS。

## G2 · 可行性与风险压测

- Orchestrator 自动 grounding 保持默认 fail-soft，IQS 故障不能阻断整轮健康回答。
- 用户/模型显式调用 `realtime_search` 时必须区分依赖不可用与真实零命中。
- 依赖故障返回稳定、脱敏的 `Error:` 结果，使 Agent Kernel 记录 `success=false`；不得把 AccessKey、异常全文或用户健康内容写入结构化遥测。
- 真实零命中继续返回诚实的“未返回结果”，不误报基础设施故障。
- 无 DB migration，无 Mobile/Web 变更；Backend-only 发布。
- **裁决**：PASS。

## S4 · 研发任务

- [x] T1 读取最近生产消息、元数据与同时间窗口日志，确认真实工具轨迹。
- [x] T2 RED：未配置和上游异常的严格模式应抛稳定不可用原因。
- [x] T3 RED：显式 `realtime_search` 必须请求严格模式并返回 `Error:`。
- [x] T4 GREEN：新增 opt-in `raise_on_unavailable`，保留默认 fail-soft 兼容。
- [x] T5 GREEN：显式工具调用 fail-honest，零命中保持原契约。
- [x] T6 将项目部署配置切换到已验证有效的授权凭证。
- [x] T7 完整本地验证。
- [x] T8 提交、推送、Backend 部署与生产只读回放。

## G3 · 测试证据

- TDD RED：3 个目标测试按预期失败，原因分别为严格不可用类型缺失和显式工具未请求严格模式。
- Focused GREEN：`test_iqs_search_hardening.py` + `test_realtime_search_tool.py` 共 `19 passed`。
- 相关 Agent 状态/进度回归：4 个测试文件共 `183 passed`。
- 真实模型 Gate：invariants `12/12`、health-agent-core `50/50`、Orchestrator `5/5`（平均分 `0.92`、无 regression）、trajectory `12/12`、goldens `9/9`。
- 本地真实 IQS strict probe：同一目标查询返回 3 条搜索结果。
- Ruff、`compileall`、`git diff --check`、Dossier consistency：PASS。
- GitHub Actions `33298075484`：最终 `success`；IQS、PostgreSQL、LLM 回归、发布约束与全部测试分片通过。
- CI 慢测诊断：`agent-executor-i-z` 首次在 GitHub runner 超过 600 秒；原命令本地精确复现为 `360 passed`（35.29 秒），仅重跑失败分片后通过，未绕过 Gate。
- 生产验证：PASS。

## G4 · 安全边界

- IQS query 出口继续经过手机号、身份证和邮箱脱敏。
- 外部返回继续经过 prompt-injection defang 和字符预算限制。
- 搜索结果仍标为外部候选证据，不替代医生或个体化医疗判断。
- 新错误只暴露 `not_configured / timeout / upstream_error` 稳定原因，不暴露密钥或上游异常详情。
- **裁决**：PASS。显式失败只进入稳定错误码与安全中文提示；默认自动 grounding 兼容行为不变。

## G5 · 部署

- Release target：Backend-only。
- 配置同步和代码部署统一通过根目录 `deploy.sh`。
- 回滚：代码回滚到部署前 revision；环境配置由 deploy transaction 的 env backup 恢复。
- 发布 revision：`751eae98ea1ee6fb4169f04ee083c93a1be9d2bc`。
- 已验证回滚点：`ee1e12f949dafd190bff53b1e81344be670f6341`。
- 数据库备份、237 张表恢复演练、站外加密归档：PASS。
- 部署健康度三次 `60/60`；runtime-only KB guard/staged contract 与 skills manifest `22=22`：PASS。
- 状态：PASS，事务已 finalize，未触发回滚。

## G6 · 生产回放

- 使用原问题“浙一的余杭院区能挂儿童急诊吗？”做生产 IQS 严格模式只读探测。
- 结果：`PRODUCTION_IQS_REPLAY_OK results=3 evidence_block=1`。
- 验收：有效生产凭证返回非空证据块；严格工具失败语义由单元/Agent 回归测试覆盖，不再把依赖故障伪装成零命中。
- 状态：PASS。

## Gate ledger

| Gate | 状态 | 证据 |
|---|---|---|
| G1 | PASS | 既有能力 incident，无产品语义扩张。 |
| G2 | PASS | 自动 grounding fail-soft；显式工具 fail-honest。 |
| G3 | PASS | 183 related tests；真实模型全绿；本地 IQS strict probe 返回 3 条。 |
| G4 | PASS | 既有隐私/注入护栏保留；错误原因稳定且脱敏。 |
| G5 | PASS | `751eae98ea1e` 已发布；健康度 `60/60`；回滚点 `ee1e12f949da`。 |
| G6 | PASS | 原问题生产严格回放返回 3 条实时证据。 |
