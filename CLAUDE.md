# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-driven health management platform with Next.js frontend, FastAPI backend, and Capacitor iOS app. Integrates Garmin/Withings wearables, LLM-based health analysis, and OpenClaw AI assistant.

## Common Commands

### Backend (FastAPI + Python)

```bash
cd backend
source venv/bin/activate

# Run backend locally
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run all tests
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

### iOS (Capacitor)

```bash
cd frontend
npm run build:ios    # BUILD_TARGET=native next build && cap copy ios
npm run sync:ios     # cap sync ios
npm run open:ios     # Open in Xcode
```

When `BUILD_TARGET=native`, Next.js enables static export and the API base URL switches to `https://health.westwetlandtech.com/api`. Platform detection uses `NEXT_PUBLIC_IS_NATIVE_APP`.

### Deployment

```bash
./deploy.sh -f   # Deploy frontend only (most common)
./deploy.sh -b   # Deploy backend only (also syncs Skills to OpenClaw Gateway)
./deploy.sh -a   # Deploy both
./deploy.sh -e   # Sync .env-online to server and restart
./deploy.sh -r   # Restart services without pulling code
./deploy.sh -s   # Check service status
./deploy.sh -l   # View logs
```

Backend deploy automatically syncs `skills/*/SKILL.md` to the OpenClaw Gateway.

### Database Migrations

No Alembic — migrations are manual SQL files in `backend/migrations/`. Apply via:

```bash
psql $DATABASE_URL -f backend/migrations/create_xxx_tables.sql
```

## Architecture

### Request Flow (Web)

```
Browser → Next.js (localhost:3000)
  → rewrites /api/* → backend (localhost:8000) /api/v1/*
```

The Next.js `rewrites` in `next.config.js` proxies `/api/:path*` to the backend's `/api/v1/:path*`. Frontend code in `services/api.ts` uses relative `/api` paths (web) or absolute URLs (native app via Capacitor).

### Backend Structure

- **Entry point**: `backend/main.py` — creates FastAPI app, sets up CORS, rate limiting, DB tables
- **Router registry**: `backend/app/api/main.py` — imports and mounts all ~80 API routers
- **Config**: `backend/app/config.py` — Pydantic `Settings` class, reads from `.env`
- **Database**: `backend/app/database.py` — SQLAlchemy engine (PostgreSQL in prod, SQLite for tests)
- **Models**: `backend/app/models/` — SQLAlchemy ORM models
- **Services**: `backend/app/services/` — business logic layer (called by API routes)
- **Schemas**: `backend/app/schemas/` — Pydantic request/response models
- **Tasks**: `backend/app/tasks/` — Celery async tasks (Garmin sync, notifications, anomaly detection)
- **Scheduler**: `backend/app/scheduler.py` — Garmin data sync scheduler with OAuth token caching, rate limit handling, VO2Max extraction
- **Skills**: `backend/skills/` — OpenClaw skill definitions (10 skills, each with `SKILL.md`)
- **Tests**: `backend/tests/` — pytest with SQLite in-memory DB; fixtures in `conftest.py`

### Test Fixtures

`backend/tests/conftest.py` provides:
- `db()` — clean in-memory SQLite database per test (StaticPool)
- `client(db)` — FastAPI TestClient with DB dependency override
- `sample_user_data`, `sample_basic_health_data`, `sample_medical_exam_data` — reusable test data

### Frontend Structure

- **Pages**: `frontend/src/app/*/page.tsx` — Next.js App Router (~50+ pages)
- **API client**: `frontend/src/services/api.ts` — Axios instance with JWT auth interceptor
- **Auth**: `frontend/src/contexts/AuthContext.tsx` — React Context for auth state, token in `localStorage` as `auth_token`
- **Route guard**: `frontend/src/components/ProtectedRoute.tsx` — redirects to `/login` or `/onboarding`

### Auth Pattern

Backend uses JWT tokens. Frontend stores token in `localStorage` under key `auth_token`. Axios request interceptor in `api.ts` attaches `Authorization: Bearer {token}` header automatically.

### Adding a New Feature (typical pattern)

1. **Backend**: Create model in `models/`, schema in `schemas/`, service in `services/`, router in `api/`
2. **Register router**: Add import and `api_router.include_router()` in `api/main.py`
3. **Frontend**: Add API methods in `services/api.ts`, create page in `app/{feature}/page.tsx`

### OpenClaw Integration

