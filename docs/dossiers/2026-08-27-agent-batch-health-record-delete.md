# Dossier: Agent 批量健康记录删除

| 字段 | 值 |
|---|---|
| slug | `agent-batch-health-record-delete` |
| 创建日期 | 2026-08-27 |
| 当前阶段 | G5 PASS；G6 技术验证 PASS，等待用户真实重试 |
| 状态 | deployed-awaiting-user-validation |
| 负责 | Codex + release owner |
| 反馈环 | Backend tests + independent safety review + backend deploy |

## S0 · 用户需求（逐字）

> “分析刚才Mobile上的操作记录，我请求删除错误输入的两餐，但是系统无法响应，如何解决？”
>
> “修复并发布”

## S1 · Discovery

- 生产三次相关 Agent run 都停在 `waiting_for_user`，没有工具操作；最后一次 31.09 秒内四次删除调用均被 `delete_requires_explicit_whole_record_intent` 阻断。
- 记录 977/979 仍存在；本次研发和发布验证不删除它们。
- 根因是删除授权、GoalSpec 和 owner 证据均只支持一个类型 + 一个 ID，且回退文案诱导用户继续给出不受支持的泛化确认。

## G1 · 准入裁决

- 对象：`WriteIntent`、`ExecutionEvent`；surface：Mobile + Backend；真源：owner-scoped PostgreSQL 记录和 verified receipts。
- 安全：隐私敏感、不可逆健康写；`manual_confirm`。
- 最小切片：明确饮食类型、正整数 ID、去重后最多 5 条；全部 owner 校验后才执行。其他类型保持单条删除。
- Spec：`docs/specs/active/2026-08-27-agent-batch-health-record-delete.md`。
- **裁决：PASS**。用户明确要求修复并发布，且方案不扩大到模糊或跨类型删除。

## S2 · PRD

- 复用 `docs/prd/reva-personal-health-os-prd.md` 的健康写入与可验证执行原则。
- 非目标：非饮食类型批量删除、按“上一条/全部/范围”删除、混合类型、跨回合猜测、生产验证删除真实数据。

## S3 · 规划

- 链接：`docs/plans/2026-08-27-agent-batch-health-record-delete.md`。
- 发布：仅 Backend；无 OTA、原生包和数据库迁移。

## G2 · 可行性 + 安全压测

- 使用当前回合闭合语法编译完整 ID 集；owner lookup 必须返回全集。
- 查询后由服务端生成确定性删除计划，模型不能少删、多删或换 ID。
- 继续使用既有逐条持久化计划、verified receipt 和部分失败恢复，不新增宽泛批量 API。
- **裁决：PASS**。

## S4 · 研发任务分解

- [x] RED：批量语法、目标 Goal、策略全集校验、确定性计划测试。
- [x] GREEN：最小实现并保持单条兼容。
- [x] G3：聚焦回归、LLM/治理/结构检查。
- [x] G4：本地 commit 后独立安全评审。
- [x] 推送首版候选到 main。
- [x] G4b：依赖安全与部署同步修复独立复审。
- [x] Backend 部署、生产只读验证。

## S5 · 实现

- 闭合语法只接受明确饮食类型、去重后 2 至 5 个正整数 ID；保留所有类型单条删除兼容。
- GoalSpec 保留全部 ID；owner lookup 使用饮食列表 100 条窗口，全部命中后才返回安全目标集。
- 查询后删除调用由服务端按完整 ID 集生成，模型少发、漏发或追加其他目标都不能改变计划。
- Capability policy 要求当前回合文本目标集与 owner-scoped 查询结果全集一致；缺一条时对每个删除调用都拒绝。
- 拒绝提示改为给出可执行的明确句式，并在 owner 不完整时说明本轮零删除。

## G3 · 测试闸

- TDD RED：新增 API 在实现前因缺失 `explicit_whole_record_delete_targets` 和确定性删除 builder 发生预期收集失败。
- Backend 核心回归：`2788 passed`（删除语法、Goal、Capability、目标解析、Executor 完整状态文件）。
- Gateway 删除聚焦：`28 passed`；Runtime/Gateway 删除聚焦合跑另有 `29 passed`。
- 生产路径回归：模型只给一个删除调用和完全不给删除调用两种情况均执行 `list -> delete 977 -> delete 979`，得到两个 verified receipts。
- Live LLM gate：最终候选 `12/12 invariants`、`50/50 health_agent_core`、`5/5 orchestrator`、`12/12 trajectory contract`、`9/9 trajectory goldens`；LLM change gate PASS。
- 结构闸：System Map、113 dossiers、agent-skill governance PASS；目标 Ruff、`py_compile`、`git diff --check` PASS。全仓 Ruff 仍有 635 个既有 report-only 问题，不在本次范围。
- 首次 live 尝试因错误本地 PostgreSQL 角色和 OpenAI 余额不足失败；改用项目现有 `health_test` 本地数据库执行同一 quota guard 后，最终候选 live gate 完整通过，没有绕过配额护栏。
- 首版候选推送后，主干 CI 新命中 `chromadb==0.6.3` 的 `CVE-2026-45830`、`CVE-2026-45831` 和 critical `CVE-2026-45833`；审计数据没有给出任何修复版本，因此未带红部署。
- 生产知识路径已使用 reviewed System KB，legacy Chroma runtime 默认关闭；从生产 requirements/lock 移除 ChromaDB 及其专属传递依赖，其他 127 个锁定包版本零变化。
- 修复部署残留风险：依赖同步在写 lock marker 前卸载旧 `chromadb`/`chroma-hnswlib`，锁验证器同时拒绝两项残留；匹配 marker 但验证失败时先持久删除旧 marker，修复失败不得伪装成可复用环境。
- 修复回滚风险：旧锁在服务停止状态安装后立即移除两项无修复版本的 Chroma 包，再由 immutable stage verifier 按“目标锁减去禁用包”验证；既保留旧提交其余依赖语义，也不重新暴露漏洞。
- 依赖、部署与安全合同 `142 passed`；完整回滚合同 `39 passed`；Chroma 缺失下知识路径 `49 passed`；批量删除核心回归再次 `2788 passed`。
- 新锁 `pip-audit` 为 `No known vulnerabilities found`；全新临时 venv 从哈希锁安装 127 个包、依赖兼容检查通过且 `chromadb=absent`。
- System Map 已移除生产 `resource.chromadb` 依赖并重生成，结构、Dossier、Skill 治理和硬阻断 Ruff/shell 语法门禁通过。
- **裁决：PASS**。

