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
| 后端/前端上线请求（自动 remote release 与联网 observation 均冻结） | `.claude/skills/backend-deploy/SKILL.md` | offline evidence/public unauthenticated HTTPS only；`docs/governance/deploy.md` |
| Mobile JS/TS/UI OTA 请求（所有 channel writer 冻结） | `.claude/skills/mobile-ota/SKILL.md` | 本地 Metro/exact-UDID Simulator/test；existing-IPA offline inspection |
| Mobile native / EAS / TestFlight 请求（所有 production/ASC writer/observation 冻结） | `.claude/skills/mobile-testflight-release/SKILL.md` | 已有本地 candidate/IPA 材料；禁止 network query/build/sign/physical-device acceptance |
| iOS App Store 送审 / 审核被拒 / Review Notes / 截图隐私 / 审核账号可达性 | `.claude/skills/ios-app-review-gate/SKILL.md` | non-final-submit 静态 release-pack；reviewer login/reset/ASC observation/mutation/submission 均 BLOCK |
| Mac app 构建/安装/分发 | `.claude/skills/mac-build-deploy/SKILL.md` | 本地 compile/test；`release-dmg.sh` 整体 BLOCK；独立 isolated test fixture 与 local create-candidate only |
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

## 2026-08-12 production release freeze（覆盖所有 release binding）

同 UID writable repo 不能闭合 bootstrap trust：Git replace、shared
`.git/info/attributes` + clean/smudge filter、被 `.git/info/exclude` 隐藏的 untracked
import shadow、`BASH_ENV`、`PYTHONPATH`/`sitecustomize` 均已复现。故 server
backend/frontend/env/restart/push/evidence/App Review reset/coordinator、Mobile **所有 channel**
OTA/rollback 与 production native/EAS/ASC、Mac route/publish/recover/rollback 及所有自动
release 旁路均 exit 78。人工 release Gate 是 STOP/BLOCK，不能转 raw SSH 发布、供应商 CLI
或 release helper。server-local DB migration/setup/admin utility 只属独立 manual admin
Gate，不得被自动 release 入口调用。

repo rc78 只作 ordinary-invocation tombstone：Bash caller 可经 `BASH_ENV` 覆盖
`exit`/`builtin` function。`deploy.sh`/`_run-mobile-tf.sh` legacy 必须 literal-false、语法级
不可达，runtime/operator 不得 source/extract/eval；隔离测试 marker extraction 仅作无
writer/网络的协议 fixture，不构成 proof。`release-dmg.sh` 整体冻结，read-only checker 必须独立且
不含 writer code。

EAS channel→branch 映射可能漂移或共用，不能证明 preview/development 不触达 production。
`release.py`/`release.sh` plan/validate/publish、`release_production_state` 的联网模式、
`deploy.sh` status/logs/inspect 均 earliest exit 78。当前只允许 offline evidence parser、
公开未认证 HTTPS、本地 Metro/iOS Simulator/test，以及
`scripts/mobile-local-qr.sh --no-upload --ipa <EXISTING_IPA>` 读取现成 IPA 并生成离线检视
metadata/report（无安装 manifest、安装二维码或可安装承诺）。`npm run ios`
固定走 Simulator wrapper，不得向 npm/Expo 追加 `--device`；wrapper 从 available inventory
锁定 exact Simulator UDID。物理 iOS repo CLI、连接/安装/验收冻结。bare `--no-upload`、自动 archive/export/signing/provisioning、
`mobile-fast-device.sh`、`mobile-local-device.sh` 与 `-allowProvisioningUpdates` 均冻结。解冻需新 dossier、
repo-external root-owned launcher、固定解释器、`env -i` allowlist、canonical archive/tree
仓库外 materialization 和独立 G4。此前 G5/G6/App Store submission 均 BLOCK，不得标
`shipped`/`complete`。

Android 尚不是 shipped/audited Mobile surface；`npm run android`/`expo run:android` 会进入
native generation、debug signing 与 ADB install，故 repo entry 必须 earliest `exit 78`，
冻结期无 Android native CLI 例外。

Mac/nginx direct Python production CLI 与 wrapper 同样冻结。`release-dmg.sh` 整体不可运行；
独立 test-only protocol fixture 必须同时满足
strict non-root、explicit test mode 与固定 non-production roots（macOS `/private/tmp` 或
`/private/var/folders`；其他平台 `/tmp`，忽略 caller `TMPDIR`）；本地 `create-candidate`
也须满足相同隔离条件，仅生成元数据，不签名、不联网、不发布。`deploy.sh
--inspect-release-lock` 也须在读取 lock/env 前 exit 78；应用层脱敏不能防止
`SHELLOPTS=xtrace`/`BASH_ENV` 在 repo guard 前捕获变量，锁状态须等待 repo-external
root-owned inspector。

`check_app_store_release_pack.py --final-submit` 会登录 production reviewer 并取得可写
bearer token，必须冻结；只保留不带 `--final-submit` 的静态 pack 与纯静态 iOS config
check，且不得形成 G5/G6 或 submission 授权。
