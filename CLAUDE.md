# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-driven health management platform with Next.js frontend (Web only), FastAPI backend, an Expo React Native app for iPhone/iPad, a WeChat mini program, and a standalone MCP server. Integrates Garmin/Withings wearables, LLM-based health analysis, and OpenClaw AI assistant.

## ⚠️ 移动端构建方向（2026-04-19 决定）

**iPhone / iPad 原生 App 只走 React Native (`mobile/`) 路线。**

- ✅ **`mobile/`** (Expo SDK 54 + React Native 0.81) — **唯一**的 iPhone/iPad 原生 App 实现
- ❌ **Capacitor 壳 (`frontend/ios/`)** — 已停用；不再 `build:ios` / `sync:ios` / `open:ios`，新功能不往 Capacitor 方向适配
- ✅ **`frontend/`** (Next.js 14) — 继续作为 Web (PC 浏览器) 前端；iOS Safari 访问走 Web 版

**原因**：Capacitor 是 WebView 套壳，手势/滚动/键盘/动画有网页味，启动慢；RN 编译到真原生 UIView，体验和性能都显著更好。

**新功能开发规则**：
- 涉及 iPhone/iPad 的功能：**先写 `mobile/` 的 RN 版本**；Web 版可以延后或不做
- 组件复用通过 `packages/shared/` 的纯 TypeScript 类型/工具；UI 组件 RN 和 Web 两套各自写
- 后端 API 保持同一套（`/api/v1/*`），不为客户端分叉
- Capacitor 相关文件 (`frontend/ios/`, `frontend/capacitor.config.*`, `package.json` 的 `build:ios`/`sync:ios`/`open:ios`) 等后续统一清理；在此之前不要往里加新代码

## Monorepo Layout

This is a **pnpm workspace** (`pnpm-workspace.yaml` → `packages/*`) plus several non-workspace project roots. Each root has its own dependencies; `npm install`/`pnpm install` must be run in the right directory.

| Path | Stack | Purpose |
|------|-------|---------|
| `backend/` | FastAPI + SQLAlchemy + Celery | API server, agents, Twin, orchestrator |
| `frontend/` | Next.js 14 | Web app (PC browsers). `frontend/ios/` Capacitor 已停用 |
| `mobile/` | Expo SDK 54 + expo-router + React Native 0.81 | **iPhone/iPad 唯一原生 App** — 所有移动端新功能在这里做 |
| `packages/mini-program/` | WeChat mini program (uni-app) | `weixin` client |
| `packages/shared/` | TypeScript | Shared types/utilities across web/mobile/mini |
| `mcp-server/` | Python | Standalone MCP server exposing health tools |
| `openclaw-skills/` | Markdown | Root-level skill definitions consumed by OpenClaw Gateway (distinct from `backend/skills/` which are deployed with the backend) |

When working on shared logic, prefer `packages/shared` over duplicating. Mobile and mini-program are independent builds — changes in `frontend/` do NOT automatically propagate.

## Common Commands

### Backend (FastAPI + Python)

```bash
cd backend
source venv/bin/activate

# Run backend locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run all tests (CI requires SECRET_KEY and GARMIN_ENCRYPTION_KEY env vars)
pytest

# Run a single test file
pytest tests/test_achievement.py -v

# Run a single test function
pytest tests/test_users.py::test_create_user -v -s

# Test coverage
pytest --cov=app --cov-report=term-missing
```

### Celery (Async Tasks)

```bash
cd backend
source venv/bin/activate

# Start Celery worker
celery -A app.celery_app worker --loglevel=info

# Start Celery Beat (scheduled tasks)
celery -A app.celery_app beat --loglevel=info
```

Celery uses Redis as broker (`settings.redis_url`). Timezone is `Asia/Shanghai`. Scheduled tasks include daily health plans (6:00), morning summaries (7:30), plan reminders (8:00), trend pushes (8:30), evening insights (20:30), anomaly checks (23:00), weekly reports (Mon 9:00), and data cleanup (3:00). Full schedule in `backend/app/celery_app.py`.

### Frontend (Next.js 14 + TypeScript)

```bash
cd frontend
npm install
npm run dev      # Dev server at localhost:3000
npm run build    # Production build
npm run lint     # ESLint
npm run test     # Vitest
```

### iOS (Capacitor) — ⛔ DEPRECATED

