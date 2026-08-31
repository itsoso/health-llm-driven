# AGENTS.md — Reva / health-llm-driven 研发硬规则

> 本文件只保留高频、可裁决的约束。详细说明和示例放在 `docs/governance/`；研发 Skill 的机器真源是 `docs/governance/agent-skill-registry.json`，不要在这里复制 Skill 清单。

## 1. 固定启动顺序：Router first，System Map on demand

1. 先读本文件。
2. 仓库研发任务先运行 `reva-workflow-router`，选择一个 primary controller 与必要 overlay：

   ```bash
   python3.12 scripts/check_agent_skill_governance.py recommend --mode <analysis|quick_fix|feature|implementation|incident|release>
   ```

   `planning` and `verification` are workflow phases, not mode values.
   有安全、DB、文档漂移等明确风险时才附加对应 `--overlay`；Skill / plugin 治理分别声明 `--capability-trigger skill-governance` / `plugin-authoring`。不要机械叠加多个 controller；feature 的 Health Harness delegate 只在父流程进入 S5 后加载。
3. 启动只消费推荐结果的 `immediate_skills`，进入实际阶段后才加载 `deferred_by_phase[phase]`。`activation_skills` 是完整有序审计 union；`selected_skills` 保留 v1 非 delegate 选择，`deferred_skills` 只保留 delegate；三者都**禁止作为预载清单**。
4. **非仓库元任务**（例如 Codex 设置、执行速度、通用问答、个人工作流讨论）不运行 Router，也不加载 System Map。
5. `system-map` 只在任务实际命中系统现状、架构、跨端/跨组件关系、代码派生结构或漂移需求时，从 `deferred_by_phase.on_demand` 激活：
   - 已知路径或局部修改：直接用 `python3.12 scripts/system_map_context.py --path <path> --depth 0`；
   - 已知实体/流：用 `--entity` / `--flow` / `--keyword`，默认零跳，确有需要再增大 `--depth`；
   - onboarding、全局架构或跨域设计：先读 `docs/system-map/INDEX.md` 与 `docs/_generated/system-map-agent-context.md`，再做局部查询。
6. 打开查询结果指向的源码和邻近测试后，才能形成技术结论或实现计划。

地图不可用或验证失败时，运行 `./scripts/system-map-check.sh`，并直接回到代码、测试和注册表调查。`docs/_generated/system-map.json` 是 canonical graph；摘要与查询结果只是派生视图。

项目级绑定与跨 agent 规则见 `docs/agent-skill-binding.md`、`docs/governance/agent-skill-governance.md`。

## 2. 产品准入与完整生命周期

涉及产品定位、新用户行为、跨端职责、Health OS 对象、安全边界或验证闭环时，先按 `docs/specs/reva-product-governance-spec.md` 做需求准入；非平凡行为使用 `docs/specs/templates/feature-spec-template.md`。

用户要求“立项 / 走一遍流程 / 从需求到上线”时，遵循 `docs/specs/product-pipeline-contract.md`：

- 定义环：需求 → PRD → 规划；交付环：分解 → 实现 → 测试 → 部署 → 验证。
- G1–G6 任一 Gate 失败必须回上游，禁止带红或带安全 BLOCK 前进。
- 每个 feature 用 `docs/dossiers/<date>-<slug>.md` 记录状态、Gate 裁决、证据和断点；接手先读已有 Dossier。

## 3. 安全、隐私与数据隔离

完整规则见 `docs/governance/security.md` 与 `docs/governance/privacy.md`。硬规则：

- 禁止提交密钥、Token、密码、健康原始数据或可识别个人信息；日志与错误输出必须脱敏。
- 所有用户数据读写必须按认证用户/租户隔离；敏感操作要鉴权并保留审计证据。
- 不允许空 `try/except`、静默 fallback 或捕获后伪装成功；失败必须让调用方和验证 Gate 感知。
- 改用药、补剂、基因、化验、CGM、提醒、通知、认证、隐私、健康建议或写路径时，必须选择 `safety-gate` overlay。
- 锁屏可见推送不得出现药名、补剂名、化验项目名或诊断名；LLM 文案必须经过 `push_privacy.llm_push_backstop`，扫描异常时收紧到泛化文案，原文只留应用内安全载荷。
- 新增通知出口必须复用现有隐私 choke point，并提供“敏感词被泛化、良性文案不被误伤”的正反测试。

## 4. 测试、验证与数据库语义

完整规则见 `docs/governance/testing.md`、`docs/governance/database.md`。

