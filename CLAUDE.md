# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Doc map — read the right file

Claude Code 读本文件；Cursor 读 `.cursor/rules/00-agents-bootstrap.mdc` → `AGENTS.md`。两条路径下 `AGENTS.md` 都是安全/日志/测试/部署/隐私的最终裁判 —— **本文件不重述 `AGENTS.md` 的硬规范**，只在需要时指一下章节。

| 我要做的事 | 读这个 |
|---|---|
| **系统全景 / 这系统是什么 / 有哪些能力 / 多端×UI×流 / onboard 本项目** | **`docs/system-map/INDEX.md`(agent 开工先读这个)** |
| **本项目研发 skill binding / Claude-Codex 怎么共用研发 skills** | **`docs/agent-skill-binding.md`**（项目级 binding；全局 PRACTICES 不在此重写） |
| 把一句需求走完整流程（需求→PRD→规划→研发→测试→部署→上线验证） | `docs/specs/product-pipeline-contract.md`（双环 + 6 道 Gate + Dossier） |
| 项目结构 / 命令 / 架构总览 / Multi-Agent 系统 | 本文件 |
| 安全 / 日志 / 测试 / 隐私 / 部署 / DB / 提交规范的硬约束 | `AGENTS.md` |
| 产品范围 / 需求演进 / 一等对象准入 Gate / Claude-Codex-Qwen-GLM-Kimi-Gemini-Grok 通用遵循协议 | `docs/specs/reva-product-governance-spec.md` |
| LLM Harness 设计（source-aware fast path / verification before write / tool schema / memory 4-stage / streaming） | `docs/HARNESS.md` |
| 编码 agent 如何在本仓库导航 / 验证 / 沉淀经验（**操作工具架**,≠ 上面那条产品 HARNESS.md） | `docs/design-agent-operating-harness.md` |
| iOS / Expo 工作流通用经验（Metro / dev-client / EAS 异步双通道） | `~/work/personal/PRACTICES/mobile-expo-dev-workflow.md` |
| Expo local native module 手写规则 | `~/work/personal/PRACTICES/expo-local-module-podspec.md` |
| 改 Rokid CXR-L 集成（`mobile/modules/rokid-bridge/` · `rokid-health.tsx` · `apps/rokid-pushup-glasses/` · `backend/app/api/rokid.py`） | **先读结论**：`docs/plans/2026-06-24-rokid-codex-review-adjudication-conclusion.md`（终裁 + 修复顺序）+ `docs/plans/2026-06-24-rokid-sdk-doc-vs-code-architecture-review.md`（SDK×代码 F1-F5）；**再按需 grep SDK 原文**：`docs/vendor/rokid-cxr-l-sdk/`（CXR-L v1.0.3 官方知识库 32 篇，`README.md` 是索引——别整目录 `@`，会爆上下文） |
| 新功能起步（四问 + ASCII 数据流） | `~/work/personal/PRACTICES/feature-plan.md` |

**每个 coding task 的固定启动**:`AGENTS.md` → `docs/system-map/INDEX.md` → `docs/_generated/system-map-agent-context.md` → 用 `python3.12 scripts/system_map_context.py` 查询任务相关局部图谱 → 打开结果中的源码与测试再判断。摘要与查询结果都派生自 canonical `docs/_generated/system-map.json`,不能替代代码验证；若地图闸门失败,回到代码、测试和注册表调查。

> 移动端构建方向以本文件 §"移动端构建方向" 为准（RN/Expo;Capacitor 已停用,README 现已与此一致）。
>
> 涉及产品定位或新需求时，先读 `docs/specs/reva-product-governance-spec.md`。`AGENTS.md` 管工程硬规则；该 Spec 管产品范围、需求准入和跨模型遵循协议。
>
> **三个 "harness" 别混**：① `docs/HARNESS.md` 是**产品** LLM 方法论(健康 agent 怎么造);② `docs/design-agent-operating-harness.md` 是**编码 agent 操作工具架**(本文件 + `AGENTS.md` 就是它的入口);③ 下面这条 §"代理团队 Harness" 是 **Claude Code 开发代理团队**(`.claude/agents/` + `.claude/skills/`)。

## 代理团队 Harness（开发用 · 2026-06-04 引入）