Capacitor 壳已于 2026-04-19 停用，iPhone/iPad 请使用 React Native (`mobile/`) 路线。
历史命令（`build:ios` / `sync:ios` / `open:ios`）仍在 `package.json` 中但不再维护，等待统一清理。**不要**用这些命令构建 iOS App，也**不要**往 `frontend/ios/` 提交新代码。

### Mobile (Expo React Native)

```bash
cd mobile
npm install
npm run start        # Expo dev server (Metro)
npm run ios          # expo run:ios (requires Xcode)
npm run android      # expo run:android
```

The Expo app uses `expo-router` (file-based routing under `mobile/app/`), `@tanstack/react-query` for data, and `expo-secure-store` for tokens. React 19.1 with New Architecture enabled.

**App identity**: "HealthPilot", bundle ID `life.executor.health`, scheme `mobile`.

**Mobile architecture layers**:
- `services/` — API clients (api.ts, auth.ts, chat.ts, dashboard.ts, diet.ts, goals.ts, sleep.ts, workouts.ts, safety.ts, etc.)
- `hooks/` — React Query hooks wrapping services (useAuth, useDashboardData, useDiet, useGoals, useSleepData, useWorkouts, etc.)
- `components/` — UI split by domain: `chat/`, `dashboard/`, `diet/`, `goals/`, `notifications/`, `sleep/`, `design-system/`

**Tab navigation** (`mobile/app/(tabs)/`): Home, AI Chat, Quick Record, Safety Alerts, Health Cards.

**Notable native dependencies**: `react-native-maps` (workout GPS), `@react-native-voice/voice`, `expo-haptics`, `expo-notifications`, `expo-local-authentication` (Face ID), `react-native-reanimated`, `expo-image-picker`, `react-native-markdown-display`.

**⚠️ 这是 iPhone / iPad 的唯一原生 App 实现（Capacitor 已退役）**。所有涉及移动端的新 feature 都应先在 `mobile/` 里实现；`frontend/` 只负责 Web。

当前 `mobile/` 和 `frontend/` 的 feature parity 还在追赶中 — 若某个 Web 页面在 mobile/ 里没有对应的 RN 实现，优先补 RN 版本，而不是通过 Capacitor 把 Web 页面包成 App。

### Mini Program (WeChat)

```bash
cd packages/mini-program
npm install
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
./deploy.sh -f   # Deploy frontend only (most common)
./deploy.sh -b   # Deploy backend only (also syncs Skills, restarts Celery worker+beat, does DB backup)
./deploy.sh -a   # Deploy both (same as no flags)
./deploy.sh -e   # Sync .env-online to server and restart
./deploy.sh -r   # Restart services without pulling code
./deploy.sh -p   # Push code to GitHub without deploying
./deploy.sh -s   # Check service status
./deploy.sh -l   # View logs
```

Backend deploy automatically syncs `skills/*/SKILL.md` to the OpenClaw Gateway. Health score is checked post-deploy — auto-rollback on failure.

### Database Migrations

No Alembic — migrations are manual SQL files in `backend/migrations/`. Apply via:

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
10 Specialists (L3) ← 每个专家读 Twin、产出结构化 Finding
    ↓
Digital Health Twin (L2) ← 13 语义分区的统一状态视图 (Redis 5min 缓存)
    ↓
