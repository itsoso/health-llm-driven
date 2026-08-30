---
doc: agent-skill-binding
last-reviewed: 2026-08-29
scope: health-llm-driven
---

# Agent Skill Binding — health-llm-driven 项目级研发入口

> 本文是本仓库自己的 binding。全局层(`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` / `~/work/personal/PRACTICES/`)只管跨项目共性;这里管 Reva / health-llm-driven 内部研发时,Claude、Codex、Cursor 和其他 coding agent 如何共同触发本仓库的研发 skills、系统地图、产品流水线和验证闸门。

## 先分清四类 skill

| 类别 | 位置 | 谁用 | 用途 |
|---|---|---|---|
| **治理真源** | `docs/governance/agent-skill-registry.json`、`docs/governance/agent-skill-governance.md` | 所有研发 agent | Skill 分类、生命周期、Router、唯一 controller 与 overlay 规则 |
| **Claude 研发 adapter** | `.claude/skills/*/SKILL.md` | Claude Code | 用 Claude 能力执行同一 agent-neutral 合同 |
| **Codex 研发 adapter** | `plugins/reva-health-harness/skills/*/SKILL.md` | Codex | 用 Codex 能力执行同一 agent-neutral 合同 |
| **产品运行时 skill** | `backend/skills/*/SKILL.md` | Reva 后端第一方 Agent | 登录态用户的健康查询、记录、分析等产品能力 |

**不要混用**:研发 adapter 管“怎么改这个仓库”;产品运行时 skill 管“用户/外部 agent 怎么使用健康能力”。Claude/Codex adapter 不互相逐字复制；它们必须共同服从治理真源。

## 所有 agent 的固定启动顺序

1. 读 `AGENTS.md`:安全、日志、测试、隐私、DB、提交、部署硬规则的最终裁判。
2. 先判断是否为仓库研发任务。Codex 设置/性能、通用问答等**非仓库元任务**到此停止，不运行 Router，也不加载 System Map。
3. 仓库研发任务运行 `python3.12 scripts/check_agent_skill_governance.py recommend --mode <mode>`，由 `reva-workflow-router` 选择最小充分 Skill 集；不得把多个 controller 机械叠加。
4. 按平台读取 Router 选中的 adapter：Claude 读 `.claude/skills/<name>/SKILL.md`，Codex 读 `plugins/reva-health-harness/skills/<name>/SKILL.md`；未封装的平台能力才按注册表 source 读取。
5. 只有 Router 选中 `system-map` 或任务明确需要全局架构/跨组件/代码派生结构时才加载地图：
   - 已知 path/entity/flow 的局部任务直接运行 `python3.12 scripts/system_map_context.py ... --depth 0`；
   - onboarding、全局架构或跨域设计先读 `docs/system-map/INDEX.md` 与 `docs/_generated/system-map-agent-context.md`，再局部查询。
6. 打开查询结果给出的源码与附近测试后，再形成技术结论或实现计划。
7. 如果是产品/用户行为/跨端能力,继续读 `docs/specs/reva-product-governance-spec.md` 和 `docs/specs/product-pipeline-contract.md`。
8. 如果进入完整需求生命周期,创建或接续 `docs/dossiers/<date>-<slug>.md`,按 6 道 Gate 留痕。
9. 完成后按对应 skill 的 S8/沉淀规则更新 system map、PRD/Plan、doc drift 生成物或相关 agent 约束。

轻量摘要与局部查询均为 `docs/_generated/system-map.json` 的派生视图；管理员在产品内通过 `/admin/system-map` 看同一 canonical graph,研发 agent 直接读仓库生成物。CI 只能验证生成物和入口接线,不能证明模型已阅读。

Router 的机器推荐是入口，不是第二套状态机。`product-pipeline`、`health-harness-orchestrator` 与 release skill 同一任务最多选一个 primary controller；safety、DB、通知隐私、doc drift 和 App Review 只作为可阻断 overlay，不拥有独立计划或 ledger。

## Binding 表

