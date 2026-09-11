# Dossier: 健康 Agent 可靠性改进

| 字段 | 值 |
|---|---|
| slug | health-agent-reliability |
| 创建日期 | 2026-09-11 |
| 当前阶段 | G5 阻断，源码准备超时进入 NEEDS_OPERATOR，禁止重跑 |
| 状态 | parked |
| 负责 | Codex |
| 反馈环 | 合成回放、PostgreSQL、Mobile、真实模型与发布验证 |

- 状态：代码已提交并推送，最终候选 CI 与工程安全复审通过；续跑已通过服务器就绪检查，但正式源码准备超时进入 NEEDS_OPERATOR，后端与 OTA 均未上线。
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
| T10 | 发布受阻 | 已获提交部署授权，隔离真实模型与候选 CI 通过；源码准备超时需受审处置，模拟器路径与上线后观察待完成，医学审阅另行补齐 |

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

真实 PostgreSQL 测试使用独立、名称含 test 的本地数据库。纯策略批量测试采用快速单元环境，不能代替数据库语义验证。最终候选已取得下文记录的真实 CI 证明；本机单进程全量入口曾遇到 SQLite 线程互锁和 Jest 状态串扰，未将这些运行记为通过。后续使用 CI 的隔离分片完成相关验证。

## 独立评审与整改

- advice_safety 独立复验主 stream 的普通上下文意外剂量输出、协议终态及编号只读写入拒绝。修复后反例通过；发现编号可走多模型捷径后新增真实 RED，受限只读回合统一保留普通路径。
- time_queries 独立审查多模型 lead/perspective/synthesis 入参、可见正文和预算/授权失败传播。最终方法 SHA `6932c9aa87e706604a40fe933c9dbf2cc47786dae234d4f58269f5ea0313accb`：限定工程 GO；最后上下文异常日志脱敏独立复验通过。
- advice_safety 独立审查 T5 签名与 API 锁内比对，并以独立 PostgreSQL 并发反例复验：限定工程 GO。
- write_domain 独立审查评测导出，发现同会话错误助手指针以及真实 owner 编码兼容问题；两项均以真实持久化 RED 固化，复用现有 owner 编码生成方法后，两项独立复验通过，完整 PostgreSQL 集合 53 passed，限定工程 GO。
- 上述工程 GO 不等于医学、完整产品或发布 GO。没有用本地 commit 替代授权，也没有为审阅擅自推送。

## Gate 与恢复条件

G3：**PASS（本轮工程验收范围）**。应用修复提交 `7d980b4cf297f453d5479c7e3147846e0a5f12ba` 的真实模型验收 5/5，通过评分 0.96；使用与线上相同的 tokenplan / MiniMax-M2.5、隔离合成 PostgreSQL 主体及真实授权/预算守卫。未读取生产健康原文，未替真实用户生成同意。此 suite 只覆盖 synthesis，不能推导完整 Agent 或临床水平。

最终候选 `7498ab01a2c04e53e440f0351e8a284b2e479f48` 仅在其基础上更新测试契约和计划，全部应用及 eval 代码逐字节等价；沿用原模型报告，保留原执行提交和时间，没有冒充再次执行。关联证据为私有目录中的 `7498ab01a/source-equivalence.json`。

- 最终候选真实 CI：`34581238855`，success；此前失败记录 `34579145765`、`34580350949` 保留。
- 固定提交独立安全复审：原候选工程 GO；来源标签增量独立 10 项通过，混合正文及所有安全扫描保持原边界。
- CI 发现的过期日期、正文/推理释放、剂量冲突测试已同步；确定性工具结果来源误标已修复。相关定向集 60 与 182 项通过；后续隔离分片 536 项通过、1 项跳过。
- Mobile 按 CI 方式隔离运行：305 套、2870 项通过；前端 385 项通过。临床专业审阅、1.3.3 模拟器 UI 路径与长期效果仍未验证；现有模拟器为 1.3.1，不能充当本次 OTA 验收。

G4：**GO（限定工程范围）**，最终候选以源码等价证据关联固定复审，不代表临床认证。

G5：**BLOCK**。受审发布 validate `34581923448` 成功；backend 发布 `34582119405` 在只读服务器 readiness 失败，backend job 被跳过。确定故障为服务器到 GitHub 的 Git 请求持续超时，内部 loopback SSH 正常。多个 GitHub 官方地址已做有界只读验证，未关闭 TLS、修改发布 Gate 或上传本机代码替代 canonical source。

