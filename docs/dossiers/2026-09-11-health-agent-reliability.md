# Dossier: 健康 Agent 可靠性改进

| 字段 | 值 |
|---|---|
| slug | health-agent-reliability |
| 创建日期 | 2026-09-11 |
| 当前阶段 | G3 阻断，候选代码已实现，发布等待真实模型验收 |
| 状态 | parked |
| 负责 | Codex |
| 反馈环 | 合成回放、PostgreSQL、Mobile、真实模型与发布验证 |

- 状态：本地候选实现与定向验证；真实模型门禁 BLOCK，未进入发布。
- 授权：用户先授权“按照计划执行”，随后明确要求提交和部署已修复代码。本轮 commit、必要 push 与部署已获授权，执行仍须通过对应 Gate；未授权修改生产历史健康记录。
- 计划：`docs/plans/2026-09-11-health-agent-reliability-improvement.md`
- 规格：`docs/specs/active/2026-09-11-health-agent-reliability.md`
- 单一运行：`docs/_generated/harness-runs/7c5a6fbb9fd7.jsonl`（本地忽略，不提交）
- 基线：main `f791da13e1816b7ddb2228d0b17af397476ab5c3`。同步前已有改动保留于原 stash/私有备份，当前没有恢复或覆盖。
- 工作流：implementation / Health Harness controller / safety overlay；安全审阅使用固定文件 SHA 快照，AGENTS 的单独提交授权优先。

## 实施范围

| 工作包 | 本地实现 | 状态与保留限制 |
|---|---|---|
| T0 | focused spec、合成反例、同一 Dossier | 本地契约完成；非临床审批 |
| T1 | 完整生成正文检查后释放；普通、跨轮、多模型出口；已知剂量、缺失数据推断、无依据因果阻断；个性化日报缺少受审依据时 hold | 已知反例与工程复审通过；规则未命中不证明医学安全，逐句临床依据与医学审阅仍未完成 |
| T2 | 明确补剂绑定领域、同一实体数量冲突定向澄清，避免营养字段绕道饮食 | 策略及认证 API→PostgreSQL→回执闭环通过；不批量修正历史误写 |
| T3 | 协议污染、逐动作失败/等待/对账、医学 hold 真实终态；Mobile 断连和历史恢复尊重权威状态 | 本地跨层测试通过；模拟器实际 UI 验收未执行 |
| T4 | 饮食/睡眠明确自然日读取，醒来日归属，数据缺失与同步 unknown，卡片/证据统一窗口 | PostgreSQL 验证通过；现有日聚合行不足以重建完整睡眠事件和旅行时区 |
| T5 | 历史受控读取；内部份量修正 v2 签名绑定 owned GET 基线，行锁下 CAS，旧基线 409 | PostgreSQL 并发验证及独立审查通过；公开通用 PUT 未新增 CAS；照片捕获真实并发竞态未新增验证 |
| T6 | 不可恢复同请求去重、停止重复模型回合；拥有者/会话/哈希/有效期绑定的只读编号继续 | 本地真实 stream 持久化回合通过；写选项保持原确认，不自动继承权限 |
| T7 | 快速记录只保留必要的上一问；确定性数据卡片可先显示，模型正文审后释放 | 部分完成；普通非快路径背景注入尚未全面收敛，无同请求性能提升结论 |
| T8 | v2 绘制指标分流；匿名任务快照、已有元数据导出与评测 CLI；owner/turn/run 严格匹配，成本缺失保留 unknown | 本地工具完成；部署 revision/客户端版本绑定、别名映射、自动采集和人工任务质量标注尚缺 |
| T9 | 预算/授权阻断不切换供应方绕行，错误脱敏，日报保留确定性摘要与显式失败/hold 状态 | 定向回归通过；外部供应方真实恢复未验证 |
| T10 | 未执行 | 真实模型、完整 CI、医学审阅、模拟器路径、单独发布授权与上线后观察仍需完成 |

## 新鲜验证

测试分组有重叠，不累加成独立场景总数。使用合成数据与独立本地测试库，不向其他账户重放生产对话。

| 验证 | 结果 | 私有原始日志 |
|---|---|---|
| 完整策略/语义/工具网关定向集 | 5582 passed | `/tmp/reva-final-policy-integration.log` |
| 执行终态、正文、工具回执、GenUI、多模型、编号继续 | 574 passed | `/tmp/reva-final-executor-integration.log` |
| 正文审后释放及边界 | 35 passed | `/tmp/reva-final-stream-contract-green.log` |
| 查询→卡片/证据→编号继续，真实 PostgreSQL | 25 passed | `/tmp/reva-final-read-pg.log` |
| 补剂真实认证 API→PostgreSQL→回读，重复回合与负例 | 3 passed；脚本化模型，不是模型质量分数 | `/tmp/reva-supplement-e2e.log` |
| 内部份量 CAS 与相关路径，真实 PostgreSQL | 41 passed | `/tmp/reva-portion-cas-green-final.log` |
| T5 独立 PostgreSQL 复审 | 13 passed，含并发一次 200/一次 409 | `/tmp/reva-t5-review-20260911/pg-cas.log` |
| Mobile 恢复、历史、状态、实际埋点传输 | 182 passed；TypeScript 通过 | `/tmp/reva-final-mobile-integration.log`、`/tmp/reva-final-mobile-types.log` |
| 安全叙事及后台失败恢复 | 211 passed | `/tmp/reva-safety-review-final.log` |
| orchestrator 预算/授权 fallback 与相邻回归 | 93 passed | `/tmp/reva-orchestrator-policy-final.log` |
| 最后编号多模型旁路修复 | RED 后 41 passed | `/tmp/reva-pending-multi-green.log` |
| 多模型独立审查 | 19 passed；最后日志脱敏单点复验 2 passed | `/tmp/reva-multi-model-independent-review.log`；reviewer 固定快照 |
| 匿名评测导出，真实 PostgreSQL | 53 passed，独立关联复审 2 passed | `/tmp/reva-task-export-pg-final-reviewed.log`、`/tmp/reva-export-review-final-green.log` |
| 新增服务覆盖率 | 95 passed；五个新增服务合计 93.94%，各自均超过 80% | `/tmp/reva-final-new-service-coverage-green.log` |
| 零成本 LLM gate | invariants 12、health_agent_core 50、trajectory 12、goldens 9 全通过 | `/tmp/reva-final-offline-llm-gate.json` |
| 结构生成物及文档漂移 | 重生成后 System Map 检查通过 | `/tmp/reva-final-system-map-check.log` |

