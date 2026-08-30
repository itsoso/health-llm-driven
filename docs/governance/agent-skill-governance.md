# Reva 研发 Agent Skill 治理合同

**状态：** active

**版本：** 2.0

**最后复审：** 2026-08-30

**机器真源：** `docs/governance/agent-skill-registry.json`

## 1. 范围与目标

本合同治理在 `health-llm-driven` 内工作的研发 Agent Skill，包括项目 Skill、平台 Skill 的项目级推荐，以及 Claude/Codex 适配器。`backend/skills/*` 是产品运行时能力，不属于本合同，不能被注册成研发工作流。

Router 的适用边界是**仓库研发任务**。Codex 配置、执行速度、通用知识问答等非仓库元任务不进入本路由，也不加载 System Map。仓库任务先路由、后按选择加载能力；System Map 采用已知路径零跳查询优先，全局摘要只用于 onboarding、架构与跨域任务。

治理目标只有四个：

1. 每个任务至多一个主控制器，避免重复计划、重复 ledger 和互相矛盾的完成状态。
2. 只加载完成任务所需的最小 Skill 集合，简单修复不被完整产品流程放大。
3. Agent-neutral 合同与平台执行细节分离，Claude 指令不能泄漏进 Codex 适配器。
4. 用任务结果、返工和 Gate 证据评估 Skill；不把安装数、调用数或“用了很多 Agent”当成功。

优先级为：`AGENTS.md` 与 `docs/governance/*` 工程硬规则 > 本合同及机器注册表 > 平台适配器。适配器只能落实合同，不能放宽安全、隐私、测试或发布 Gate。

## 2. 核心模型

### 2.1 五种角色

| 角色 | 职责 | 是否拥有任务状态 |
|---|---|---|
| Router | 识别模式并给出确定性最小路由 | 只拥有选择结果，不拥有交付状态 |
| Controller | 拥有计划、checkpoint、父 run 和最终完成状态 | 是；每个任务至多一个 |
| Capability | 提供系统理解、TDD、调试或验证纪律 | 否 |
| Overlay | 对安全、DB、隐私、文档漂移等风险做阻断检查 | 否 |
| Terminal | 执行一个明确目标的部署或发布路径 | 仅在 `release` 模式作为唯一主执行者 |

Overlay 可以返回 BLOCK，但不能再创建计划、批次、父 run 或“第二个完成”。`product-pipeline` 在 S5 委托 `health-harness-orchestrator` 时仍拥有父 run；后者只能作为同一 run 的交付子阶段。

### 2.2 三层供给

- **platform：** 高复用基础能力与硬纪律。Standard 表示受支持，不表示每轮对话都自动加载。
- **workflow：** Router、Controller、Overlay 和 Terminal，根据任务模式与风险选择。
- **incubator：** 长尾或尚未完成证据闭环的能力，不得自动进入主路由。

### 2.3 四态生命周期

生命周期只能为 `experimental → recommended → standard → deprecated`。

| 状态 | 准入与使用规则 |
|---|---|
| experimental | 有 owner、版本、清晰触发边界和测试计划；仅显式试用，不进默认路由 |
| recommended | 已通过代表性场景验证，无未解决的主控制器冲突；Router 可在限定模式选择 |
| standard | 有 owner、版本、平台、触发族、证据、来源、复审日期及阻断测试；项目承诺维护 |
| deprecated | 有原因和替代路径；不得直接充当 Controller，清除引用后再删除 |

安全 Skill 不因调用频率低而降级。发生安全事故或确定性冲突时，可以从任意状态紧急进入 `deprecated`；其他升级应逐级进行。版本采用 SemVer：合同或路由不兼容变更升 major，向后兼容能力升 minor，说明或缺陷修复升 patch。

注册表中的 `version` 是本项目对该 Skill 合同或外部推荐策略的治理版本，不冒充上游包版本。推荐器同时返回 ID、治理版本和角色，使隐私最小事件可以直接复用，不必再从自由文本推断。

## 3. 推荐的最佳 Skill 组合

### 3.1 默认基础能力

基础集合保持最小，并且都不是 Controller：

- `system-map`：按需定位当前系统、实体、流程和源文件；局部任务 query-first，全局任务才加载摘要；
- `karpathy-guidelines`：约束改动范围和复杂度；
- `test-driven-development`：行为变更与修复的风险校准 RED/GREEN；
- `systematic-debugging`：只在故障或原因不明时加载；
- `verification-before-completion`：所有完成声明的证据门。

“基础集合”表示项目认可这些能力，不表示每个模式全量加载。这里的 `analysis` 指仓库分析；非仓库元任务不进入 Router。`quick_fix` 不需要完整 Controller，`incident` 才强制加入系统调试能力。