发布短期双身份已经受审 revoke 撤销；本轮 GitHub SSH secret 与本机临时私钥已删除。为诊断所做的单条 hosts 调整已精确恢复原始文件，备份和失败证据保留。未产生 release/deployment started 标记，未执行数据库迁移或业务重启；线上仍为 `5ddd9402d22c8124bc84b578662ea87c1f6e432c`。按 backend-deploy/mobile-ota 顺序，后端未通过健康门，OTA 未发布。G6 尚未进入。

## 交接断点

最新断点以下方续跑记录为准：5fe8c3d83 的授权已经消费并进入 NEEDS_OPERATOR，不能重新 dispatch、重置标记、直接撤权轮换，或因没有业务 lease 就推断可退役。先完成这一类源码下载超时的受审取证与处置方案，再恢复发布。仍需完成 T7 非快速背景策略、T8 真实版本/别名/标注与持续采集、模拟器验收；不得把本次部分实现标成 T0–T10 全量交付。

## 发布续跑（2026-09-11）

- 候选 `5fe8c3d83f526e6b529bf1684b0ff956f6ede4ff` 的 CI `34582936629` 成功。与真实模型及固定独立复审提交相比仅测试和文档不同，应用及 eval 字节未变；原报告保留原 SHA 与时间，关联证据为私有 `5fe8c3d83/source-equivalence.json`。
- validate `34586153621` 成功；backend workflow `34586693554` 的 preflight 和服务器 readiness 均成功，backend 最终失败。没有执行原生构建或 TestFlight。
- 网络诊断发现系统 Git 2.34.1 未采用诊断参数 `http.curloptResolve`，实际目标须从连接证据核对。经公共 DNS 和 GitHub 官方地址清单校验的节点，实际 `ls-remote` 连续三次通过，且 root canonical staging 的精确 SHA 下载成功；这些小规模请求通过仍未证明正式 clone 稳定。
- 受审 bootstrap 已安全退役 7498ab01a 并安装候选专用六小时身份。正式 prepare 的前两次 clone 以 exit 128 低速超时失败，最后一次触发执行器的有界超时；`completed.json` 为 **NEEDS_OPERATOR**，原始日志为五行。不能将其改记 PREPARATION_FAILED，也不满足现有历史四行初始 clone 失败恢复入口。
- 新鲜只读取证：`prepared.json`、`deployment-started.json` 与 native 标记均不存在，业务 lease 不存在，没有观察到残余发布/Git 进程；这仅是取证，不解除终态阻断。线上仍为 `5ddd9402d22c8124bc84b578662ea87c1f6e432c`，backend、worker、beat 均 active，未迁移或切换业务服务。
- 单条 hosts 临时调整已经精确恢复原文件，摘要 `b3bc3f05707892989a6ec855943cdf9718538a060fc82c4b050dbe48662f4114`。本次短期身份和失败现场按 NEEDS_OPERATOR 规则保留供调查，未重置或轮换；这不同于上一轮未消费身份已清理的状态。
- OTA source guard 通过，Mobile/shared 摘要未变；按后端健康门前置规则，**OTA 未发布**。现有 1.3.1 模拟器仍不能证明 1.3.3 更新验收。
- 私有证据：`/Users/liqiuhua/.codex/artifacts/reva-release-20260911/5fe8c3d83/failed-preparation-evidence.json`、`backend-workflow-result.json`、`network-repair.json`。网络记录中的调整摘要是过程中间态，最终恢复结果见本节与收尾回执。

## 私有证据归档

定向测试日志、live gate 真实失败记录和候选代码逐文件 SHA256 已复制到本地私有目录 `/Users/liqiuhua/.codex/artifacts/reva-reliability-implementation-20260911/`。`candidate-files.sha256.json` 绑定本地候选，不是 commit、部署或线上性能证明；生产健康原文不进入本仓库。

## 发布推进（2026-09-11）

已获提交与部署授权；代码逐文件比对与上一轮验收快照一致。当前 origin/main 与本地基线均为 f791da13e，该基线 CI 34553931110 成功；这不证明本轮候选 CI。下一轮计划见 `docs/plans/2026-09-11-health-harness-next-iteration.md`。最终工程验证与实际发布结果见上方 Gate 记录；授权不替代通过证据。

## G1 · 需求准入

裁决：PASS。沿用关联计划的 RequirementAdmission 与 focused spec：修复健康 Agent 的领域、时间、回执和安全边界，不增加诊断处方或自动干预能力。

## G3 · 当前验收裁决

裁决：PASS（工程范围）。最终候选 CI、源码等价的真实模型证据与独立复审具备；医学、完整产品体验不据此宣称通过。当前 parked 的原因是 G5 源码准备超时的 NEEDS_OPERATOR 终态，不代表已上线。