Collectors + Services (L1) ← Garmin/Withings/CGM/化验/基因/环境/补剂/药物
```

**Orchestrator** (`app/orchestrator/`):
- `intent.py` — 关键字意图分类（safety/labs/recovery/fuel/movement/mental/chronic/knowledge/longitudinal）
- `specialists.py` — 10 个 specialist 注册表，按依赖顺序执行
- `orchestrator.py` — `run_orchestrator` (非流式) / `stream_orchestrator` (SSE)
- 共享 context：Recovery Coach 的 readiness_zone 自动传递给 Movement Coach
- 对话记忆：注入 `conversation_memory_service` 到 LLM prompt
- LLM 失败自动回退 OpenClaw provider

**10 Specialists** (`app/agents/`):

| Specialist | 模块 | 职责 |
|---|---|---|
| SafetyGuardian | `agents/safety_guardian/` | 47 条确定性规则（药物/基因/急性阈值/CGM/训练负荷） |
| RecoveryCoach | `agents/recovery_coach/` | Readiness 0-100 加权评分（HRV/睡眠/压力/电量） |
| FuelStrategist | `agents/fuel_strategist/` | TDEE-摄入缺口 + 蛋白目标 + 基因驱动营养（MTHFR/APOE/FTO） |
| MovementCoach | `agents/movement_coach/` | ACWR × readiness 决策矩阵 + ACTN3 基因偏好 |
| MentalHealthCompanion | `agents/mental_health_companion/` | 危机检测 + 非药物行动 + 心理援助热线（Tier 5 隐私） |
| HypertensionSpecialist | `agents/chronic_specialists/` | ACC/AHA BP 分级 + 降压药识别 |
| MetabolicSpecialist | `agents/chronic_specialists/` | 代谢综合征判定（5 项命中 3 项）+ CGM TIR |
| RhinitisSpecialist | `agents/chronic_specialists/` | 症状分级 + AQI/湿度环境关联 + 用药依从性 |
| KnowledgeLibrarian | `agents/knowledge_librarian/` | 得到 wiki 69 篇 → ChromaDB RAG 检索 |
| LongitudinalAnalyst | `agents/longitudinal_analyst/` | 6 个月趋势 + 干预事件×指标变化因果叙事 |

**Safety Guardian 规则分类** (`agents/safety_guardian/rules/`):
- `vitals.py` (9): BP/HR/SpO2/stress/sleep 急性阈值
- `labs.py` (6): 肝酶三联/LDL/HbA1c/eGFR/WBC 模式识别
- `ddi.py` (7): GLP-1×磺脲、华法林×NSAID、SSRI×MAOI 等
- `dsi.py` (7): 鱼油×抗凝、钙×铁、维K×华法林、圣约翰草等
- `pgx.py` (9): CYP2D6/CYP2C19/SLCO1B1/G6PD/HLA-B*5701/DPYD/ALDH2/MTHFR
- `training_load.py` (3): ACWR 过载/欠训练/零运动
- `cgm.py` (6): 低血糖/高血糖/TIR/CV/GLP-1 联动

**Digital Health Twin** (`app/twin/`):
- `schema.py` — 13 语义分区 Pydantic 模型（physiological/body/labs/cgm/meds/supplement/genetic/env/behavioral/mental/chronic/goals/freshness）
- `builder.py` — 从 service 层聚合，Redis 函数级缓存（use_cache=True），失败降级
- `_collectors.py` — 过渡期薄 SQL 层（water/checkin/supplement/BP/exam/gene），事务安全回滚
- `cache.py` — Redis 5min TTL
- `formatter.py` — `twin_to_prompt_blob()` 生成紧凑 LLM 上下文文本

**Agent 审计日志** (`app/agents/audit.py` + `models/agent_audit_log.py`):
- 每次 Safety/Orchestrator 评估自动写入（旁路，失败不影响）
- `GET /api/v1/safety/audit` 查询用户的 agent 决策历史
- SQLite/PostgreSQL 双兼容 JSONColumn

### Request Flow (Web)

```
Browser → Next.js (localhost:3000)
  → rewrites /api/* → backend (localhost:8000) /api/v1/*
```

The Next.js `rewrites` in `next.config.js` proxies `/api/:path*` to the backend's `/api/v1/:path*`. Frontend code in `services/api.ts` uses relative `/api` paths. Mobile app (`mobile/services/api.ts`) uses absolute URLs pointing to `health-api.executor.life`.

### AI Chat Routing (智能助理对话路由)

```
用户输入
    ↓
needsSkill 正则匹配？(记录/打卡/吃了/早午晚餐...)
    ↓ YES                    ↓ NO
OpenClaw Gateway          Agent Executor / Orchestrator
(skill 写入数据库)        (纯分析/问答)
```

- **数据记录意图** → 走 OpenClaw（skill 才能调 POST API 写入）
- **分析/知识/问答** → 走 Orchestrator（10 specialist 协作）
- **有附件（图片/文件）** → 走 OpenClaw（支持多模态）

### Backend Structure

- **Entry point**: `backend/main.py` — creates FastAPI app, sets up CORS, rate limiting, DB tables
- **Router registry**: `backend/app/api/main.py` — imports and mounts all 107 API routers
- **Config**: `backend/app/config.py` — Pydantic `Settings` class, reads from `.env`
- **Database**: `backend/app/database.py` — SQLAlchemy engine (PostgreSQL in prod, SQLite for tests)
- **Models**: `backend/app/models/` — ~67 SQLAlchemy ORM models（含 `cgm_reading.py`、`agent_audit_log.py`）
- **Services**: `backend/app/services/` — business logic layer（含 `cgm/` CGM 服务）
- **Twin**: `backend/app/twin/` — Digital Health Twin（schema/builder/cache/formatter/collectors）
- **Agents**: `backend/app/agents/` — 多 Agent 舰队（safety_guardian/recovery_coach/fuel_strategist/movement_coach/mental_health_companion/chronic_specialists/knowledge_librarian/longitudinal_analyst）
- **Orchestrator**: `backend/app/orchestrator/` — 意图路由 + 专家调度 + LLM 合成
- **Schemas**: `backend/app/schemas/` — Pydantic request/response models
- **Tasks**: `backend/app/tasks/` — Celery async tasks
- **Skills**: `backend/skills/` — OpenClaw skill definitions
- **Knowledge**: `backend/data/knowledge_chromadb/` — 得到 wiki 知识库索引（302 chunks from 69 篇健康文章）
- **Tests**: `backend/tests/` — 104 agent/twin/safety 测试 + 800+ 总测试

### New API Endpoints (Multi-Agent System)

| 端点 | 方法 | 职责 |
|---|---|---|
| `/api/v1/twin/me` | GET | 用户的 Digital Health Twin（13 分区状态快照） |
| `/api/v1/twin/me/invalidate` | POST | 手动使 Twin 缓存失效 |
| `/api/v1/safety/me` | GET | Safety Guardian 安全告警报告（47 规则） |
| `/api/v1/safety/rules` | GET | 列出所有已注册的安全规则 |
| `/api/v1/safety/explain` | POST | 对单条告警请求 LLM 个性化解读 |
| `/api/v1/safety/audit` | GET | Agent 审计日志查询 |
| `/api/v1/safety/knowledge/index` | POST | 触发知识库索引构建 |
| `/api/v1/orchestrator/chat` | POST | 非流式综合分析（10 specialist 协作） |
| `/api/v1/orchestrator/chat/stream` | POST | SSE 流式综合分析 |
| `/api/v1/cgm/readings` | POST/GET | CGM 血糖读数 CRUD |
| `/api/v1/cgm/readings/batch` | POST | CGM 批量导入（幂等） |
| `/api/v1/cgm/readings/latest` | GET | 最新 CGM 读数 |
| `/api/v1/cgm/readings/summary` | GET | CGM 24h 摘要（TIR/GMI/CV） |
| `/api/v1/personal-outcome/me/timeline` | GET | 长期健康改善时间序列 |

### Test Fixtures

`backend/tests/conftest.py` provides:
- `db()` — clean in-memory SQLite database per test (StaticPool)
- `client(db)` — FastAPI TestClient with DB dependency override
- `sample_user_data`, `sample_basic_health_data`, `sample_medical_exam_data` — reusable test data

**Agent-specific tests** (104 tests):
- `tests/test_twin_builder.py` (20): schema defaults, builder empty/partial, formatter, API shape
- `tests/test_safety_guardian.py` (32): 各规则类别正反例, severity 排序, API shape
- `tests/test_orchestrator.py` (18): intent, specialist registry, run e2e, API shape
- `tests/test_specialists.py` (34): Recovery/Fuel/Movement/Mental/Chronic 单测, needsSkill 回归

### Frontend Structure

- **Pages**: `frontend/src/app/*/page.tsx` — Next.js App Router (~100 pages)
- **API client**: `frontend/src/services/api/` — Barrel re-export 目录（含 `safety.ts`、`orchestrator.ts`）
- **Auth**: `frontend/src/contexts/AuthContext.tsx` — React Context for auth state
- **Route guard**: `frontend/src/components/ProtectedRoute.tsx`
- **AI Assistant components** (`components/assistant/`):
  - `SafetyPanel.tsx` — 安全告警卡片 + 颜色分级 + 展开/折叠 + LLM 解读 + AI 综合分析弹窗
  - `SpecialistsPanel.tsx` — 10 specialist 结果面板 + 类型化渲染（readiness/进度条/处方/危机红框）
  - `HeroCard.tsx` — 仪表盘主卡（含 PM2.5 + 电量峰值/当前）
  - `QuickRecordBar.tsx` — 快速打卡 + undo 撤销 + action-lock 防双击
  - `AlertsBanner.tsx` — 饮水/血氧/HRV 实时提醒

### Auth Pattern

Backend uses JWT tokens. Frontend stores token in `localStorage` under key `auth_token`. Axios request interceptor in `api.ts` attaches `Authorization: Bearer {token}` header automatically.

### Adding a New Specialist (新 Agent 开发模式)

1. 创建 `backend/app/agents/{name}/` 目录
2. 实现 Specialist Protocol: `applies_to(intent, twin) -> bool` + `run(twin, context) -> SpecialistFinding`
3. 在 `backend/app/orchestrator/specialists.py` 的 `_build_registry()` 里注册
4. 注意循环导入：`__init__.py` 不要 import specialist 类（由 specialists.py 直接 import）
5. 写测试到 `tests/test_specialists.py`

### Adding a New Safety Rule

1. 在 `backend/app/agents/safety_guardian/rules/` 下对应文件写函数
2. 加 `@register` 装饰器（自动注册，无需修改 engine）
3. 函数签名: `(twin: HealthTwin) -> Optional[Alert] | List[Alert]`
4. 在 `engine.py` 的 `_load_rule_modules()` 里 import 新模块（如果是新文件）
5. 写测试到 `tests/test_safety_guardian.py`

### OpenClaw Integration

- **OpenClaw Gateway**: `POST /api/v1/openclaw/stream` (SSE) — 需要数据写入的对话走这里
- **Orchestrator**: `POST /api/v1/orchestrator/chat` — 分析/知识/问答走这里
- 前端 `handleSend()` 通过 `needsSkill` 正则自动路由

**Skills system**: Each skill in `backend/skills/<name>/SKILL.md` defines the API endpoints, parameters, and behavior that OpenClaw can invoke.

### LLM Configuration

Backend supports multiple LLM providers via `app/config.py`:
- `LLM_PROVIDER`: `openai` | `ollama` | `openclaw`
- Separate vision model config (`LLM_VISION_MODEL`)
- OpenClaw model: `OPENCLAW_MODEL=openclaw:main`（冒号自动转斜杠）
- LLM 失败自动回退到 OpenClaw provider

### Knowledge Base (知识库)

- **来源**: `~/work/personal/down-dedao/wiki/`（本地）或 `/opt/health-app/knowledge/dedao-wiki/`（服务器）
- **索引**: ChromaDB 持久化到 `backend/data/knowledge_chromadb/`
- **规模**: 137 篇 MD → 69 篇健康相关 → 302 个 chunks
- **触发索引**: `POST /api/v1/safety/knowledge/index` 或 `build_index(force=True)`
- **检索**: `search_knowledge(query, n_results=5)` → 语义向量搜索

## Infrastructure

### Production Server (Alibaba Cloud ECS)

- **IP**: `39.98.206.178` (SSH port 22)
- **Project path**: `/opt/health-app/` (frontend/ and backend/)
- **Frontend**: PM2 process `health-frontend` → `health.executor.life`
- **Backend**: systemd service `health-backend` → `health-api.executor.life`
- **Database**: PostgreSQL (on the same server)

### Docker

Root-level `docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.frontend` for containerized local development. Production uses systemd/PM2 (not Docker).

### Logs

```bash
# Backend logs (systemd)
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"