## G4 · 安全闸

- 固定评审提交：`2528282c08c9d5c730c44999998d60b13fb85e4a`。
- 独立 reviewer 结论：**GO**；Critical 0、Important 0。
- 已确认闭合语法、owner-scoped 全集校验、查询不完整时零删除、服务端确定性完整计划、sealed write plan、逐条响应 ID 校验，以及部分失败/未知结果不假报全部成功。
- 非阻断项：`health_manage_mutation` 尚未注册独立 postcondition verifier；当前由精确回执、失败状态机和 sealed write plan 保证完成性，后续可补充 ID 集 postcondition 作为纵深防御。
- 结论只覆盖固定本地 commit 的代码安全；不替代 main/CI、部署健康和生产行为验证。
- **裁决：PASS**。

## G4b · 依赖与发布安全复审

- 首轮固定候选 `68ab3f671ef91c31aad7c5752fdafe72cdd79651` 结论：**NO-GO**；发现旧 SHA 回滚错误套用候选 verifier，以及单独残留 `chroma-hnswlib` 可绕过同 digest marker 复用检查。
- 已补 TDD 回归并修复：前向部署同时禁止两项残留、失败修复先失效 marker；回滚使用哈希封存 verifier 的显式 sanitized 模式，服务启动前证明禁用包已移除且目标锁其余依赖准确。
- 修复候选 `d70c868ac174476a133bac532b1727a6fa721b6d` 独立复审结论：**GO**；Critical 0、Important 0、无阻断 Minor。
- 独立证据：聚焦 verifier/marker/rollback `9 passed`；完整 rollback 合同 `39 passed`；`git diff --check`、shell 语法、verifier 编译与 System Map drift 均通过。
- 结论边界：只允许进入 main CI/G5，不替代生产 venv、systemd、精确 SHA 和服务稳定验证。
- **裁决：PASS**。

## S6 · 部署

首版候选 `241b5eb15efd496a5d41a4e799beba7070780e9b` 推送后因无修复版本的 ChromaDB 漏洞被 CI 阻断，没有带红部署。最终运行时候选 `5d84a48f4d3eb53228487db9c6c88e82d009f909` 的 main CI `52/52` 成功，随后从全新 clean main clone 执行 `./deploy.sh -b`，退出码 0。

## G5 · 部署健康闸

- 生产备份 43 MB、权限 0600；恢复演练 237 张表通过；站外加密归档哈希与 HMAC 真实性通过。
- 回滚点 `994c5665aef34fcf092679ba99edc12b7adfa9b8` 对实时 schema 兼容，候选按精确 SHA `5d84a48f4d3eb53228487db9c6c88e82d009f909` 安装。
- 生产实际卸载 `chromadb 0.6.3` 与 `chroma-hnswlib 0.7.6`；127 个锁定包精确校验及 `pip check` 通过，依赖 marker 与 lock digest 一致。
- 受控迁移无新增项，runtime schema 202 张表通过；多轮健康度均 `60/60 PASS`，4 个服务 active，runtime state finalized。
- System KB staged contract、906 文档/906 dense vectors、Skills `22 = 22` 均通过；feature flag 保持 false。
- **裁决：PASS**。

## S7 · 上线验证

- 生产只读解析探针：`删除饮食记录 977 和 979` → `(('diet', 977), ('diet', 979))`。
- Fail-closed 探针：缺少记录类型的 `删除 977 和 979` 和超过上限的 6 条饮食删除均返回空目标集。
- 本次验证未删除 977/979；真实结果必须由用户在新版本中重新明确请求后，根据 verified receipts 确认。

## G6 · 验证闸

技术路径 **PASS**；用户真实删除闭环 **Pending**。建议请求：`删除饮食记录 977 和 979`。

## S8 · 沉淀

Pending。
