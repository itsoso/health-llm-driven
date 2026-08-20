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
- [ ] T3 实现机器注册表、检查器和 Router。
- [ ] T4 接入 binding、plugin、validate、pre-commit、CI 和 system map。
- [ ] T5 前向压测、独立评审、提交与安全推送。

## S5 · 实现

- 当前分支:`main`；仅精确暂存本 Dossier 列出的治理文件，保留共享工作树中的 Health Day / KBase WIP。
- 当前状态:并行实现 registry/checker 与 Codex-native plugin adapters；主代理负责 binding 和 repository gates。

## G3 · 测试闸

- 待完成:focused pytest、checker self-check、Skill validation、`scripts/validate.py -v`、system-map、`git diff --check`。

## G4 · 安全闸

- 触发:研发治理和最小事件 schema；不触发产品健康写路径。
- 待完成:独立 diff review，重点检查 prompt/健康事实/凭据不进入事件 schema，未知 route fail closed。

## S6 · 部署

- 无生产部署；交付为仓库内插件、文档、检查器和 CI Gate。

## G5 · 部署健康闸

- 不适用；以 plugin validation 和 CI 接线取代。

## S7 · 验证

- 待用原 quick-fix/cross-end 场景前向验证 Router 输出，并核对 `codex plugin list` 安装状态边界。

## G6 · 验证闸(人在环)

- 待用户确认治理结果是否符合“更少触发、更少重复状态、平台适配清晰”的目标。

## S8 · 沉淀

- 待更新 system-map 生成物、治理证据和最终状态。
