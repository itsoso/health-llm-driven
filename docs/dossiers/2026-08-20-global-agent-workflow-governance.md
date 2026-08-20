# Dossier: Global Agent Workflow Governance Skill

| 字段 | 值 |
|---|---|
| slug | `global-agent-workflow-governance` |
| 创建日期 | 2026-08-20 |
| 当前阶段 | S8 沉淀 |
| 状态 | validating |
| 负责 | Codex |
| 反馈环 | synthetic registry tests / plugin digest / cross-project forward smoke |

## Correct Course

- [x] 2026-08-20 governance bootstrap instead of a second runtime Router
  - 触发:全局隐式 Router 与 Reva 已启用 Router 会争夺控制权；未配置项目还可能误用 Health 路由。
  - 旧基线:复制 Reva checker/Router 成为全局默认。
  - 新基线:首个全局 Skill 只治理和生成项目本地 Registry/Router；普通任务仍由项目 Router 或项目规则接管。
  - 回退阶段:S2。
  - 需重跑 Gate:G2、G3、G4、G5。
  - 用户确认:☑ 用户确认可以沉淀为全局 Skills。
- [x] 2026-08-20 remove runtime routing from the global validator
  - 触发:独立复审发现 `route` 命令会再次选择 primary/immediate/deferred，和“全局层只治理”自相矛盾。
  - 旧基线:全局 validator 同时做静态校验与运行时路线选择。
  - 新基线:v1 CLI 只保留 `check`；项目可以有零或一个 active Router，mode 名称及动态选择完全归项目。
  - 回退阶段:S2。
  - 需重跑 Gate:G2、G3、G4、G5。

## S0 · 用户需求(逐字)

> 能否沉淀为全局的skills？

> 好

> 可以

- 谁用 / 解决什么:让不同项目复用可靠的 Agent Skill 角色、生命周期和治理检查，同时不携带 Reva 领域策略。
- 范围:一个个人全局 Codex Plugin、一个治理 Skill、项目 Registry Schema/validator、内容摘要、安装与跨项目验证。
- non_goals:全局运行时 Router、Health/医疗规则、项目部署命令、生产遥测、批量迁移所有项目。

## S1 · Discovery

- Reva Registry/Router 已在 fresh Codex 进程验证，但 checker 的 root、Skill ID、模式、Overlay 与发布目标属于 Reva。
- 从非 Health 项目调用 Reva checker仍返回 Reva 路由，证明直接复制不是跨项目方案。
- 当前安装 cache 与其 marketplace revision 内容一致；较旧本地 checkout 中同版本文件不同，证明安装真实性必须锚定发布 revision 与内容摘要，不能锚定任意 worktree。
- `browser-llm-orchestrator` 有独立工程 Skills 与产品运行时 Skills，可作为非 Health 前向 smoke；稳定 CI 仍使用合成 fixture。

## G1 · 准入裁决

- classification:internal engineering governance。
- smallest_end_to_end_slice:one governance Skill → one deterministic project Registry validator → content-locked personal Plugin → fresh discovery and two-project smoke。
- safety_boundary:不读取或写入健康数据，不执行项目命令，不接生产系统。
- **裁决:PASS** —— 解决可复用治理与供应链完整性问题，且不会新增产品行为。

## S2 · 设计合同

- 链接:`docs/plans/2026-08-20-global-agent-workflow-governance-design.md`。
- 核心合同:元治理而非第二 Router；全局层只拥有角色、生命周期、Schema/validator 和内容锁；项目层拥有路由、Controller、Overlay、Terminal、Gate 与领域规则。

## S3 · 规划

- 链接:`docs/plans/2026-08-20-global-agent-workflow-governance-implementation.md`。
- 顺序:定义/G2 → Plugin skeleton → RED → one-Skill GREEN → official validation → install/digest → forward smoke/review。

## G2 · 可行性 + 风险压测

- controller collision:首版不参与普通任务路由，消除第二隐式 Router。
- domain leakage:合成测试拒绝 Reva/Health ID 与平台专属编排命令；没有项目 Registry 时无 fallback。
- filesystem:只读显式 project root 内固定 Registry；拒绝绝对路径、`..` 和 symlink source。
- supply chain:SemVer + 完整 runtime file set digest；source/cache/release revision 三者核验。
- privacy/network:v1 无遥测、Hook、MCP、网络访问或自由文本事件。
- rollback:从个人 marketplace 删除 Plugin 即可；项目 Registry 不依赖全局 Plugin 才能被读取。
- **裁决:PASS** —— 允许进入一个 Skill 的 TDD 实现；禁止在本 slice 增加全局运行时 Router。

## S4 · 研发任务分解

- [x] T1 独立设计、实施计划与 Dossier。
- [x] T2 Plugin skeleton 与失败测试 RED。
- [x] T3 one-Skill、Registry validator 与 content lock GREEN。
- [x] T4 官方验证、个人 marketplace 安装与 cache digest。
- [x] T5 Reva/非 Health 前向验证和独立 G4 复审。
- [x] T6 双仓窄提交与 committed-state 复验。

