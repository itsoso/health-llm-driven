# Dossier: Reva 研发 Agent Skill 治理

| 字段 | 值 |
|---|---|
| slug | `agent-skill-governance` |
| 创建日期 | 2026-08-20 |
| 当前阶段 | S5 实现 |
| 状态 | building |
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
- [x] 2026-08-20 measurement before next Bug
  - 触发:用户要求先完成 Skills 优化，再用新体系改 Bug，并判断速度和质量是否提高。
  - 旧基线:用安装数、调用数或一次主观体验判断提效；饮食修复已在执行中接触新版 Router，无法充当纯旧体系对照。
  - 新基线:提供显式日志、append-only hash chain 的前瞻采集器；饮食修复只做 transition observation，下一条真实 Bug 在开工前注册 `router_v1_prospective`；单样本不宣称因果改善。
  - 回退阶段:S2。
  - 需重跑 Gate:G3、G4、G6。
  - 用户确认:☑ 用户明确要求衡量新 Skills 的改 Bug 速度和质量。

## S0 · 用户需求(逐字)

> 基于以上讨论，形成本项目的最佳skills的推荐并进行治理

- 谁用 / 解决什么:让 Claude、Codex、Cursor 等研发 agent 以最小充分 Skill 集完成任务，避免触发风暴、平台指令泄漏和多套状态机。
- 范围:研发 agent skills、plugin adapters、机器注册表和仓库治理 Gate；不修改 `backend/skills/*` 产品运行时技能，不接生产 telemetry。

## S1 · Discovery(现状勘察)

- `docs/agent-skill-binding.md` 让 Codex 直接读取 `.claude/skills/*`。
- repo-local Codex plugin 0.1.0 逐字复制 Product Pipeline / Health Harness Claude adapter，包含 Claude-only 工具和模型指令。
- 一行测试修复的压力场景会触发多项重复流程；跨端提醒场景会出现至少三层编排控制器和两份 ledger。
- 旧版 `scripts/validate.py`、pre-commit 和 CI 不验证 Skill 分类、生命周期、平台边界或唯一 controller；本项将这些规则机械化。

## G1 · 准入裁决

- classification:internal engineering governance。
- smallest_end_to_end_slice:machine registry → deterministic recommendation → native adapters → blocking repository gates。
- non_goals:运行时健康 Skill、生产遥测、部署和健康建议行为。
- **裁决:PASS** —— 改善研发正确性与维护性，不新增用户健康行为或写路径。

## S2 · 设计合同

- 链接:`docs/plans/2026-08-20-agent-skill-governance-design.md`。
- 核心合同:一个 Router、每任务最多一个 controller、overlay 非 owning、deferred delegate、三层供给、四态生命周期、语义 digest、隐私最小事件与前瞻 trace schema。

## S3 · 规划

- 链接:`docs/plans/2026-08-20-agent-skill-governance-implementation.md`。
- 路径:契约测试 RED → 注册表/checker → Router/native adapters → local/CI gates → 插件真实安装/发现 → 下一 Bug 前瞻计量。

## G2 · 可行性 + 风险压测

- 评审方式:两个独立只读压力场景（quick fix 与跨端 feature）+ 源码/adapter 审计。
- 已焊入规划:controller 唯一性、overlay 去重、未知 overlay fail closed、Codex/Claude adapter 分离、事件 schema 禁原始 prompt/健康文本/凭据。
- **裁决:PASS** —— 最小实现仅为本地确定性文件和检查器，无数据库、网络或运行时副作用。

## S4 · 研发任务分解

- [x] T1 设计与实施计划。
- [x] T2 先写治理/插件/接线契约测试并取得预期 RED。
- [x] T3 实现机器注册表、检查器、Router、adapter 语义 digest 与 benchmark collector。
- [x] T4 接入 binding、plugin、validate、pre-commit、CI 和 system map。
- [ ] T5 前向压测、独立评审、提交与安全推送。

## S5 · 实现

- 当前分支:`codex/agent-skill-governance-20260820`，基于最新 `origin/main` 的独立干净 worktree；共享主工作树中的 Health Day / KBase / 环境文件 WIP 未被带入。
- 当前状态:registry/checker、Codex-native adapters、semantic digest、deferred delegate、隐私最小 benchmark collector 与 repository gates 已实现，正在做最终评审、提交、推送和插件安装发现验证。

## G3 · 测试闸

- 当前证据:治理/插件/benchmark/仓库接线 focused tests `65 passed`；checker self-check PASS；官方 plugin validator 与 3 个 Skill validator PASS；`scripts/validate.py -v` 的 blocking system-map、Dossier 与 Skill governance 全 PASS；目标 Ruff、py_compile、`git diff --check` PASS。
- `validate.py` 的 backend 全局 Ruff 是 report-only，仍报告仓库既有问题；本治理 diff 的目标 Ruff 为零错误。
- **裁决:PASS** —— 待提交后仍会从 committed state 重跑同一证据包，主干 CI 是推送后的独立真实性检查。

## G4 · 安全闸

- 触发:研发治理和最小事件 schema；不触发产品健康写路径。
- 当前防线:run/task 只接受 opaque UUID；trace 无 prompt/path/free reason/duration，证据只存 SHA-256；未知 route、未跟踪 source、adapter 漏 Gate/内容漂移均 fail closed。成功耗时只取目标 stage 的首次 PASS，失败或 BLOCK 不会伪装成更快完成。
- 独立复审:首轮发现 benchmark 会把首次失败事件计作完成时间，已按 fail→pass RED/GREEN 修复；fresh 复审确认无剩余 BLOCKER/HIGH。
- **裁决:PASS**。

## S6 · 部署

- 无生产部署；交付为仓库内插件、文档、检查器和 CI Gate。

## G5 · 部署健康闸

- 不适用；以 plugin validation 和 CI 接线取代。

## S7 · 验证

- 已验证 Router 静态输出:quick-fix 无 controller；feature 仅 Product Pipeline 一个 controller，Health Harness 留在 `deferred_skills`；Skill/plugin 治理只增加对应 authoring capabilities。
- 待提交后用官方 CLI 安装 repo marketplace/plugin，并在 fresh Codex 进程核对三项 Skill 的发现与仅 Router implicit 边界。

### Transition observation（不作为纯旧体系对照）

- 饮食修复从任务启动到根因:3m54s；首次 RED:backend 20m25s / mobile 21m52s；初始跨端 GREEN:27m53s。
- 首次 NO-GO:38m48s；两类 reviewer 最终 GO:约 1h25m；推送 main:1h32m；CI 全绿:1h56m；技术交付:2h30m。
- 质量/返工:首次评审至少发现 1 个 BLOCKER 和 4 类 HIGH；经历 1 次 NO-GO→GO、1 次 CI rerun、1 次 backend pre-mutation retry，OTA 第 3 次成功；真实用户 G6 仍待验证。
- 解释边界:该 run 已使用新 Router recommendation，以上只作为 transition observation。下一 Bug 必须在根因调查前启动 `router_v1_prospective` trace；单个新样本只报告描述性 delta，不宣称因果提升。

## G6 · 验证闸(人在环)

- 待用户确认治理结果是否符合“更少触发、更少重复状态、平台适配清晰”的目标。

## S8 · 沉淀

- 待更新 system-map 生成物、治理证据和最终状态。