Two distinct AI paths in the `/ai-assistant` page:
- **Health Assistant tab**: Backend builds health context → LLM API → parses action responses
- **OpenClaw tab**: Pure proxy to OpenClaw Gateway → `POST /api/v1/openclaw/stream` (SSE)

OpenClaw Gateway runs on a separate server (47.237.191.17, SSH port 22222) behind Nginx SSL at `bot.executor.life`.

**Skills system**: Each skill in `backend/skills/<name>/SKILL.md` defines the API endpoints, parameters, and behavior that OpenClaw can invoke. When modifying API routes used by OpenClaw, update the corresponding SKILL.md — do not add backend alias routes to accommodate AI guesses.

### LLM Configuration

Backend supports multiple LLM providers via `app/config.py`:
- `LLM_PROVIDER`: `openai` | `ollama` | `openclaw`
- Separate vision model config (`LLM_VISION_MODEL`)
- OpenClaw Analyze: dedicated multi-model analysis endpoint (`OPENCLAW_ANALYZE_*`)

## Infrastructure

### Production Server (Alibaba Cloud ECS)

- **IP**: `39.98.206.178` (SSH port 22)
- **Project path**: `/opt/health-app/` (frontend/ and backend/)
- **Frontend**: PM2 process `health-frontend` → `health.executor.life`
- **Backend**: systemd service `health-backend` → `health-api.executor.life`
- **Database**: PostgreSQL (on the same server)

### Logs

```bash
# Backend logs (systemd)
ssh root@39.98.206.178 "journalctl -u health-backend -n 50 --no-pager"

# Frontend logs (PM2)
ssh root@39.98.206.178 "pm2 logs health-frontend --lines 50"
```

## Conventions

- **Git commits**: Conventional Commits in Chinese — `feat: 新功能`, `fix: 修复`, `docs:`, `refactor:`, `test:`
- **Frontend**: TypeScript, Tailwind CSS, Next.js App Router
- **Backend**: Python PEP 8, FastAPI, SQLAlchemy ORM, Pydantic schemas
- **API prefix**: All backend routes under `/api/v1`
- **Environment vars**: Production secrets in `.env-online` (not committed), synced by deploy script
- **Dependency versions**: Pin exact versions (no `^` or `~`). Check Snyk before adding new dependencies. See `AGENTS.md` for full security standards.
- **Database**: PostgreSQL only (SQLite is deprecated except for test fixtures). Use `JSONB` for JSON columns, `TIMESTAMP WITH TIME ZONE` for timestamps.

## Complexity Budget (复杂度预算)

借鉴 autoresearch 的极简理念："20 行换 0.001 提升？不值得"。以下是硬性约束：

### 文件大小限制

- **单个 .py / .tsx 文件不超过 500 行**。超过时必须拆分为子模块/子组件。
- **已知违规待修复**：`frontend/src/components/Navigation.tsx`、`frontend/src/app/settings/page.tsx`

### 路由组织

- `backend/app/api/main.py` 超过 100 个 router 时，必须按领域分组为子包（如 `api/health/`、`api/social/`）。

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

## Architecture Layers (三层分离)

借鉴 autoresearch 的 prepare.py（不可变）→ train.py（可变）→ program.md（指令）模式：

### 不可变核心层 (Frozen Core) — 修改需 review

| 文件 | 职责 |
|------|------|
| `backend/app/database.py` | 数据库连接、会话管理、get_db |
| `backend/app/config.py` | Pydantic Settings、环境变量 |
| `backend/app/models/*.py` | SQLAlchemy ORM 模型 |
| `backend/main.py` 中间件部分 | 安全头、CORS、限流、请求上下文 |
| `backend/tests/conftest.py` | 测试基础设施 |
| `deploy.sh` | 部署流程（含备份与回滚） |

### 可变业务层 (Mutable Business) — 自由迭代

| 目录 | 职责 |
|------|------|
| `backend/app/api/*.py` | API 路由 |
| `backend/app/services/*.py` | 业务逻辑 |
| `backend/app/tasks/*.py` | Celery 异步任务 |
| `frontend/src/app/*/page.tsx` | 前端页面 |
| `frontend/src/components/*.tsx` | 前端组件 |

### 指令层 (Instructions) — 定义 AI Agent 行为

| 文件 | 职责 |
|------|------|
| `CLAUDE.md` | Claude Code 工作指南 |
| `AGENTS.md` | AI Agent 开发规范 |
| `backend/skills/*/SKILL.md` | OpenClaw Skill 定义 |