### 3.2 两个主控制器

- `product-pipeline`：需求仍需定义，或用户要求从需求到上线完整闭环时使用；
- `health-harness-orchestrator`：需求已定，需要跨文件、跨端、对抗评审或实现到验证协同时使用。

不再允许全局 `using-superpowers` 或 `executing-plans` 在本项目直接取得控制权。它们没有被从全局环境删除；本项目只把其直接 Controller 身份标为 deprecated，需要的局部能力由 Router 显式选入。

### 3.3 其他平台 Skill 的位置

- `brainstorming`、`writing-plans`：仅作为 Product Pipeline 定义环内部能力，不另建控制流程；
- `dispatching-parallel-agents`、`subagent-driven-development`：是 Harness 的平台实现手段，不拥有项目 checkpoint；
- `requesting-code-review`、`receiving-code-review`：按风险和评审 charter 加载，不作为每个小修的固定税；
- React Native、Postgres、OTA 等技术 Skill：只有对应技术面真实命中时才加载，并服从项目 Overlay 与 Terminal；
- `skill-creator`、`writing-skills`、`plugin-creator`：只在 `skill-governance` / `plugin-authoring` capability trigger 命中时加载，不进入普通开发任务；
- 未被 Git 跟踪、未登记或只有本地草稿的 Skill 不进入机器注册表；孵化实验先在单独证据包中完成 owner、版本和测试，再申请登记。

### 3.4 当前治理裁决

| 裁决 | Skill | 使用方式 |
|---|---|---|
| standard | `reva-workflow-router`、`product-pipeline`、`health-harness-orchestrator`、`system-map`、`safety-gate`、`add-managed-migration`、`doc-drift-fix`、`mobile-ota` | Router 可在严格触发边界内选择；controller 仍遵守唯一性 |
| standard external capability | `karpathy-guidelines`、`test-driven-development`、`systematic-debugging`、`verification-before-completion` | 只增加纪律，不取得 controller 身份 |
| recommended | `backend-deploy`、`ios-app-review-gate`、`mobile-testflight-release`、`mac-build-deploy`、`extend-safety-or-specialist` | 可显式使用，但在配置抽取、产品身份或工具链 pin 硬化前不宣称平台标准 |
| deprecated as direct controller | `using-superpowers`、`executing-plans` | 不删除上游 Skill；本项目禁止其直接取得控制权 |

机器可执行状态以注册表为准。本表只解释裁决理由，不复制 owner、版本或完整路由字段。

## 4. 确定性路由

Router 不凭自由文本“顺手多加几个 Skill”。它先把任务归入一个 canonical mode，再调用检查器；模式和选项不接受别名，未知输入 fail-closed。

| mode | 主控制器 | 委托 | 关键能力 |
|---|---|---|---|
| `analysis` | 无 | 无 | system-map |
| `quick_fix` | 无 | 无 | system-map、最小改动、TDD、完成验证 |
| `feature` | product-pipeline | health-harness-orchestrator（S5 才按需加载） | 定义环、交付环与同一父 run |
| `implementation` | health-harness-orchestrator | 无 | 已定义需求的实现、评审和验证 |
| `incident` | health-harness-orchestrator | 无 | systematic-debugging、回归验证 |
| `release` | 一个目标对应的 Terminal | 无 | 发布前验证与目标端 Gate |

`planning` 与 `verification` 是工作流阶段，不是 Router mode；唯一 mode 词汇固定为 `analysis|quick_fix|feature|implementation|incident|release`。

Skill 激活阶段由注册表 `routing.activation_policy` 唯一裁决：Router、当前 controller/terminal、实际命中的 Overlay 与 authoring capability trigger 在 `immediate` 启动；incident 的 debugging 语义阶段为 `diagnosis`，但该模式将 diagnosis 设为 eager；System Map 为 `on_demand`；最小改动与 TDD 在 `implementation`；完成验证在 `verification`；feature delegate 只在 `S5` 激活。未知阶段或覆盖不完整由 checker fail-closed。

模式选择标准：

1. 只读理解、审计或报告为 `analysis`。
2. 范围明确、单点、无新产品行为且无需多方协调为 `quick_fix`。
3. 新用户行为、产品对象、跨端职责或需求仍需定义为 `feature`。
4. Spec/验收已定但实现非平凡为 `implementation`。
5. 线上故障、测试异常或根因未知为 `incident`。
6. 源码已完成，只需一个明确端的发布为 `release`。