# Frontend logs (PM2)
ssh root@39.98.206.178 "pm2 logs health-frontend --lines 50"
```

## CI/CD

GitHub Actions (`.github/workflows/ci.yml`) runs on push/PR to `main`:
- **Backend**: `pytest tests/ -q --no-cov --tb=short -x` (Python 3.12, fails fast on first error)
- **Frontend**: `npm run build` + `npm run lint` (Node.js 22)

## Conventions

- **Git commits**: Conventional Commits in Chinese — `feat: 新功能`, `fix: 修复`, `docs:`, `refactor:`, `test:`
- **Frontend**: TypeScript, Tailwind CSS, Next.js App Router
- **Backend**: Python PEP 8, FastAPI, SQLAlchemy ORM, Pydantic schemas
- **API prefix**: All backend routes under `/api/v1`
- **Environment vars**: Production secrets in `.env-online` (not committed), synced by deploy script
- **Dependency versions**: Pin exact versions (no `^` or `~`). Check Snyk before adding new dependencies.
- **Database**: PostgreSQL only (SQLite is deprecated except for test fixtures). Use `JSONB` for JSON columns, `TIMESTAMP WITH TIME ZONE` for timestamps.
- **Security & quality standards**: `AGENTS.md` is the authoritative source for security rules, logging standards, testing specs, performance targets, and data privacy requirements. Read it before making infrastructure or security-related changes.

## Complexity Budget (复杂度预算)

借鉴 autoresearch 的极简理念："20 行换 0.001 提升？不值得"。以下是硬性约束：

### 文件大小限制

- **单个 .py / .tsx 文件不超过 500 行**。超过时必须拆分为子模块/子组件。
- **已知违规待修复**：`frontend/src/components/Navigation.tsx`、`frontend/src/app/settings/page.tsx`

### 路由组织

- `backend/app/api/main.py` 已有 107 个 router，应按领域分组为子包（如 `api/health/`、`api/social/`）。

### 新依赖审批

- 新增 pip/npm 包前，必须说明：(1) 现有包为什么不能解决 (2) Snyk 无已知漏洞 (3) 最近 6 个月内有更新
- 禁止 alpha/beta/rc 版本

### 简洁优先

- 优先删除代码而非新增代码
- 不为假想的未来需求设计
- 三行相似代码优于过早抽象
- 如果改动加大了复杂度但没有可测量的改善（测试通过率、延迟、健康度评分），不应合入

### 系统健康度

- **健康度评分脚本**: `backend/scripts/system_health_score.py`（项目的 "val_bpb"）
- 部署后自动运行，低于阈值自动回滚
- 任何改动不应导致健康度评分下降

## Architecture Layers (四层分离)

### 不可变核心层 (Frozen Core) — 修改需 review

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | 数据库连接、会话管理、get_db |
| `backend/app/config.py` | Pydantic Settings、环境变量 |
| `backend/app/models/*.py` | SQLAlchemy ORM 模型（~67 个） |
| `backend/app/twin/schema.py` | Digital Health Twin Pydantic schema（13 分区） |
| `backend/main.py` 中间件部分 | 安全头、CORS、限流、请求上下文 |
| `backend/tests/conftest.py` | 测试基础设施 |
| `deploy.sh` | 部署流程（含备份与回滚） |

### Agent 层 (Agent Fleet) — 确定性规则 + 结构化裁决

| 目录 | 职责 |
|------|------|
| `backend/app/twin/` | Digital Health Twin 构建 + 缓存 + 格式化 |
| `backend/app/agents/safety_guardian/` | 47 条安全规则引擎（不依赖 LLM） |
| `backend/app/agents/recovery_coach/` | Readiness 评分 + 恢复行动 |
| `backend/app/agents/fuel_strategist/` | 营养缺口 + 基因驱动饮食 |
| `backend/app/agents/movement_coach/` | ACWR + 训练处方 |
| `backend/app/agents/mental_health_companion/` | 危机检测 + 非药物支持 |
| `backend/app/agents/chronic_specialists/` | 鼻炎/高血压/代谢 专科管理 |
| `backend/app/agents/knowledge_librarian/` | 得到 wiki RAG 检索 |
| `backend/app/agents/longitudinal_analyst/` | 长期趋势 + 因果叙事 |
| `backend/app/orchestrator/` | 意图路由 + 专家调度 + LLM 合成 |
| `backend/app/agents/audit.py` | Agent 审计日志 |

### 可变业务层 (Mutable Business) — 自由迭代

| 目录 | 职责 |
|------|------|
| `backend/app/api/*.py` | API 路由（107 个） |
| `backend/app/services/*.py` | 业务逻辑（含 `cgm/` CGM 服务） |
| `backend/app/tasks/*.py` | Celery 异步任务 |
| `frontend/src/app/*/page.tsx` | 前端页面（~100 个） |
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
| `backend/skills/*/SKILL.md` | OpenClaw Skill 定义（22 个 skill，部署时同步到 Gateway） |
| `openclaw-skills/` | 根级 Skill 定义（10 个，由 OpenClaw Gateway 直接消费） |
| `backend/data/knowledge_chromadb/` | 得到 wiki 知识库索引（302 chunks） |