本仓库已应用 [revfactory/harness](https://github.com/revfactory/harness) 元 skill,为开发任务生成了一套**代理团队**(`.claude/`)。

**触发**:在本仓库做跨端功能 / 修复 / 上线时(「加一个功能」「实现 X」「修 bug」「合并部署」「发 OTA / TestFlight」)→ 用 **`health-harness-orchestrator`** skill 组队;扩建/审计团队本身 → 用 **`harness`** skill(由 marketplace 插件 `harness@harness-marketplace` 提供,user scope,非仓库内 —— 若新克隆缺该 skill,`claude plugin install harness@harness-marketplace`)。

**团队**(均 `model: opus`,定义在 `.claude/agents/`):
- `backend-engineer` — `backend/` 实现(API/service/model/agents/twin/safety/迁移)
- `mobile-engineer` — `mobile/` 实现(屏/组件/hooks/services/主题)
- `mac-engineer` — `apps/mac/` 实现(Swift 6/SwiftUI;配 `mac-build-deploy` skill)
- `frontend-engineer` — `frontend/` 实现(Next.js 14 Web;注意页面冻结 Phase 0-4)
- `qa-verifier` — 跑闸门(pytest/doc-drift/tsc/jest/swift/前端 vitest+page-freeze)+ 跨界 shape 比对 + 真红/假红判别
- `safety-privacy-reviewer` — AGENTS.md 硬规范 + 医疗安全/隐私评审(高风险必经)
- `release-engineer` — deploy.sh / OTA / EAS TestFlight / mac 打包安装(先后端再 OTA)

**专用 skill**:`mac-build-deploy`(apps/mac 的 swift build/test 闸门 + package-app.sh 安装 + CI 工具链坑)。

**项目 binding**:Claude/Codex/Cursor/其他 coding agent 如何共同触发这些研发 skills,见 `docs/agent-skill-binding.md`。全局层只管跨项目共性;health-llm-driven 内以该 binding + `AGENTS.md` 硬规则为准。

**工作流**:计划 → 实现(后端‖移动‖mac‖前端 fan-out)→ 增量 QA → 安全评审 → PR/上线。详见 `.claude/skills/health-harness-orchestrator/SKILL.md`。单文件小修/纯文档可降级单代理。

**变更历史**:
- 2026-06-04 初次构建(5 agents + orchestrator skill)。
- 2026-06-04 加 `mac-engineer` agent + `mac-build-deploy` skill(覆盖 apps/mac 开发与分发)。
- 2026-06-04 加 `frontend-engineer` agent(覆盖 frontend/ Next.js Web,补齐 4 端)。
- 2026-06-04 删仓库内 vendored 的 `harness` 工厂副本,改由 marketplace 插件 `harness@harness-marketplace` 提供(消除撞名;定制团队 agents + orchestrator + mac-build-deploy 仍随仓库)。

harness 是演进系统,每次执行后把新坑沉淀回对应 agent 定义。

## Project Overview

AI-driven health management platform with a Next.js web frontend, FastAPI backend, an Expo React Native app for iPhone/iPad, a WeChat mini program, and a standalone MCP server. Integrates Garmin/Withings wearables, LLM-based health analysis, and a first-party health Agent.

## ⚠️ 移动端构建方向（2026-04-19 决定）

**iPhone / iPad 原生 App 只走 React Native (`mobile/`) 路线。**

- ✅ **`mobile/`** (Expo SDK 54 + React Native 0.81) — **唯一**的 iPhone/iPad 原生 App 实现
- ❌ **Capacitor 壳 (`frontend/ios/`)** — 已停用。`package.json` 的 `build:ios` / `sync:ios` / `open:ios` 仍在但不再维护，等待统一清理。不要用这些命令，也不要往 `frontend/ios/` 提交新代码
- ✅ **`frontend/`** (Next.js 14) — 继续作为 Web (PC 浏览器) 前端；iOS Safari 访问走 Web 版

**原因**：Capacitor 是 WebView 套壳，手势/滚动/键盘/动画有网页味，启动慢；RN 编译到真原生 UIView。

**新功能开发规则**：
- 涉及 iPhone/iPad 的功能：**先写 `mobile/` 的 RN 版本**；Web 版可以延后或不做
- 组件复用通过 `packages/shared/` 的纯 TypeScript 类型/工具；UI 组件 RN 和 Web 两套各自写
- 后端 API 保持同一套（`/api/v1/*`），不为客户端分叉
- `mobile/` 和 `frontend/` 的 feature parity 还在追赶中 — 若某个 Web 页面在 mobile/ 里没有对应的 RN 实现，优先补 RN 版本

## Monorepo Layout

Root is a **pnpm workspace** (`pnpm-workspace.yaml` → `packages/*`) **plus several non-workspace project roots**. Each root has its own dependencies installed with its own package manager.

| Path | Stack | Package manager | Purpose |
|------|-------|-----------------|---------|
| `backend/` | FastAPI + SQLAlchemy + Celery | `pip` + `venv/` | API server, agents, Twin, orchestrator |
| `frontend/` | Next.js 14 | `npm` | Web app (PC browsers) |
| `mobile/` | Expo SDK 54 + expo-router + React Native 0.81 | `npm` | **iPhone/iPad 唯一原生 App** |
| `packages/mini-program/` | WeChat mini program (uni-app) | `pnpm` (workspace) | `weixin` client |
| `packages/shared/` | TypeScript | `pnpm` (workspace) | Shared types/utilities |
| `mcp-server/` | Python | `pip` + `venv/` | Standalone MCP server |

## Local Dev Gotchas

These will burn you if you don't know them:

- **Do not run `pnpm install` inside `frontend/` or `mobile/`.** They are not workspace members; use `npm` in each. `pnpm install` must only run at the repo root (and only affects `packages/*`).
- **Mobile app URL**: `mobile/services/api.ts` reads `EXPO_PUBLIC_API_URL` (defaults to production). To point at a local backend, export it before `npm run start` — do not edit the file.
- **Local `pytest` needs two env vars.** Copy from `.env.example` or export:
  ```bash
  export SECRET_KEY=test-secret-key-32-chars-minimum!!
  export GARMIN_ENCRYPTION_KEY=mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=
  ```
  Production additionally requires `DEVICE_ENCRYPTION_KEY` (guarded in `app/config.py`). Tests don't need a real DB/Redis — `conftest.py` uses in-memory SQLite and Redis usage is lazy.
- **SQLite is only a test fixture.** Production, staging, and local dev all run PostgreSQL. The only place SQLite touches the app is `conftest.py` (in-memory, `StaticPool`). Do **not** point `DATABASE_URL` at a SQLite file for development — some code paths assume PostgreSQL features (`JSONB`, `TIMESTAMP WITH TIME ZONE`).
- **CI uses `DATABASE_URL=sqlite:///:memory:`** (historical artifact; see `test_smoke.py` note below). Don't copy that into local `.env`.

## Common Commands

### Backend (FastAPI + Python 3.12)

```bash
cd backend
source venv/bin/activate

uvicorn main:app --reload --host 0.0.0.0 --port 8000

pytest                                                # all tests
pytest tests/test_twin_builder.py -v                  # single file
pytest tests/test_users.py::test_create_user -v -s    # single test
pytest --cov=app --cov-report=term-missing            # coverage
```

### Celery (Async Tasks)

```bash
cd backend
source venv/bin/activate
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

Celery uses Redis as broker (`settings.redis_url`). Timezone is `Asia/Shanghai`. Scheduled tasks include daily health plans (6:00), morning summaries (7:30), plan reminders (8:00), trend pushes (8:30), evening insights (20:30), anomaly checks (23:00), weekly reports (Mon 9:00), data cleanup (3:00), and meal-monitoring raw-media purge (3:05). Full schedule in `backend/app/celery_app.py`.

### Frontend (Next.js 14 + TypeScript)

```bash
cd frontend
npm install
npm run dev      # Dev server at localhost:3000
npm run build    # Production build
npm run lint     # ESLint
npm run test     # Vitest
```

### Mobile (Expo React Native)

```bash
cd mobile
npm install
npm run start        # Expo dev server (Metro)
npm run ios          # expo run:ios (requires Xcode)
npm run android      # expo run:android
```

The Expo app uses `expo-router` (file-based routing under `mobile/app/`), `@tanstack/react-query` for data, and `expo-secure-store` for tokens. React 19.1 with New Architecture enabled.

- **App identity**: 显示名 "健康助理"（Home Screen / Siri / 通知），内部 bundle name 保留 "HealthPilot"；bundle ID `life.executor.health`，scheme `mobile`。
- **Architecture**: `services/` (API clients) → `hooks/` (React Query wrappers) → `components/` (domain-split UI) → `app/(tabs)/` (Home, AI Chat, Quick Record, Safety Alerts, Health Cards).
- **Native deps worth knowing**: `react-native-maps`, `@react-native-voice/voice`, `expo-haptics`, `expo-notifications`, `expo-local-authentication` (Face ID), `react-native-reanimated`, `expo-image-picker`, `react-native-markdown-display`.
- **API URL**: `services/api.ts` reads `EXPO_PUBLIC_API_URL` (defaults to `https://health.executor.life/api`). For local backend dev, export `EXPO_PUBLIC_API_URL=http://<your-lan-ip>:8000/api/v1` before `npm run start`.
- **API 契约类型(防静默漂移)**: `mobile/types/api.generated.ts` 由后端 OpenAPI 生成(`npm run generate-types`,镜像 frontend)。**改了后端 request/response schema 后必须重跑 `npm run generate-types` 并提交**,否则 mobile 手写类型与后端漂移会静默坏(历史教训:`sleep_hours` vs `total_sleep_minutes`、float→int 422)。已接护栏的出口:`services/appleHealth.ts` 的 `toApiRecord` 把 import payload 标注为生成 schema——后端改名/删字段 → 该处 tsc 直接红。新增 mobile→backend 写接口时,同样用 `components['schemas'][...]` 标注出口 payload。

#### iOS 反馈环：本地 Sim 默认，EAS / TestFlight 异步（2026-05-06 工作流）

**默认路径**：`cd mobile && npm run ios` → 本地 Xcode build → iOS Simulator 验证。EAS build 只用于 (a) 真机功能验证 (b) TestFlight / App Store 发版，且必须**异步执行**（提交后切回 backend，不等）。

**为什么**：本地 incremental build 30s–2min + Sim 热重载秒级；EAS production build 15–25 分钟 + 排队 + 装包，反馈环差 50–100 倍。Siri keychain bug 烧过 10+ 次 EAS build 才定位，本地 prebuild 几秒就能看到 `ios/Podfile.lock` 缺条目。

**判断该走哪条路**：

| 改动类型 | 走哪条 | 命令 |
|---|---|---|
| `.ts` / `.tsx` / `.js` / 样式 / 文案 / API 调用 / hooks | 本地 Sim | `npm run ios` |
| RN 组件、navigation、React Query、状态管理 | 本地 Sim | `npm run ios` |
| Dark mode、键盘行为、ScrollView、markdown 渲染 | 本地 Sim | `npm run ios` |
| 已上线的真机功能微调（push payload、Siri response 文案） | OTA | `./scripts/mobile-ota.sh production "msg"` |
| `app.json` plugins / `Info.plist` / Podfile / 新 native module | **必须** EAS build | 异步触发，**不要等** |
| Expo SDK 升级、`expo-*` 大版本 bump | **必须** EAS build | 异步 |
| Siri / AppShortcut / AppIntent（需真机 Apple ID） | 真机 dev build 或 TestFlight | 周末批量验 |
| APNs production token / App Group / Face ID / Camera | 真机 dev build 或 TestFlight | 周末批量验 |
| 发版 | EAS build production + submit | 异步 |

**禁止反模式**：
- ❌ 提交 → `eas build` → 等 20 分钟看 log → 改一行 → 再 `eas build` → 再等。任何超过 1 次的 EAS build 重跑都说明本地没复现就提了。
- ❌ JS 改动用 `eas build`。永远走 OTA。
- ❌ 同步等 EAS build。触发后立刻切别的活，build 完再回。

**OTA 命令**：

```bash
./scripts/mobile-ota.sh                        # production channel, commit msg as message
./scripts/mobile-ota.sh preview                # push to preview channel
./scripts/mobile-ota.sh production "fix …"     # with explicit message
```

- **OTA (`scripts/mobile-ota.sh` → `eas update`)** — push 改过的 `.ts/.tsx/.js`。设备 cold start 或 30s+ 后台时拉。只发 iOS bundle (`--platform ios`)，`react-native-maps` 会炸 web bundler，Android 也没在分发。
- **Channels**: `development` (dev client, iOS sim 允许), `preview` (内部分发), `production` (App Store, 自动 bump iOS build 号, `ascAppId=6763569720`)。见 `mobile/eas.json`。

**本地 build 失败排查路径**（比 EAS log grep 快 10 倍）：
1. `npx expo prebuild --platform ios --clean` 看是否报错
2. 看 `ios/Podfile.lock` 是否包含预期 module（手写 local module 必须有 podspec，否则静默 skip）
3. `open ios/*.xcworkspace` 用 Xcode 直接看红 error

#### Cross-platform asymmetries (know these before shipping Android)

- `modules/shared-keychain/` — custom native module for sharing the JWT with iOS app extensions (Siri / Widget). **iOS-only**; Android has no implementation. `index.ts` silently `noop`s on Android, so widget / extension features simply don't work there.
- `mobile-ota.sh` pushes iOS-only (see above).
- Before treating Android as shipped, audit both of these.

#### Feature parity status

`frontend/src/app/` has ~45 top-level route directories; `mobile/app/` has ~15 routes. **Mobile is not at feature parity with Web and is unlikely to reach it.** Use this rough map when deciding where a feature lives:

| Category | In mobile? | Strategy |
|---|---|---|
| Daily use (Home, AI Chat, Safety Alerts, Quick Record, Diet, Sleep, Goals, Workouts, Reminders, Notifications, Settings) | ✅ Yes | New features **must** land in RN first |
| Deep analytics (Digital Twin, Health Trends, Personal Outcome, Health Report, Longitudinal analysis) | ⚠️ Partial (`indicator-history`, `sleep-spo2-analysis`) | Add RN if it's a daily-driver metric; leave on Web otherwise |
| Admin / Ops / Content authoring (admin, skills, review, onboarding, register) | ❌ No | **Stay on Web** — don't port |
| Low-frequency references (medical-exams, supplement-audits, supplement-products, knowledge browsing, family, shared) | ❌ No | Evaluate per-user-request before adding |

When porting a Web page to RN, update this table in the same PR.

### Mini Program (WeChat)

```bash
cd packages/mini-program
npm install   # workspace member, but npm works here too
# See packages/mini-program/RELEASE.md for the WeChat DevTools build flow
```

### MCP Server

```bash
cd mcp-server
source venv/bin/activate
python server.py     # See mcp-server/README.md for tool list
```

### Deployment

```bash
./deploy.sh -f   # Frontend only (most common)
./deploy.sh -b   # Backend only (also syncs Skills, restarts Celery worker+beat, does DB backup)
./deploy.sh -a   # Both (same as no flags)
./deploy.sh -e   # Sync .env to server and restart
./deploy.sh -r   # Restart services without pulling code
./deploy.sh -p   # Push code to GitHub without deploying
./deploy.sh -s   # Check service status
./deploy.sh -l   # View logs
```

Backend deploy validates the first-party `backend/skills/*/SKILL.md` manifest. Post-deploy, `backend/scripts/system_health_score.py` runs — on failure, deploy auto-rollbacks.

### Database Migrations

No Alembic — migrations are manual SQL files in `backend/migrations/`:

```bash
psql $DATABASE_URL -f backend/migrations/create_xxx_tables.sql
```

## Architecture

### Multi-Agent Health System (核心架构)

```
用户对话框
    ↓
Orchestrator (L4)  ← 意图路由 + 专家调度 + LLM 合成
    ↓
13 Specialists (L3) ← 每个专家读 Twin、产出结构化 Finding
    ↓
Digital Health Twin (L2) ← 14 语义分区的统一状态视图 (Redis 5min 缓存)
    ↓
Collectors + Services (L1) ← Garmin/Withings/CGM/化验/基因/环境/补剂/药物
```

**Orchestrator** (`app/orchestrator/`):
- `intent.py` — 关键字意图分类（safety/labs/recovery/fuel/movement/mental/chronic/longevity/knowledge/longitudinal）
- `specialists.py` — specialist 注册表，按依赖顺序执行
- `orchestrator.py` — `run_orchestrator` (非流式) / `stream_orchestrator` (SSE)
- `cross_review.py` — 确定性 specialist 冲突检测（营养 vs 慢病 / 训练 vs 恢复 / 补剂 vs 药物）。给冲突 finding 加 `conflict_flag`，合成 prompt 把冲突放最显眼位置。不引入额外 LLM 调用
- `arbitration.py` — LLM 仲裁层：cross_review 检出 hard conflict 或 ≥2 冲突时才升级到 LLM 裁决（成本可控），结构化 JSON 输出写 audit log，失败 fail-soft 回退到 prompt-based 渲染
- 共享 context：Recovery Coach 的 readiness_zone 自动传递给 Movement Coach
- 对话记忆：注入 `conversation_memory_service` 到 LLM prompt
- LLM 失败走模型注册表内的 provider failover

**13 Specialists** (`app/agents/`):

| Specialist | 模块 | 职责 |
|---|---|---|
| SafetyGuardian | `agents/safety_guardian/` | 确定性规则（计数以 `docs/_generated/system-map.json` 为准；覆盖药物/基因/急性阈值/CGM/训练负荷/症状急症/ECG房颤/个性化红线） |
| RecoveryCoach | `agents/recovery_coach/` | Readiness 0–100 加权评分（HRV/睡眠/压力/电量） |
| FuelStrategist | `agents/fuel_strategist/` | TDEE-摄入缺口 + 蛋白目标 + 基因驱动营养（MTHFR/APOE/FTO） |
| MovementCoach | `agents/movement_coach/` | ACWR × readiness 决策矩阵 + ACTN3 基因偏好 |
| MentalHealthCompanion | `agents/mental_health_companion/` | 危机检测 + 非药物行动 + 心理援助热线（Tier 5 隐私） |
| HypertensionSpecialist | `agents/chronic_specialists/` | ACC/AHA BP 分级 + 降压药识别 |
| MetabolicSpecialist | `agents/chronic_specialists/` | 代谢综合征判定（5 项命中 3 项）+ CGM TIR |
| RhinitisSpecialist | `agents/chronic_specialists/` | 症状分级 + AQI/湿度环境关联 + 用药依从性 |
| KnowledgeLibrarian | `agents/knowledge_librarian/` | reviewed System KB V2 entity/claim 检索；legacy Chroma/RAG 仅显式开关调试 |
| LongitudinalAnalyst | `agents/longitudinal_analyst/` | 6 个月趋势 + 干预事件×指标变化因果叙事 |
| SupplementAdvisor | `agents/supplement_advisor/` | SNP+化验驱动补剂建议 (MTHFR/APOE/HFE/COMT/VDR/FADS1) + Episode 12 周 N-of-1 闭环 + HFE 硬阻断 |
| LongevitySpecialist | `agents/longevity_specialist/` | PhenoAge(Levine 2018)表型年龄解读 + 缺值列清单 + 委托四件套(抗衰 MVP) |
| CrossSourceValidator | `agents/cross_source_validator/` | 跨设备(Garmin/Apple Watch/RingConn)同指标差异过大检测(佩戴位移/硬件故障/数据可疑)+ 暂以高优先级源为准 |

**Safety Guardian 规则分类** (`agents/safety_guardian/rules/`;
精确计数以 `docs/_generated/system-map.json` 为准):
- `vitals.py`: BP/HR/SpO2/stress/sleep 急性阈值
- `labs.py`: 肝酶三联/LDL/HbA1c/eGFR/WBC 模式识别 + 高尿酸血症(尿酸≥420μmol/L,自动判 mg/dL,非急症 MEDIUM) + 红细胞系整体偏高(HGB+HCT 同向超上限才触发,MEDIUM,非诊断)
- `ddi.py`: GLP-1×磺脲、华法林×NSAID、SSRI×MAOI 等
- `dsi.py`: 鱼油×抗凝、钙×铁、维K×华法林、圣约翰草、长期抑酸(PPI/P-CAB)×B12/镁/铁化验感知等
- `pgx.py`: 手写规则 + CPIC Level-A 表驱动(`pgx_cpic_table.py` 纯数据,无 @register;迭代 TPMT/NUDT15/HLA-B*15:02/HLA-A*31:01/HLA-B*58:01/CYP2C19/CYP2D6/CYP2C9/CYP3A5/CYP2B6/RYR1/CACNA1S)
- `training_load.py`: ACWR 过载/欠训练/零运动
- `cgm.py`: 低血糖/高血糖/TIR/CV/GLP-1 联动
- `symptoms.py`: 症状级急症红线(可疑心脏事件/卒中FAST/急性呼吸困难/急腹症/大病前兆/腰痛严重神经压迫警示)
- `cardiac.py`: Apple Watch ECG 房颤分类筛查(筛查非诊断, 升级措辞按次数, 给就医动作)
- `problem_red_lines.py`: 数据驱动——把用户已登记 HealthProblem 的 red_lines 与当前症状文本关键词匹配, 命中按 problem 风险等级升级(P0/P1→CRITICAL, P2→HIGH), 给医嘱里的 action
- `guidance_red_lines.py`: R4 越界拦截——扫描 AI 生成指导/总结文本里的量化/命令式饮食处方(`diet_prescription_red_line`→CRITICAL)与命令式体态/训练指令(`movement_imperative_red_line`→HIGH);读 `twin.acute.pending_guidance_texts`(仅 guidance 校验路径临时塞入, builder 永不填充, 默认空=存量评估行为零变化), 与 `services/guidance_validator.py` (token 级 strip/soften 护栏)共享正则

> 规则增删后运行 `scripts/dump_system_map.py` 与
> `scripts/check_doc_drift.py`；文档不手写架构计数。

**Digital Health Twin** (`app/twin/`):
- `schema.py` — 14 语义分区 Pydantic 模型（physiological/body_composition/labs/cgm/medication/supplement/genetic/environment/behavioral/acute/mental/chronic/goals/freshness）
- `builder.py` — 从 service 层聚合，Redis 函数级缓存（`use_cache=True`），失败降级
- `_collectors.py` — 过渡期薄 SQL 层（water/checkin/supplement/BP/exam/gene），事务安全回滚
- `cache.py` — Redis 5min TTL
- `formatter.py` — `twin_to_prompt_blob()` 生成紧凑 LLM 上下文文本

**Agent 审计日志** (`app/agents/audit.py` + `models/agent_audit_log.py`):
- 每次 Safety/Orchestrator 评估自动写入（旁路，失败不影响）
- `GET /api/v1/safety/audit` 查询用户的 agent 决策历史

### Request Flow (Web)

```
Browser → Next.js (localhost:3000)
  → rewrites /api/* → backend (localhost:8000) /api/v1/*
```

The Next.js `rewrites` in `next.config.js` proxies `/api/:path*` to the backend's `/api/v1/:path*`. Frontend code in `services/api.ts` uses relative `/api` paths. Mobile app (`mobile/services/api.ts`) uses an absolute URL — see "Local Dev Gotchas".

### AI Chat Routing (智能助理对话路由)

```
用户输入
    ↓
Agent Executor (/api/v1/agent/stream or /api/v1/agent/send)
    ↓
tool-calling 写库 / health_advice 调 Orchestrator / 普通问答
```

- **数据记录意图** → AgentExecutor tool-calling 写入受控 API
- **分析/知识/问答** → AgentExecutor 或 Orchestrator（specialist 协作）
- **有附件（图片/文件）** → AgentExecutor 多模态路径

Two entry points:
- `POST /api/v1/agent/stream` (SSE) — mobile/web/Mac 主入口
- `POST /api/v1/agent/send` — 不方便消费 SSE 的客户端入口
- `POST /api/v1/orchestrator/chat` / `POST /api/v1/orchestrator/chat/stream` — 深度分析/专家协作入口

### Key API Endpoints (Multi-Agent System)

| 端点 | 方法 | 职责 |
|---|---|---|
| `/api/v1/twin/me` | GET | 用户的 Digital Health Twin（14 分区状态快照） |
| `/api/v1/twin/me/invalidate` | POST | 手动使 Twin 缓存失效 |
| `/api/v1/safety/me` | GET | Safety Guardian 安全告警报告 |
| `/api/v1/safety/rules` | GET | 列出所有已注册的安全规则 |
| `/api/v1/safety/explain` | POST | 对单条告警请求 LLM 个性化解读 |
| `/api/v1/safety/audit` | GET | Agent 审计日志查询 |
| `/api/v1/safety/knowledge/index` | POST | 触发知识库索引构建 |
| `/api/v1/orchestrator/chat` | POST | 非流式综合分析 |
| `/api/v1/orchestrator/chat/stream` | POST | SSE 流式综合分析 |
| `/api/v1/cgm/readings` | POST/GET | CGM 血糖读数 CRUD |
| `/api/v1/cgm/readings/batch` | POST | CGM 批量导入（幂等） |
| `/api/v1/cgm/readings/latest` | GET | 最新 CGM 读数 |
| `/api/v1/cgm/readings/summary` | GET | CGM 24h 摘要（TIR/GMI/CV） |
| `/api/v1/personal-outcome/me/timeline` | GET | 长期健康改善时间序列 |

### Frontend AI Assistant Components

- `components/assistant/SafetyPanel.tsx` — 安全告警卡片 + 颜色分级 + 展开/折叠 + LLM 解读 + AI 综合分析弹窗
- `components/assistant/SpecialistsPanel.tsx` — 11 specialist 结果面板 + 类型化渲染
- `components/assistant/HeroCard.tsx` — 仪表盘主卡
- `components/assistant/QuickRecordBar.tsx` — 快速打卡 + undo + action-lock 防双击
- `components/assistant/AlertsBanner.tsx` — 饮水/血氧/HRV 实时提醒

### Auth Pattern

Backend uses JWT tokens. Frontend stores token in `localStorage` under key `auth_token`. Axios request interceptor in `api.ts` attaches `Authorization: Bearer {token}` header automatically. Mobile app uses `expo-secure-store` for the same key.

### Agent + LLM Configuration

Backend supports multiple LLM providers via `app/config.py`:
- `LLM_PROVIDER`: `openai` | `ollama` | `tokenplan`
- `LLM_VISION_MODEL` — separate vision model
- LLM 失败走模型注册表内的 provider failover

**Provider 类型与切换**：模型 registry 在 `backend/app/services/llm/model_registry.py`。每个 `ModelEntry.provider` 决定走哪条客户端路径：
- `openai-proxy` — `OPENAI_API_KEY` + `OPENAI_BASE_URL` (代理 CDN)
- `tokenplan` — 阿里云 TokenPlan 套餐 (qwen/deepseek/glm/minimax)
- `moonshot` / `zhipu` — 官方直连 (独立 key, 默认未配)
- `langbridge-proxy` — **走 browser-llm-orchestrator 的 `/api/llm/*` 代理**, 透明用 Claude / GPT / Gemini (含 vision)。需 `LANGBRIDGE_GATEWAY_BASE_URL` + `LANGBRIDGE_GATEWAY_API_KEY` 才会在 admin 下拉里出现。当前暴露 `claude-opus-4.7` / `gpt-5.5` / `gemini-3.1-pro` 三条 entry。

切换粒度：admin 全局 (`set_active_model_id`) / per-user (`user_profile.llm_model_id`)。`create_provider_for_user(user_id, db)` 每次新建,不缓存,用户切换立刻生效。

**Gateway 上线烟测**:配好两个 env 后跑 `python3 backend/scripts/smoke_langbridge_gateway.py` —— 仅靠 stdlib,串 GET `/health` + GET `/models` + POST 非流式 + POST 流式 + POST vision (合成 8×8 PNG),任一失败 exit 非零。模型不支持图片时加 `--skip-vision`,远端代理 buffer 流式时加 `--skip-stream`。

**LLM Harness 设计与方法论**：见 [`docs/HARNESS.md`](docs/HARNESS.md) — source-aware fast path / verification before write / tool schema 加厚 / memory 4-stage / provider failover / streaming TTS / Twin → prompt blob。新加 specialist / source / tool / memory stage 时**必须**同 PR 更新 HARNESS.md。

**Skills: one runtime location**

| Location | Lifetime | Auth context | Use case |
|---|---|---|---|
| `backend/skills/*/SKILL.md` | Deployed with backend; exposed through first-party Agent skills manifest | Runs as the logged-in user (JWT already attached) | Features that write/read **this user's** data via our API |

**Rule of thumb**: adding a feature for logged-in web/mobile users → `backend/skills/`. Do not add external skill distribution packages unless a new, explicit product decision restores that surface.

Per memory: **do not add backend route aliases to accommodate wrong skill calls** — update `SKILL.md` to be more explicit about the correct API path.

### Knowledge Base (知识库)

- **主路径**: reviewed System KB V2，数据来自 `backend/data/system_kb_v2_seed/*.jsonl` 导入到 `kb_documents/kb_edges/kb_audit`
- **来源**: `down-dedao` / `dedao-kbase` 只作为 authoring/export plane；健康运行时不直接搜原始笔记或 MCP
- **检索**: `/api/v1/knowledge/search` + `/api/v1/knowledge/lookup_for_twin`，BM25 + PostgreSQL `tsvector` FTS + sparse/pgvector vector + graph RRF
- **治理**: 只服务 `review_status=reviewed` 文档；draft/needs_review 不进入 health agent prompt
- **Legacy**: Chroma/RAG endpoint 默认 410；仅 `LEGACY_KNOWLEDGE_RUNTIME_ENABLED=true` 时用于本地调试旧索引

### Test Infrastructure

`backend/tests/conftest.py` provides:
- `db()` — clean in-memory SQLite database per test (StaticPool)
- `client(db)` — FastAPI TestClient with DB dependency override
- `sample_user_data`, `sample_basic_health_data`, `sample_medical_exam_data` — reusable fixtures

**Agent-specific test files**:
- `tests/test_twin_builder.py` — schema defaults, builder empty/partial, formatter, API shape
- `tests/test_safety_guardian.py` — each rule category正反例, severity 排序, API shape
- `tests/test_orchestrator.py` — intent, specialist registry, run e2e, API shape
- `tests/test_specialists.py` — Recovery/Fuel/Movement/Mental/Chronic 单测, needsSkill 回归

**Smoke test** (`tests/test_smoke.py`): A fixture-free `from main import app` check. Exists because `main.py` previously ran `Base.metadata.create_all()` at import time — when DB was unreachable, *every* test ImportError'd silently. Keep this file fixture-free so it still runs when `conftest.py` itself is broken.

## Extension Points

### Adding a New Specialist

1. 创建 `backend/app/agents/{name}/` 目录
2. 实现 Specialist Protocol: `applies_to(intent, twin) -> bool` + `run(twin, context) -> SpecialistFinding`
3. 在 `backend/app/orchestrator/specialists.py` 的 `_build_registry()` 里注册
4. **注意循环导入**：`__init__.py` 不要 import specialist 类（由 `specialists.py` 直接 import）
5. 写测试到 `tests/test_specialists.py`

### Adding a New Safety Rule

1. 在 `backend/app/agents/safety_guardian/rules/` 下对应文件写函数
2. 加 `@register` 装饰器（自动注册，无需修改 engine）
3. 函数签名: `(twin: HealthTwin) -> Optional[Alert] | List[Alert]`
4. 如果是新文件，在 `engine.py` 的 `_load_rule_modules()` 里 import 新模块
5. 写测试到 `tests/test_safety_guardian.py`

## Infrastructure

### Production (Alibaba Cloud ECS)

- **IP**: `39.98.206.178` (SSH port 22)
- **Project path**: `/opt/health-app/`
- **Frontend**: PM2 process `health-frontend` → `health.executor.life`
- **Backend**: systemd service `health-backend` → `health-api.executor.life`
- **Database**: PostgreSQL (same server)

### Docker

Root-level `docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.frontend` for local containerized dev. Production uses systemd/PM2 (not Docker).

### Logs

```bash
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"
ssh root@39.98.206.178 "pm2 logs health-frontend --lines 50"
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on push/PR to `main`:
- **Backend**: `pytest tests/ -q --no-cov --tb=short -x` (Python 3.12, fails fast; `DATABASE_URL=sqlite:///:memory:`) from `backend/`, then `python scripts/check_doc_drift.py` **from the repo root** (the script lives at repo-root `scripts/`, not `backend/scripts/` — running it from `backend/` fails with "No such file")
- **Frontend**: `npm run build` + `npm run lint` (Node.js 22)
- **Mobile**: `npx tsc --noEmit` (TypeScript typecheck only; no native build in CI)

**Doc-drift check** (`scripts/check_doc_drift.py`): Runs after backend tests. Compares code against a pinned `EXPECTED` table and fails CI if the architecture numbers in CLAUDE.md disagree with reality. Currently enforces: per-file `@register` counts in safety rules, `_build_registry()` length, and `HealthTwin` partition count. When you add/remove a rule/specialist/partition, update both this script's `EXPECTED` **and** CLAUDE.md in the same PR.

## Conventions

硬规范的权威来源是 `AGENTS.md`（章节导航）+ `docs/governance/*.md`（安全/测试/部署三章全文已拆出，见 Operating Harness Phase 2）。下面只列本文件必要的提示，**细节别在这里重述,去读对应章节/文件**：

| 触发场景 | 去读 |
|---|---|
| 新 API 路由 / 改认证 / 改 CORS | `docs/governance/security.md`（= AGENTS.md §1） |
| 加/改日志 | `AGENTS.md §2 日志` |
| 加测试 / 改 fixture | `docs/governance/testing.md`（= AGENTS.md §3） |
| 改 DB schema / 索引 / JSONB | `AGENTS.md §9 数据库` |
| 部署脚本 / CI 改动 | `docs/governance/deploy.md`（= AGENTS.md §8） |
| 处理敏感数据（基因、化验、CGM、消息） | `§5 数据安全与隐私` |
| 写 commit / 发 PR | `§6 代码提交规范` |

本文件范围内只记与架构相关的一条：所有后端路由挂在 `/api/v1` 下;生产密钥在 `.env`(不入库,`deploy.sh` 同步)。

## Complexity Budget (复杂度预算)

借鉴 autoresearch 的极简理念："20 行换 0.001 提升？不值得"。以下是硬性约束：

### File size

- **目标**：单个 `.py` / `.tsx` / `.ts` 文件不超过 500 行。新代码应遵守；已超限的文件不应扩大。
- **豁免**：自动生成的文件（文件名含 `.generated.`）不受约束。
- **现状是债务而非合规**：仓库有 20+ 文件超过 500 行，少数接近 2000+。需要当前实况时现场跑（别把数字钉在文档里,会过时）：

  ```bash
  find backend/app frontend/src mobile -type f \( -name '*.py' -o -name '*.tsx' -o -name '*.ts' \) \
    ! -name '*.generated.*' -exec wc -l {} + | sort -rn | head -20
  ```

- **操作原则**：修复不是目标，但"下次碰这个文件的时候顺手拆"是默认姿势。新加功能禁止往 1000+ 行的文件继续堆。

### Router organization

- `backend/app/api/main.py` mounts a large and growing number of routers. When adding new domain routes, consider grouping into subpackages (e.g. `api/health/`, `api/social/`) rather than piling onto the flat list.

### New dependencies

- 新增 pip/npm 包前，必须说明：(1) 现有包为什么不能解决 (2) Snyk 无已知漏洞 (3) 最近 6 个月内有更新
- 禁止 alpha/beta/rc 版本
- Pin exact versions (no `^` or `~`)

### 简洁优先

- 优先删除代码而非新增代码
- 不为假想的未来需求设计
- 三行相似代码优于过早抽象
- 如果改动加大了复杂度但没有可测量的改善（测试通过率、延迟、健康度评分），不应合入

### System health score

- **Script**: `backend/scripts/system_health_score.py`（项目的 "val_bpb"）
- `deploy.sh` 部署后自动运行；阈值 `DEPLOY_SCORE_THRESHOLD=35`（满分 60，skip-tests 模式）。低于阈值自动回滚到上一版本。
- 任何改动不应导致健康度评分下降。

## Architecture Layers (四层分离)

### 不可变核心层 (Frozen Core) — 修改需 review

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | 数据库连接、会话管理、`get_db` |
| `backend/app/config.py` | Pydantic Settings、环境变量 |
| `backend/app/models/*.py` | SQLAlchemy ORM 模型 |
| `backend/app/twin/schema.py` | Digital Health Twin Pydantic schema（14 分区） |
| `backend/main.py` 中间件部分 | 安全头、CORS、限流、请求上下文 |
| `backend/tests/conftest.py` | 测试基础设施 |
| `deploy.sh` | 部署流程（含备份与回滚） |

### Agent 层 (Agent Fleet) — 确定性规则 + 结构化裁决

| 目录 | 职责 |
|------|------|
| `backend/app/twin/` | Digital Health Twin 构建 + 缓存 + 格式化 |
| `backend/app/agents/safety_guardian/` | 安全规则引擎（不依赖 LLM；计数以 `docs/_generated/system-map.json` 为准） |
| `backend/app/agents/recovery_coach/` | Readiness 评分 + 恢复行动 |
| `backend/app/agents/fuel_strategist/` | 营养缺口 + 基因驱动饮食 |
| `backend/app/agents/movement_coach/` | ACWR + 训练处方 |
| `backend/app/agents/mental_health_companion/` | 危机检测 + 非药物支持 |
| `backend/app/agents/chronic_specialists/` | 鼻炎/高血压/代谢 专科管理 |
| `backend/app/agents/knowledge_librarian/` | reviewed System KB V2 检索；legacy Chroma/RAG 仅显式开关调试 |
| `backend/app/agents/longitudinal_analyst/` | 长期趋势 + 因果叙事 |
| `backend/app/orchestrator/` | 意图路由 + 专家调度 + LLM 合成 |
| `backend/app/agents/audit.py` | Agent 审计日志 |

### 可变业务层 (Mutable Business) — 自由迭代

| 目录 | 职责 |
|------|------|
| `backend/app/api/*.py` | API 路由 |
| `backend/app/services/*.py` | 业务逻辑（含 `cgm/` CGM 服务） |
| `backend/app/tasks/*.py` | Celery 异步任务 |
| `frontend/src/app/*/page.tsx` | 前端页面 |
| `frontend/src/components/*.tsx` | 前端组件（含 SafetyPanel/SpecialistsPanel） |
| `mobile/app/` | RN 页面 + Tab 导航 |
| `mobile/components/` | RN 组件（按领域分目录） |
| `mobile/services/` + `mobile/hooks/` | RN API 层 + React Query hooks |

### 指令层 (Instructions) — 定义 AI Agent 行为

| 文件 | 职责 |
|------|------|
| `CLAUDE.md` | Claude Code 工作指南（本文件） |
| `AGENTS.md` | AI Agent 开发规范（安全/日志/测试/性能/隐私的权威来源） |
| `.cursor/rules/00-agents-bootstrap.mdc` | Cursor 规则：强制读取并遵守 AGENTS.md |
| `backend/skills/*/SKILL.md` | 第一方 Agent Skill 定义（随后端部署） |
| `backend/data/knowledge_chromadb/` | 得到 wiki 知识库索引 |