不确定 `quick_fix` 还是 `feature` 时，优先检查是否引入新用户行为或安全边界；命中则升级为 `feature`。不确定 `implementation` 还是 `incident` 时，根因未知即为 `incident`。

## 5. Overlay 与发布目标

Overlay 触发映射：

| 触发 | Skill |
|---|---|
| `safety` | safety-gate |
| `notification-privacy` | safety-gate |
| `database` | add-managed-migration |
| `doc-drift` | doc-drift-fix |
| `app-review` | ios-app-review-gate |

多个触发映射到同一个 Overlay 时必须去重。例如同时命中 `safety` 与 `notification-privacy`，只运行一次 `safety-gate`，但评审范围覆盖两个原因。

`release` 必须且只能给一个目标：

| 目标 | Terminal |
|---|---|
| `backend` | backend-deploy |
| `mobile-ota` | mobile-ota |
| `mobile-testflight` | mobile-testflight-release |
| `mac` | mac-build-deploy |

App Store 审核是 `app-review` Overlay，不是第二个 Terminal。原生 iOS 发布可选择 `mobile-testflight` 并叠加 `app-review`。

## 6. 操作合同

先校验治理资产：

```bash
python3.12 scripts/check_agent_skill_governance.py check
```

获取一个任务的路由：

```bash
python3.12 scripts/check_agent_skill_governance.py recommend \
  --mode feature \
  --overlay safety \
  --overlay database \
  --overlay notification-privacy
```

发布路由示例：

```bash
python3.12 scripts/check_agent_skill_governance.py recommend \
  --mode release \
  --release-target mobile-ota
```

推荐输出是 `agent-skill-recommendation.v2` 机器合同：

- 启动时只加载 `immediate_skills`；进入实际阶段时才按注册表 `routing.activation_policy.phases` 的顺序加载 `deferred_by_phase[phase]`。这两个字段是唯一加载依据。
- `selected_skills` / `selected_skill_details` 保留 v1 的非 delegate 选择，即 Router、当前 controller/terminal、capability 与 Overlay；它们不包含 S5 delegate，也**不得驱动预载**。
- `deferred_skills` / `deferred_skill_details` 只保留 delegate 的 v1 兼容语义，也**不得驱动预载**。
- `activation_skills` / `activation_skill_details` 是 `immediate_skills` 加各 `deferred_by_phase` 的完整有序 union，只用于审计与确定性比较，不是预载清单。
- detail 都带合法 `activation_phase`；immediate 与 phase-deferred 集合不重叠，union 等于 `activation_skills`。v1 选择顺序固定为 Router → controller/terminal → 注册表 route capability → 按 ID 排序的 authoring capability → 按 ID 排序的 Overlay；delegate 保留 route 顺序。`activation_skills` 先按上述选择顺序收集 immediate/eager 项，再按注册表 phase 顺序和各 phase 内选择顺序追加；`deferred_by_phase` 不按 JSON key 字母重排。

`controller_count` 只能为 0 或 1。未知 mode、phase、Overlay、capability trigger 或发布目标，以及覆盖不全、角色冲突、adapter 漂移等输入均以非零退出码 fail-closed。

Skill / plugin 治理任务应额外声明 capability trigger：

```bash
python3.12 scripts/check_agent_skill_governance.py recommend \
  --mode analysis \
  --capability-trigger skill-governance \
  --capability-trigger plugin-authoring
```

`feature` 的 delegate 出现在 `deferred_by_phase.S5`、`activation_skills` 和 v1 `deferred_skills`，不进入 v1 `selected_skills`；它不会在定义环预载，也不会计作第二个 controller。Product Pipeline 进入 S5 后才在同一父 run 中显式加载该 delegate。

## 7. 平台适配器

机器注册表和本合同是 Agent-neutral 真源。平台 Skill 是薄适配器：

- Claude adapter 可以使用 Claude 的团队协作工具；
- Codex adapter 只能使用 Codex collaboration、tool 和 checkpoint 语义；
- 两端必须保留相同 mode、唯一 Controller、Gate、BLOCK、委托和失败语义；注册表用 required markers 与整文件 SHA-256 同时阻断删 Gate、漏 BLOCK 或未同步 digest 的 adapter 漂移；不兼容语义变更仍必须按 SemVer 规则升版并接受评审；
- Codex adapter 禁止出现 `TeamCreate`、`TaskCreate`、`SendMessage`、硬编码 Opus 或 Claude 署名；
- 平台适配器可以摘要稳定语义帮助人阅读，但机器检查器的路由输出始终是唯一裁决；
- Router 是 Codex 插件唯一允许隐式调用的 Skill，两个 Controller 必须由 Router 显式选择。