## S5 · 实现

- Reva 文档在基于最新 `origin/main` 的 `codex/global-workflow-governance` 干净 worktree 中进行。
- 全局 Plugin 使用独立个人目录与独立本地 Git 历史；不复制共享主工作树 WIP。
- Plugin:`agent-workflow-governance@personal` `0.1.3`，唯一 Skill 为 `governing-agent-workflows`。
- Plugin source commit:`d6d9ac00b326597566178d16ca1a6a50adcd3887`；未配置远端、未发布公共 marketplace。

## G3 · 测试闸

- 初始 RED:26 failed / 1 passed，因 Skill、validator、content lock 尚未实现。
- Correct Course RED 1:33 项中 6 failed，覆盖版本未升、Router 计数、全局 `release` 语义与内容锁重写。
- 独立 G4 RED:42 项中 9 failed，覆盖可删除/篡改旧 lock、重复 JSON key、Terminal 多目标与 external 路径/URL。
- 内容锁结构 RED:46 项中 6 failed，覆盖 manifest 版本、旧 lock 版本与 `schema/plugin/files/extra` 四类篡改。
- 最终 focused suite:46 passed。
- official Plugin validator:PASS；official Skill quick validator:PASS。
- Ruff check / format check、Python compile、`git diff --check`:PASS。
- committed-state content lock:version `0.1.3`，root SHA-256 `92f7fd850abcb98f4aaf32236a8009acc39a0c2bfb36c410412d476f68e30202`。
- **裁决:PASS**。

## G4 · 安全闸

- 评审范围:controller ownership、路径逃逸、项目泄漏、平台泄漏、未知输入、同版本内容漂移和普通任务误触发。
- 已关闭:第二 runtime Router、硬编码 `release` mode、强制必须有 Router、从目标项目 cwd 误调同名脚本。
- 已关闭:删除/篡改旧 lock 后重生成、重复 JSON key、Terminal 多目标复用、external package 伪装本地路径/URL。
- 独立终审对 `schema/plugin/files/extra` 四类 prior-lock 篡改逐一重放，均 fail closed；源码、安装 cache、Git 对象与内容摘要一致。
- **裁决:PASS** —— 0 BLOCKER / 0 HIGH。

## S6 · 部署

- 目标是个人 Codex marketplace；不部署 Reva 服务或移动端。

## G5 · 部署健康闸

- 验收:官方 CLI 可列出并启用 Plugin，source 与 cache digest 一致，fresh task 能发现 Skill，卸载路径可用。
- CLI:`/opt/homebrew/bin/codex` `0.148.0-alpha.21`。
- personal marketplace 安装:enabled，source `/Users/liqiuhua/plugins/agent-workflow-governance`，cache `/Users/liqiuhua/.codex/plugins/cache/personal/agent-workflow-governance/0.1.3`。
- source/cache 都通过 content lock，root SHA-256 同为 `92f7fd850abcb98f4aaf32236a8009acc39a0c2bfb36c410412d476f68e30202`。
- fresh positive task 实际使用 `agent-workflow-governance:governing-agent-workflows`，并声明不替代项目 Router。
- **裁决:PASS**。

## S7 · 验证

- 合成 fixture 为 blocking 证据；Reva 与非 Health 仓库只做只读 forward smoke。
- 非 Health `browser-llm-orchestrator` 无 Registry 时，安装版 validator 返回 `registry_missing`，没有 Health fallback。
- `0.1.3` fresh positive task 实际加载全局治理 Skill、读取其完整合同并返回 `registry_missing`；普通 TypeScript UI bug 与 Reva 饮食卡 bug 两个 fresh negative task 均未使用全局治理 Skill。
- fresh smoke 通过 ChatGPT.app 内真实二进制执行，现场读取安装版 Skill 与合同；`/opt/homebrew/bin/codex` 的 symlink 路径不能解析同目录 code-mode host，属于本机 CLI 包装限制，不归因于 Skill。

## G6 · 验证闸(人在环)

- 技术 G6:正/负触发、项目 Router 保留、无 Health fallback、安装版源码读取、独立 G4 终审与双仓 committed-state 复验均通过，裁决 PASS。
- 效果 G6:继续复用原 Reva benchmark 规则；没有匹配的前瞻样本前，不宣称已提高速度或质量。
- **裁决:技术 PASS；效果 PENDING**。

## S8 · 沉淀

- 个人 Plugin 来源:`/Users/liqiuhua/plugins/agent-workflow-governance`；版本 `0.1.3`；内容摘要 `92f7fd850abcb98f4aaf32236a8009acc39a0c2bfb36c410412d476f68e30202`。
- 安装:`/Applications/ChatGPT.app/Contents/Resources/codex plugin add agent-workflow-governance@personal --json`；回滚:`/Applications/ChatGPT.app/Contents/Resources/codex plugin remove agent-workflow-governance@personal --json`。
- 项目 opt-in 只创建 `.agents/workflow-governance/registry.json`；项目仍拥有 Router、模式、Gate、领域规则与发布命令，不把项目策略上移。
