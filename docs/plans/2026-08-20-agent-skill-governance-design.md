# Reva Agent Skill 治理设计

**状态：** approved-for-implementation
**日期：** 2026-08-20
**范围：** 研发 agent skills；不改变 `backend/skills/*` 产品运行时技能

## 1. 问题

当前项目不缺 Skill，主要缺口是治理：

- Product Pipeline、Health Harness 与全局执行类 Skill 可能同时拥有计划、批次、checkpoint 和代理调度；
- Codex 通过项目 binding 直接读取 Claude Skill，repo-local Codex 插件又逐字复制 Claude 内容，导致 Claude 工具名、模型和署名泄入 Codex；
- Skill、插件、Tool/MCP/CLI、`AGENTS.md` 硬规则和模板没有统一分类与生命周期；
- 安装清单不能回答真实使用、任务完成、返工和质量收益。

## 2. 决策

### 2.1 一个主控制器

每个任务只能有一个 primary controller：

| 模式 | primary controller |
|---|---|
| `analysis` | 无，直接只读调查 |
| `quick_fix` | 无，单代理最小 TDD/验证 |
| `feature` | `product-pipeline` |
| `implementation` | `health-harness-orchestrator` |
| `incident` | `health-harness-orchestrator` + debugging capability |
| `release` | 恰好一个端侧 release skill |

`product-pipeline` 在 S5 委托 Health Harness 时仍拥有唯一父级 run；Health Harness 只能使用同一 run 的子 phase，不得另建竞争 ledger。

### 2.2 Overlay 不拥有流程

安全、数据库、通知隐私、doc drift 和 App Review 是 overlay。Overlay 可以阻断主流程，但不创建第二套计划、批次或完成状态。

### 2.3 三层供给与四态生命周期

- **平台标准层：** 硬策略和高复用能力；“默认支持”不等于“每次自动加载”。
- **任务工作流层：** 按任务模式选择的 controller、capability 和 terminal workflow。
- **创新孵化层：** 长尾或未验证技能。

生命周期固定为 `experimental → recommended → standard → deprecated`。`standard` 必须有 owner、版本、触发边界、证据、复审日期和维护承诺；低频安全技能不得仅因调用少而废弃。

### 2.4 Agent-neutral 合同与平台适配器

本设计与机器注册表是 agent-neutral 真源。Claude 和 Codex Skill 只做薄适配：

- Claude adapter 可使用 Claude 团队工具；
- Codex adapter 只使用 Codex collaboration/tool 语义；
- 测试验证路由、Gate、状态与安全语义等价，不再要求两个文件逐字相同。

### 2.5 最小可观测合同

本期不接数据库、不采集 prompt 或健康事实。汇总 Schema 记录任务模式、选择结果、Skill 版本、Gate、验证退出码、耗时、评审轮次、人工介入和闭集失败原因；前瞻轨迹只保存 opaque UUID4、闭集阶段、UTC 时间和 source / registry / route / evidence SHA-256，并以 append-only hash chain 提供链式完整性；只有把 head hash 锚定到外部 Dossier / evidence pack 后，才具备整链 tamper-evident 证据。后续 ROI 必须从任务结果出发，不能把安装数或调用数当成功。

已经完成的饮食修复仅是受新版 Router 污染的 transition observation，不作为随机或纯旧体系对照。下一条真实 Bug 在开工前注册为 `router_v1_prospective`；单样本只做描述，不宣称因果改善。

## 3. 机器资产

1. `docs/governance/agent-skill-registry.json`：canonical ID、分类、层级、生命周期、平台、owner、触发族、冲突、证据与路由表。
2. `docs/governance/agent-skill-run-event.schema.json`：隐私最小化事件 Schema。
3. `docs/governance/agent-skill-run-trace-event.schema.json`：append-only 前瞻轨迹 Schema。
4. `scripts/agent_skill_benchmark.py`：显式路径、hash-chain 的 `start` / `mark` / `report` 采集器。
5. `scripts/check_agent_skill_governance.py`：验证注册表、路由唯一性、文件存在性、适配器语义 digest 与事件合同。
6. `reva-workflow-router`：先路由、再加载最小充分 Skill 集合；delegate 延迟到所属父流程阶段。

## 4. 推荐 Skill 组合

基础组合保持最小：

- 项目现状：`system-map`
- 复杂度控制：`karpathy-guidelines`
- 实现纪律：风险校准后的 `test-driven-development`
- 故障：`systematic-debugging`
- 完成声明：`verification-before-completion`
- 主流程：仅 `product-pipeline` 或 `health-harness-orchestrator` 之一
- 评审：按风险 charter 选择 reviewer，使用固定 diff/evidence pack
- Overlay：只加载真实命中的 safety、DB、privacy、doc-drift 或 release 约束

`using-superpowers` 和 `executing-plans` 在本项目不作为可直接触发的 controller；如需其中能力，由 Router 显式映射，不能与项目 controller 叠加。

## 5. 验收

- 任一模式的机器推荐结果最多一个 primary controller；
- 所有 standard Skill 均有完整治理字段；
- Codex 插件不含 Claude-only 工具、模型或署名；
- project binding 先进入 Router，再读取被选中的 Skill；
- pre-commit、`scripts/validate.py` 与 CI 都阻断治理漂移；
- 不记录原始 prompt、健康文本、药名、诊断或凭据；
- Codex 插件可被官方 CLI 安装并在 fresh task 中发现，且只有 Router 可隐式触发；
- 下一条 Bug 可在开工前写入 `router_v1_prospective` 路由证据，报告不会从单样本宣称优越性；
- 现有产品运行时 skills、Health Day WIP 和部署行为保持不变。
