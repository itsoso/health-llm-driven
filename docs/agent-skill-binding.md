---
doc: agent-skill-binding
last-reviewed: 2026-08-12
scope: health-llm-driven
---

# Agent Skill Binding — health-llm-driven 项目级研发入口

> 本文是本仓库自己的 binding。全局层(`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` / `~/work/personal/PRACTICES/`)只管跨项目共性;这里管 Reva / health-llm-driven 内部研发时,Claude、Codex、Cursor 和其他 coding agent 如何共同触发本仓库的研发 skills、系统地图、产品流水线和验证闸门。

## 先分清三类 skill

| 类别 | 位置 | 谁用 | 用途 |
|---|---|---|---|
| **研发 agent skill** | `.claude/skills/*/SKILL.md` | Claude Code 自动发现;Codex/Cursor/其他 agent 直接读同一文件作为项目协议 | 研发导航、产品流水线、部署、OTA、安全评审、doc drift 修复 |
| **产品运行时 skill** | `backend/skills/*/SKILL.md` | Reva 后端第一方 Agent | 登录态用户的健康查询、记录、分析等产品能力 |

**不要混用**:研发 agent skill 管“怎么改这个仓库”;产品运行时 skill 管“用户/外部 agent 怎么使用健康能力”。

## 所有 agent 的固定启动顺序

1. 读 `AGENTS.md`:安全、日志、测试、隐私、DB、提交、部署硬规则的最终裁判。
2. 读 `docs/system-map/INDEX.md`:先知道系统目标、能力、架构、多端 surface、业务流和系统流。
3. 读 `docs/_generated/system-map-agent-context.md`:加载从 canonical graph 生成的轻量全局上下文。
4. 用 `python3.12 scripts/system_map_context.py` 按任务查询局部实体、关系、流、覆盖度和 source path,再打开源码与测试验证。
5. 按本文的 binding 表选择匹配的 `.claude/skills/<name>/SKILL.md`,并完整读完。
6. 如果是产品/用户行为/跨端能力,继续读 `docs/specs/reva-product-governance-spec.md` 和 `docs/specs/product-pipeline-contract.md`。
7. 如果进入完整需求生命周期,创建或接续 `docs/dossiers/<date>-<slug>.md`,按 6 道 Gate 留痕。
8. 完成后按对应 skill 的 S8/沉淀规则更新 system map、PRD/Plan、doc drift 生成物或相关 agent 约束。

轻量摘要与局部查询均为 `docs/_generated/system-map.json` 的派生视图；管理员在产品内通过 `/admin/system-map` 看同一 canonical graph,研发 agent 直接读仓库生成物。CI 只能验证生成物和入口接线,不能证明模型已阅读。

Codex 如果全局 openskills 已提供同名 skill,可以用 `npx openskills read <skill-name>`;否则直接读取本仓库 `.claude/skills/<name>/SKILL.md`。在 health-llm-driven 内,本仓库文件优先于全局泛化经验。

## Binding 表

| 触发场景 | 必读研发 skill / 协议 | 后续权威文档 |
|---|---|---|
| Onboard 本项目、问“系统是什么/有哪些能力/架构/产品地图/当前现状” | `.claude/skills/system-map/SKILL.md` | `docs/system-map/INDEX.md`, `docs/_generated/system-map-agent-context.md`, `docs/system-map/product-map.md`, `docs/_generated/system-map.json` |
| 一句需求要走“需求→PRD→规划→研发→测试→部署→上线验证” | `.claude/skills/product-pipeline/SKILL.md` | `docs/specs/product-pipeline-contract.md`, `docs/specs/reva-product-governance-spec.md`, `docs/dossiers/` |
| 需求已定,进入跨端实现或多 agent fan-out | `.claude/skills/health-harness-orchestrator/SKILL.md` | `CLAUDE.md` “代理团队 Harness”,对应 plan/spec |
| 改用药、基因、化验、CGM、消息、安全规则、认证、写路径或对外健康建议 | `.claude/skills/safety-gate/SKILL.md` | `AGENTS.md`, `docs/governance/security.md`, `docs/specs/reva-product-governance-spec.md` |
| 新增/修改 DB schema 或迁移 | `.claude/skills/add-managed-migration/SKILL.md` | `AGENTS.md §9`, backend migrations, schema/type generation rules |
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
| Codex | `AGENTS.md` → 本文 → 直接读 `.claude/skills/*` 或全局 openskills 同名 skill | 不假设 Claude 工具存在;用自己的 shell、git、测试、验证工具满足同一套 Gate |
| Cursor | `.cursor/rules/00-agents-bootstrap.mdc` → `AGENTS.md` → 本文 | 先遵守 AGENTS 硬规则,再按 binding 读项目 skill |
| 其他模型/agent | `docs/specs/reva-product-governance-spec.md` → 本文 → `docs/specs/product-pipeline-contract.md` | 不允许绕过 G1/G2/G3/G4/G5/G6 |

## 最小执行标准

- 小修可以降级产品流程,但仍要读 `AGENTS.md`、System Map INDEX 与轻量全局摘要,再定位局部代码并跑相关验证。
- 非平凡产品行为必须进入 product governance 和 product pipeline,至少留下 Dossier 或明确引用已有 Dossier。
- 任何带用户健康建议、写入、提醒、药物、疾病、基因、化验、CGM 的改动必须触发安全 Gate。
- 任何会漂的结构数字必须进 `docs/_generated/system-map.json`,不得手写进叙事文档；本机统一用 `./scripts/system-map-check.sh`（独立 Python 3.12 `.venv`）验证。
- 完成后提交前必须有新鲜验证证据;不要用 `| tail` 吞测试退出码。