平台能力不可用时，适配器应保持合同语义并使用本平台等价工具；不能静默跳过 Gate 或把失败写成成功。

仍位于历史 `.claude/skills/` 目录、但注册表声明为 `agent-neutral` 的共享协议，不得包含 Claude/Codex 专属工具名、固定模型、署名或私有 memory 占位符；治理检查器会机械阻断这些泄漏。只有显式声明 `adapters` 的 Skill 才允许在对应平台文件中使用平台原生编排语义。

## 8. 可观测与隐私

`docs/governance/agent-skill-run-event.schema.json` 定义汇总事件；`docs/governance/agent-skill-run-trace-event.schema.json` 与 `scripts/agent_skill_benchmark.py` 定义前瞻、append-only 的阶段轨迹。两者只接受独立生成的 opaque UUID4 或受限 UUID，不允许把任务语义编码进 ID。轨迹只保存 source / registry / route / evidence 的 SHA-256，不保存路径或证据正文；每条事件有全局序号、前驱 hash 和 event hash，写入使用文件锁与 `fsync`。

严禁写入原始 prompt、任务正文、健康文本、药名、诊断、凭据、Secret 或 Token。`task_id` 必须是独立随机生成、不含语义的 opaque ID，不能直接使用工单号或把用户请求编码进 ID。事件 Schema 顶层和嵌套 Skill 对象都关闭额外字段。

`reason_code` 只能使用 Schema 内的闭集通用原因（如 `validation_failed`、`safety_blocked`、`manual_decision_required`），不得把药名、诊断、用户文字或任意自由文本编码进原因码。

采集器没有默认日志路径，也不写数据库；操作者必须显式传 `--log`。`router_v1_prospective` 在任何工作阶段前必须先记录已哈希的 route，失败或取消则可在无路线时 fail-closed 结束。报告中的时长只由采集器 UTC 时间戳推导，调用方不能上报 duration 或自由文本 reason。`evidence_sha256` 只能哈希已提交或具备足够熵的完整 evidence pack，禁止直接哈希低熵药名、诊断、健康短句或 prompt（字典攻击可反推）。若要把链称为 tamper-evident，必须把 `trace_head_sha256` 锚定到 JSONL 之外的 Dossier 或评审证据中；未外部锚定时只能称为链式完整性校验。

```bash
python3.12 scripts/agent_skill_benchmark.py start \
  --log <explicit-jsonl> \
  --arm router_v1_prospective \
  --task-mode <canonical-mode> \
  --source-sha256 <sha256-of-fixed-source-ref> \
  --registry-sha256 <sha256-of-registry>
```

每个 run 必须解析 G3、G4、G5、G6 并记录 `run_finished` 才具备比较资格；不同 arm 的 task-mode 分布必须完全匹配。

本项目把已经完成的饮食修复仅记作 `transition_v0_observational` 叙事基线：它在执行中已经接触新版 Router，不能作为纯旧体系对照，也不回填伪造的历史 trace。下一条真实 Bug 才从任务启动前注册为 `router_v1_prospective`。单个样本只能报告描述性差异，不能宣称因果提升；初步结论至少需要同风险层每组 5 个任务（建议 10 个），且技术完成耗时中位数改善至少 20%、G3/G4/G6 与逃逸缺陷不退化。

评估优先看：任务是否完成、Gate 一次通过率、返工轮次、恢复成功率、人工介入、端到端耗时和逃逸缺陷；调用次数仅用于容量分析。自动报告永远不选“赢家”，G6 未决、任一组缺样本或单样本时明确返回证据不足。

## 9. 变更与复审

新增或调整 Skill 时按以下顺序：

1. 先添加能证明路由、角色或安全边界的失败测试；
2. 更新本合同和机器注册表，声明 owner、版本、层级、角色、平台、触发族、证据、来源和复审日期；
3. 更新薄适配器，不复制 Agent-neutral 路由逻辑；
4. 运行治理检查、相关单测和项目验证 Gate；
5. 用固定 diff/evidence pack 做独立评审；
6. 只提交治理相关文件，避免带入共享工作树改动。

每季度或发生以下事件时提前复审：Controller 竞争、同一任务重复 ledger、错误路由造成安全/发布逃逸、平台工具契约变化、连续返工、来源文件失效。复审必须给出保留、升级、降级、合并或废弃的明确裁决；“调用少”不能单独成为废弃理由。

注册表覆盖 `.claude/skills/*/SKILL.md`。新增项目 Skill 而未登记、登记来源不存在、Standard 元数据缺失或出现第二个 Router 时，治理检查必须阻断提交。
