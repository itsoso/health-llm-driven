# 简单症状记录的调用与输入预算

| 字段 | 值 |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | S7 生产读回完成 |
| 工作流 | quick_fix + safety-gate → backend-deploy |
| 基线 | 7e69aa250564f3d08194bc274bd0be1d62fbfec7 |

## G1 准入

裁决：PASS。用户要求继续解决简单症状记录两轮调用和大输入；沿用[请求链路性能规格](../specs/2026-11-03-agent-pipeline-performance.md)的 ExecutionEvent / WriteIntent、当前轮授权、写后核验和质量底线。本次为既有流程的局部性能修复，不增加诊疗、权限、通知或数据用途。原共享 main 有其他改动，沿用用户已授权的隔离工作区。普通聊天 PR #305 由另一工作区推进，不纳入本次候选。

## 行为与质量契约

原规则漏掉“记录流鼻涕症状”的“症状”后缀；症状领域质量门还会使简单请求携带完整上下文，并执行模型选工具与模型整理回复两轮。补齐后缀的当前轮授权识别，另用完整正向语法只接纳明确记录单一流鼻涕、鼻塞、打喷嚏的 typed 请求。

在现有 domain 开关、无附件/附加上下文、无待确认/恢复/只读/运行写阻断的门内，跳过可选路由和模型选工具，仍经真实 Pi、参数校验、能力网关、普通 API 写入和回执核验。只有核验回执后才由共同收尾输出；既有后写安全说明保留。原文、owner、历史记录和幂等边界不变；未知尾句、严重程度/日期、胸痛等急症、语音和医疗问答保留原流程与质量模型。没有将通用症状领域降为低风险。

## 目标与停止条件

同一组合成请求完整核验目标小于 3 秒，候选模型调用与输入为零；不能用进度冒充有效结果。任何越权/重复写、错误日期、描述丢失、漏掉附加医疗问题、假成功、质量降低或长尾变差即停止推广，保留当前健康生产版本修复候选。不创建备份或恢复旧配置。

## 可复现证据

[逐样本机器证据和复现脚本](../reviews/2026-11-04-simple-symptom-performance.json)。三种写法各两次，双方同一真实 Qwen3.8 Max 配置、实际 Pi/Gateway、临时合成 owner/SQLite 与真实症状 API；可选路由双方关闭以隔离模型调用差异。

- 基线每次 2 个模型调用、API 输入合计 34,691–34,710 token，单次约 17.3k；系统约 8.5k 字符、17 个工具 schema 约 29.2k 字符，两轮重复。输入含缓存，字符不冒充 token 或计费额。截图约 22k/轮不能用此空白主体精确复原。
- 候选 6/6 保留原描述、单条持久化及单个核验回执；零 provider 调用，0.31–0.73 秒。基线完整耗时 10.06–30.74 秒，中位 14.07 秒；候选中位 0.32 秒。六例最近秩 P95/P99 均是最大值，不代表生产长尾或手机呈现。
- 基线“症状”后缀两例虽写入成功，未原样保留完整描述，质量标记 FAIL，未掩盖。最初未采 token 的六例只作探索，不混入配对；最初探针缺合成加密配置、初次 pytest 缺测试 DATABASE_URL 的环境失败均未算业务 RED。
- RED：修正事件信封读取夹具后在原实现重跑，8 failed、2 passed、34 deselected。GREEN：定向 422 passed；PostgreSQL 17 临时非超级用户角色 44 passed，含真实 API、owner、历史、重复提交与失败回执。
- CI=true 扩展集成 3,443 passed；新增 decision_mode=on 下鼻塞/打喷嚏、新旧会话、附件和分类器失败边界后，定向 50 passed。分类器异常在既有更早阶段直接传播，未为快捷路径吞掉失败。实现未变化。System Map、秘密扫描、Dossier 一致性、diff 检查通过。
- 初轮验证时，独立 safety GO、精确候选真实模型闸、main CI 与上线仍待完成；最终结果见末节。无 Mobile 改动，本次为后端发布；视觉验收按用户要求不作为阻断，不宣称设备验证。

## G4 与主干验证

独立安全评审 GO 绑定 `424f1b462edd2bf6595b11066b1ec3f124dc1077`，独立 44+204 项回归及 4 个正例/93 个对抗反例通过。补充后 PostgreSQL 50 passed。精确候选真实模型闸通过（invariants 12、health core 50、live orchestrator 5，均分 0.92；轨迹契约与 goldens 均通过），发布预检通过。

[PR #309](https://github.com/itsoso/health-llm-driven/pull/309) 经 [PR CI 41839188103](https://github.com/itsoso/health-llm-driven/actions/runs/41839188103) 通过后快进合入 main，同 SHA 的 [完整 main CI 41840961969](https://github.com/itsoso/health-llm-driven/actions/runs/41840961969) 32/32 通过。

## 发布预检失败与处理

[validate 41842943880](https://github.com/itsoso/health-llm-driven/actions/runs/41842943880) 在 canonical source/CI 首步失败：`trusted_release_gate._latest` 对同 SHA 的所有 CI 检查 main 身份，快进合并保留了同 SHA、feature 分支的绿色 PR run，因此拒绝。不是功能测试失败，也没有到 dispatch admission、production credential、SSH 或任何生产 claim。该次失败保持原样，不重发或删除。

以本次验收文档更新形成独立 main 后继，实际应用字节与通过评审/实测的 424f 完全一致。后继只推 main，不产生同 SHA PR CI；仍要求新鲜精确 live gate、完整 CI 和新 SHA validate，不更改严格发布闸。文档 push 的轻量 CI 不能代替完整验证，因此显式补一次该候选完整 CI。生产截至本节仍为 91b1，未 stage、刷新凭据、轮换或部署。现有只读凭据过期，已准备受审刷新流程，但未执行。


## 最终发布与线上读回（2026-11-05）

最终应用发布 revision 为 `7665d92c38fc89b8defc0c8cf2153a7e7892158c`，与已审 424f 的应用字节一致。[完整 CI 41843626484](https://github.com/itsoso/health-llm-driven/actions/runs/41843626484) 32/32 通过，[validate 41845146155](https://github.com/itsoso/health-llm-driven/actions/runs/41845146155) 成功，精确真实模型闸通过。

[后端发布 41864708858](https://github.com/itsoso/health-llm-driven/actions/runs/41864708858) 成功。独立只读验收确认：生产 HEAD 精确且干净，回执 SUCCEEDED，runtime COMMITTED/finalized/code-only-no-backup，lease 不存在；backend、worker、beat 全 active；内外网 health 200，受保护接口匿名访问 401。生产 executor 与症状测试文件摘要匹配该候选。完成回执 SHA256 `56da0bee7c705f8b88f98207352f4bbfe64f8e561f359a3423b4625c90af3b63`。

授权首次本地操作在服务器 idle 检查、远端撤权意图之前停止。保留原失败与摘要；用户要求保留的其他只读扫描自然退出，没有终止扫描。新鲜 idle 证明与独立评审通过后，使用绑定原证据的限定续行完成轮换，未重跑旧发布。只读凭据 v1 成功后到期，v2 经独立评审正常续期；全部原回执保留。未新增备份或回退副本。

无 Mobile 改动，不重复 OTA。视觉验收按用户明确指令省略；本次不代表设备呈现或生产 P95 验收。此前章节中的待办/未发布描述是当时状态，由本节终态取代。