| 触发场景 | 必读研发 skill / 协议 | 后续权威文档 |
|---|---|---|
| 任一仓库研发任务的 Skill 选择 | `reva-workflow-router` + `scripts/check_agent_skill_governance.py recommend` | `docs/governance/agent-skill-registry.json`, `docs/governance/agent-skill-governance.md` |
| Onboard 本项目、问“系统是什么/有哪些能力/架构/产品地图/当前现状” | `system-map` | `docs/system-map/INDEX.md`, `docs/_generated/system-map-agent-context.md`, `docs/system-map/product-map.md`, `docs/_generated/system-map.json` |
| 一句需求要走“需求→PRD→规划→研发→测试→部署→上线验证” | `product-pipeline`（由 Router 选择平台 adapter） | `docs/specs/product-pipeline-contract.md`, `docs/specs/reva-product-governance-spec.md`, `docs/dossiers/` |
| 需求已定,进入跨端实现或多 agent fan-out | `health-harness-orchestrator`（由 Router 选择平台 adapter） | `docs/design-agent-operating-harness.md`,对应 plan/spec |
| 改用药、补剂、基因、化验、CGM、提醒/通知、安全规则、认证、隐私、写路径或对外健康建议 | `safety-gate` overlay | `AGENTS.md`, `docs/governance/security.md`, `docs/specs/reva-product-governance-spec.md` |
| 新增/修改 DB schema 或迁移 | `add-managed-migration` overlay | `AGENTS.md §9`, backend migrations, schema/type generation rules |
| 新增 Safety 规则、specialist、agent 分区或相关注册表 | `.claude/skills/extend-safety-or-specialist/SKILL.md` | `scripts/check_doc_drift.py`, `docs/ARCHITECTURE.md`, `docs/_generated/system-map.json` |
| CI/System Map/doc drift 红,或代码派生系统事实变化 | `.claude/skills/doc-drift-fix/SKILL.md` + `.claude/skills/system-map/SKILL.md` | `scripts/dump_system_map.py`, `./scripts/system-map-check.sh`, `docs/system-map/INDEX.md` |
| 后端上线 | `.claude/skills/backend-deploy/SKILL.md` | `deploy.sh`, `docs/governance/deploy.md` |
| Mobile JS/TS/UI 线上热更新 | `.claude/skills/mobile-ota/SKILL.md` | `scripts/mobile-ota.sh`, mobile release notes |
| Mobile native / EAS / TestFlight 发版 | `.claude/skills/mobile-testflight-release/SKILL.md` | EAS profiles, iOS signing, user confirmation gates |
| iOS App Store 送审 / 审核被拒 / Review Notes / 截图隐私 / 审核账号可达性 | `.claude/skills/ios-app-review-gate/SKILL.md` | `docs/release/app-store/submission-pack.md`, `docs/release/app-store/adapted-review-checklist.md`, `scripts/check_app_store_release_pack.py` |
| Mac app 构建/安装/分发 | `.claude/skills/mac-build-deploy/SKILL.md` | `apps/mac/`, packaging scripts |
| 阿里云百炼 TokenPlan 模型清单更新、每三天巡检、避免低版本模型、同步小巴模型下拉 | Codex 全局 skill `updating-tokenplan-models` (`~/.codex/skills/updating-tokenplan-models/SKILL.md`) | `backend/app/services/llm/model_registry.py`, `backend/tests/test_model_registry_latest.py`, `mobile/services/llmModelCatalog.ts` |

## Claude 与 Codex 的分工绑定

| Agent | 入口 | 约束 |
|---|---|---|
| Claude Code | `CLAUDE.md` → 本文 → `.claude/skills/*` | 可以使用 `.claude/agents/` 团队和 skill 自动编排,但仍受 `AGENTS.md` 硬规则裁判 |
| Codex | `AGENTS.md` → 本文 → Codex Router adapter → 被选中的 Codex adapter | 不读取 Claude-only 编排指令；用 Codex collaboration、shell、git、测试与验证能力满足同一套 agent-neutral Gate |
| Cursor | `.cursor/rules/00-agents-bootstrap.mdc` → `AGENTS.md` → 本文 | 先遵守 AGENTS 硬规则,再按 binding 读项目 skill |
| 其他模型/agent | `docs/specs/reva-product-governance-spec.md` → 本文 → `docs/specs/product-pipeline-contract.md` | 不允许绕过 G1/G2/G3/G4/G5/G6 |

## 最小执行标准

- 小修可以降级产品流程；读 `AGENTS.md`、先经 Router，再按已知 path/entity 做零跳局部查询。只有全局任务才读 System Map INDEX 与轻量摘要。
- 每个任务最多一个 primary controller；capability 与 overlay 不得创建竞争的 checkpoint、批次、ledger 或完成状态。
- 非平凡产品行为必须进入 product governance 和 product pipeline,至少留下 Dossier 或明确引用已有 Dossier。
- 任何带用户健康建议、写入、提醒、药物、疾病、基因、化验、CGM 的改动必须触发安全 Gate。
- 任何会漂的结构数字必须进 `docs/_generated/system-map.json`,不得手写进叙事文档；本机统一用 `./scripts/system-map-check.sh`（独立 Python 3.12 `.venv`）验证。
- 完成后提交前必须有新鲜验证证据;不要用 `| tail` 吞测试退出码。