- 修复或新增行为先写能失败的测试，再做最小实现；完成声明前运行与风险相称的新鲜验证。
- 跑测试绝不使用 `| tail`；如需管道必须 `set -o pipefail`，并检查真实退出码。
- 仅修改 agent-governance、System Map 或 doc-tooling 时，可运行 `uv run --isolated --with-requirements backend/requirements-dev.txt python scripts/run_tooling_pytests.py` 作为 supplemental fast lane；不得作为每个任务的默认入口。该入口跳过 coverage，且不替代常规项目测试、coverage 或 CI Gate。
- 部署或发布前必须运行项目 CI-mode 集成闸，并核对目标主干对应 revision 的真实 CI 状态；局部测试不能替代。
- 生产语义与新数据库行为必须用 PostgreSQL 验证；SQLite 只保留快速单元测试与迁移兼容性验证，不能证明约束、并发、JSONB、时区或方言行为。
- schema/迁移变化必须选择 `add-managed-migration` overlay，同步 ORM、API/客户端类型、迁移、回滚路径和 PostgreSQL 集成证据。
- 改接口契约要同步两侧类型并同批验证；不能只验证单端。

## 5. 日志与性能

完整规则见 `docs/governance/logging.md`、`docs/governance/performance.md`。

- 日志记录必要上下文、耗时和可操作错误，不记录秘密或完整健康载荷；异常堆栈仅在安全的调试面输出。
- 性能优化先建立同一批真实请求的基线与分段证据，再改变实现；明确目标、长尾阈值、质量底线、成本、停止/回退条件。
- 批量 I/O 使用受限并发；常用查询避免 N+1 并有可验证索引；缓存必须定义 key、TTL、一致性与失效策略。

## 6. System Map 与文档漂移

- 架构计数、规则数、路由数、roster 等会漂结构，只能由代码生成进 `docs/_generated/system-map.json`，绝不手写进叙事文档。
- 改了生成器覆盖的架构结构，运行生成器并提交生成物；本机统一以 `./scripts/system-map-check.sh` 验证。
- 查询默认 `--depth 0`；宽查询应缩小 selector，只有明确需要上下游时才提高 depth。输出超预算必须失败，禁止静默截断。
- 证据优先级：代码与测试 > 代码派生地图 > 受审声明 > 带 `last-reviewed` 的叙事。`partial` / `declaration` 命中要回源码验证。

## 7. Git、提交与发布边界

- 开工前检查分支、工作树和开放 PR；保留用户与其他 agent 的改动，只暂存本任务文件，禁止 `git add -A`。
- 默认直接在 `main` 工作，除非用户明确要求隔离分支/worktree；不得使用破坏性 reset/checkout 清理他人改动。
- 修改、验证、commit、push、merge、deploy、release 是不同动作。只在用户授权和对应 Gate 满足时执行；分支分叉、主干非绿或工作树来源不明时停止外部写入并报告。
- 提交消息使用 `<type>(<scope>): <subject>`；提交前检查秘密、依赖、安全、测试、权限、用户隔离、日志和文档。
- 部署从干净、已验证的目标 revision 进行，完整规则见 `docs/governance/deploy.md`；部署成功不等于上线验证完成。

## 8. Mobile / 桌面发布

- Mobile 纯 JS/TS/UI 且满足 OTA 边界时，使用 `scripts/mobile-ota.sh production "<message>"`。
- 需要可扫码安装的 iOS 包时，使用 `scripts/mobile-local-qr.sh`；除非用户明确指定，不走 TestFlight/EAS submit。
- 原生依赖、签名、权限或商店元数据变化不能冒充 OTA；必须走对应 release skill 与审核 Gate。
- 后端发布按根目录 `deploy.sh` 和 `docs/governance/deploy.md`；Mac 发布按注册表选中的 adapter。

## 9. 面向用户的数字精度

面向用户的卡片、表格、图表标签和叙事读数最多保留两位小数，四舍五入并去尾零。单一实现真源：

- `backend/app/utils/number_format.py::format_display_number`
- `backend/app/utils/number_format.py::format_card_numbers`

新展示面复用这两个 choke point；不得自行散落 `.1f` / `.2f`。该规则仅作用于展示层，数据库写入、草稿、安全阈值和原始读数不得降精度。

## 10. 规则冲突与完成标准

安全、隐私、测试、DB、部署等工程硬规则由本文件与 `docs/governance/*` 裁决；产品治理决定“该不该做”，Skill registry 决定“由哪个工作流做”。overlay 只能阻断或补充验证，不能另建计划、ledger 或完成状态。

完成必须同时满足：目标行为已实现；相关测试/检查真实通过；安全与数据边界有证据；必要文档和生成物同步；未把未知或计划冒充为已交付。