真实 PostgreSQL 测试使用独立、名称含 test 的本地数据库。纯策略批量测试采用快速单元环境，不能代替数据库语义验证。当前定向验证不是完整项目 CI-mode 集成闸，也未取得当前候选提交的远端 CI 证明。

## 独立评审与整改

- advice_safety 独立复验主 stream 的普通上下文意外剂量输出、协议终态及编号只读写入拒绝。修复后反例通过；发现编号可走多模型捷径后新增真实 RED，受限只读回合统一保留普通路径。
- time_queries 独立审查多模型 lead/perspective/synthesis 入参、可见正文和预算/授权失败传播。最终方法 SHA `6932c9aa87e706604a40fe933c9dbf2cc47786dae234d4f58269f5ea0313accb`：限定工程 GO；最后上下文异常日志脱敏独立复验通过。
- advice_safety 独立审查 T5 签名与 API 锁内比对，并以独立 PostgreSQL 并发反例复验：限定工程 GO。
- write_domain 独立审查评测导出，发现同会话错误助手指针以及真实 owner 编码兼容问题；两项均以真实持久化 RED 固化，复用现有 owner 编码生成方法后，两项独立复验通过，完整 PostgreSQL 集合 53 passed，限定工程 GO。
- 上述工程 GO 不等于医学、完整产品或发布 GO。没有用本地 commit 替代授权，也没有为审阅擅自推送。

## Gate 与恢复条件

G3：**BLOCK**。高风险 LLM change gate 要求真实模型证据，当前离线 gate 不能替代。

已实际尝试 `harness_llm_regression_gate.py --include-live-llm`：5 个 live orchestrator 场景没有取得有效模型验收。运行环境报本地 PostgreSQL 角色 `health_app_runtime` 缺失，预算守卫不可用；后续供应方路径出现 `ai_consent_required`。这些是环境/授权阻断，不是 5 个质量反例，也不是可接受的质量结果。旧人工 fallback 吞掉策略错误的问题已修复，未通过关闭守卫、创建同意或伪造 CI 变量绕过。

恢复方式：在具备合法模型同意和正常预算守卫的验收环境，对最终候选重新运行 live gate；通过后再验证完整 CI-mode、真实主干 CI 与模拟器关键用户路径。版本变化后须重新绑定证据。当前没有设置 `HARNESS_LIVE_LLM_EVAL_CONFIRMED`。

G4：关键代码切片完成独立工程复审；医学审阅与产品完整验收仍待完成。G5/G6：未进入，T10 发布另需授权。计划中的 P95、任务满足率与临床效果目标仍是目标，没有声称提升。

## 交接断点

当前可以审查本地候选 diff 和合成测试；应先解决 live 验收环境及受审医学依据，再进入发布链路。仍需完成 T7 非快速背景策略、T8 真实版本/别名/标注与持续采集、完整回归和模拟器验收；不得把本次部分本地实现标成 T0–T10 全量交付。

## 私有证据归档

定向测试日志、live gate 真实失败记录和候选代码逐文件 SHA256 已复制到本地私有目录 `/Users/liqiuhua/.codex/artifacts/reva-reliability-implementation-20260911/`。`candidate-files.sha256.json` 绑定本地候选，不是 commit、部署或线上性能证明；生产健康原文不进入本仓库。

## 发布推进（2026-09-11）

已获提交与部署授权；代码逐文件比对与上一轮验收快照一致。当前 origin/main 与本地基线均为 f791da13e，该基线 CI 34553931110 成功；这不证明本轮候选 CI。下一轮计划见 `docs/plans/2026-09-11-health-harness-next-iteration.md`。真实模型门禁仍待当前候选验证，未以授权替代通过证据。

## G1 · 需求准入

裁决：PASS。沿用关联计划的 RequirementAdmission 与 focused spec：修复健康 Agent 的领域、时间、回执和安全边界，不增加诊断处方或自动干预能力。

## G3 · 当前验收裁决

裁决：BLOCK。定向本地测试与工程复审通过；当前尚缺真实模型门禁、完整候选 CI 和发布环境验证。parked 表示发布停在该阻断点，不表示代码未实现或任务已上线。
