# Dossier: Reva 研发 Agent Skill 治理

| 字段 | 值 |
|---|---|
| slug | `agent-skill-governance` |
| 创建日期 | 2026-08-20 |
| 当前阶段 | S7 本地验证 |
| 状态 | verified-local / publish-blocked |
| 负责 | Codex |
| 反馈环 | deterministic registry / Router recommendation / repository gates |

## Correct Course

- [x] 2026-08-20 controller convergence
  - 触发:压力场景证明 Product Pipeline、Health Harness 与通用执行 Skill 会同时拥有计划、ledger、checkpoint 和代理调度。
  - 旧基线:按自然语言 trigger 机械叠加所有相关 Skill；Codex 直接读取或复制 Claude adapter。
  - 新基线:每个任务先经一个确定性 Router；最多一个 primary controller；overlay 只阻断；Claude/Codex 使用各自薄 adapter，共享 agent-neutral 注册表。
  - 回退阶段:S3。
  - 需重跑 Gate:G2、G3、G4。
  - 用户确认:☑ 用户要求基于讨论形成最佳 Skills 推荐并治理。
- [x] 2026-08-29 context-budget optimization
  - 触发:Codex 近期体感变慢；入口规则、System Map 全局摘要与重复 flow relation 形成常驻上下文税。
  - 旧基线:`AGENTS.md` 内嵌教程与 Skill catalog；所有仓库/非仓库任务先读全局地图；查询默认一跳；全局摘要常驻计数并按 flow 重复关系。
  - 新基线:非仓库元任务跳过项目 Router/地图；仓库研发先 Router、后按需 query-first；默认零跳；全局摘要 4KB 硬预算；计数显式 `--counts`；查询 12KB 硬预算，超限 fail closed。
  - 回退阶段:S3。
  - 需重跑 Gate:G3、G4。
  - 用户确认:☑ 用户要求按推荐直接改造。

## S0 · 用户需求(逐字)

> 基于以上讨论，形成本项目的最佳skills的推荐并进行治理

- 谁用 / 解决什么:让 Claude、Codex、Cursor 等研发 agent 以最小充分 Skill 集完成任务，避免触发风暴、平台指令泄漏和多套状态机。
- 范围:研发 agent skills、plugin adapters、机器注册表和仓库治理 Gate；不修改 `backend/skills/*` 产品运行时技能，不接生产 telemetry。

## S1 · Discovery(现状勘察)

- `docs/agent-skill-binding.md` 让 Codex 直接读取 `.claude/skills/*`。
- repo-local Codex plugin 0.1.0 逐字复制 Product Pipeline / Health Harness Claude adapter，包含 Claude-only 工具和模型指令。
- 一行测试修复的压力场景会触发多项重复流程；跨端提醒场景会出现至少三层编排控制器和两份 ledger。
- `scripts/validate.py`、pre-commit 和 CI 尚未验证 Skill 分类、生命周期、平台边界或唯一 controller。

## G1 · 准入裁决

- classification:internal engineering governance。
- smallest_end_to_end_slice:machine registry → deterministic recommendation → native adapters → blocking repository gates。
- non_goals:运行时健康 Skill、生产遥测、部署和健康建议行为。
- **裁决:PASS** —— 改善研发正确性与维护性，不新增用户健康行为或写路径。

## S2 · 设计合同

- 链接:`docs/plans/2026-08-20-agent-skill-governance-design.md`。
- 核心合同:一个 Router、每任务最多一个 controller、overlay 非 owning、三层供给、四态生命周期、隐私最小事件 schema。

## S3 · 规划

- 链接:`docs/plans/2026-08-20-agent-skill-governance-implementation.md`。
- 路径:契约测试 RED → 注册表/checker → Router/native adapters → local/CI gates → 原始场景前向压测。

## G2 · 可行性 + 风险压测

- 评审方式:两个独立只读压力场景（quick fix 与跨端 feature）+ 源码/adapter 审计。
- 已焊入规划:controller 唯一性、overlay 去重、未知 overlay fail closed、Codex/Claude adapter 分离、事件 schema 禁原始 prompt/健康文本/凭据。
- **裁决:PASS** —— 最小实现仅为本地确定性文件和检查器，无数据库、网络或运行时副作用。

## S4 · 研发任务分解

- [x] T1 设计与实施计划。
- [x] T2 先写治理/插件/接线契约测试并取得预期 RED。
- [x] T3 实现机器注册表、检查器和 Router。
- [x] T4 接入 binding、plugin、validate、pre-commit、CI 和 system map。
- [ ] T5 前向压测、评审、提交与安全推送；本地验证完成，分支分叉与共享工作树阻断 push。

## S5 · 实现

- 当前分支:`main`；仅精确暂存本 Dossier 列出的治理文件，保留共享工作树中的 Health Day / KBase WIP。
- 当前状态:已收敛入口契约与 System Map 上下文预算；保留共享工作树中的 Health Day / KBase / CI WIP，未纳入本次修改。

## G3 · 测试闸

- `python3.12 scripts/check_agent_skill_governance.py check`:PASS，14 skills / 6 routes / 5 overlays / 4 release targets。
- `.venv/bin/python -m pytest backend/tests/test_agent_skill_governance.py backend/tests/test_system_map_agent_context.py -q -o addopts=''`:42 passed。
- `./scripts/system-map-check.sh`:PASS，canonical graph、4KB agent context、mobile nav 与 doc drift 一致。
- `python3.12 scripts/validate.py -v`:PASS；system-map、dossier-consistency、agent-skill-governance 全绿。既有 ruff 635 项为 report-only，不属于本次文件。
- 查询输出预算负例:256 bytes 上限返回 exit 2 和显式 `query context exceeds`，未静默截断。
- `git diff --check`:PASS。
- **裁决:PASS**。

## G4 · 安全闸

- 触发:仅研发治理、只读地图查询与文档拆分；不触发产品健康写路径、数据库、通知或生产部署。
- diff review 确认查询器只读取 canonical artifact；超实体数、超字节数、未知 selector 和无效图均 fail closed。
- 新治理文档保留健康数据隔离、推送隐私、PostgreSQL 语义与发布授权边界；未把这些规则从硬约束降级为建议。
- **裁决:PASS**。

## S6 · 部署

- 无生产部署；交付为仓库内插件、文档、检查器和 CI Gate。

## G5 · 部署健康闸

- 不适用；以 plugin validation 和 CI 接线取代。

## S7 · 验证

- 非仓库元任务在 `AGENTS.md` 与 binding 中显式跳过 Router/System Map。
- 局部仓库任务先 Router，再以 path/entity/flow 零跳查询；全局任务才加载 INDEX 与 4KB bootstrap。
- 代码派生计数通过 `python3.12 scripts/system_map_context.py --counts` 独立按需读取。
- 当前 `main` 相对 `origin/main` ahead 8 / behind 54，且共享工作树有其他 WIP；push 不满足安全前置条件。

## G6 · 验证闸(人在环)

- 待用户确认治理结果是否符合“更少触发、更少重复状态、平台适配清晰”的目标。

## S8 · 沉淀

- 已更新 System Map skill、INDEX、binding、治理合同/注册表、生成摘要与日志/性能/数据库/隐私分层文档。
- 待安全整合主干后再 commit/push；不以本地验证冒充远端交付。
