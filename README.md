# Reva Personal Health OS

> AI health execution system for daily leverage actions, safety-gated automation, and N-of-1 outcome verification.

Reva is not a health chatbot and not another wearable dashboard. It is a Personal Health OS that turns fragmented health data into a small number of safe, high-leverage actions, helps the user execute them on the right surface, and verifies whether those actions actually improved this user's trajectory.

The first product wedge is 35-55 year-old high-intensity workers with early metabolic risk, recovery problems, wearable data, lab results, and enough motivation to act but not enough time or execution bandwidth.

## Product Thesis

Modern health products have made sensing cheap: wearables measure sleep, HRV, training load, glucose, SpO2, and activity; lab platforms expose hundreds of biomarkers. The unsolved problem is execution.

Reva's core loop is:

```text
Labs / wearables / symptoms / meds / supplements / behavior
  -> Digital Health Twin
  -> Safety Gate
  -> Leverage Action Ranker
  -> Agenda top action
  -> Watch / Mobile / Mac execution
  -> Execution event
  -> Retest / outcome review
  -> next action, with more personal evidence
```

The durable asset is not a model answer. It is the per-user causal ledger: what was suggested, what was executed, what was verified, and what actually worked for this person.

## What Is Implemented

| Layer | Purpose | Key files |
|---|---|---|
| Digital Health Twin | Shared semantic state for agents and UI | `backend/app/twin/schema.py`, `backend/app/twin/builder.py`, `backend/app/twin/snapshots.py` |
| Agent Orchestrator | Routes work across specialist agents and synthesis | `backend/app/orchestrator/` |
| Safety Guardian | Deterministic guardrails for vitals, labs, DDI/DSI, PGx, CGM, symptoms, training load | `backend/app/agents/safety_guardian/` |
| Health Agenda | Today/week/month/quarter action projection | `backend/app/services/agenda_service.py` |
| Action Ranker | Scores actionable items by upstreamness, actionability, frequency, verifiability, confidence, friction, and safety tier | `backend/app/services/action_ranker.py` |
| Watch summary | Wrist-first status, top action, quick actions, push candidates, and data freshness | `backend/app/services/watch_summary.py`, `apps/watch/` |
| Intervention cycle | 8-12 week baseline, targets, retest, delta, and noise-aware outcome status | `backend/app/models/intervention_cycle.py`, `backend/app/services/intervention_cycle_service.py` |
| Biomarker layer | Canonical observations from medical exams | `backend/app/biomarkers/`, `backend/app/services/biomarker_service.py` |
| Longevity / PhenoAge | Blood-test-derived phenotypic age with explicit claim boundary | `backend/app/services/phenoage.py`, `backend/app/agents/longevity_specialist/` |
| Mobile execution surface | Today hero, write intents, medication/supplement check-in, 90-day cycle, action cards | `mobile/app/(tabs)/index.tsx`, `mobile/components/` |

## Core Surfaces

- **Mobile**: primary daily product surface. It shows readiness, one current action, agenda timeline, medication/supplement check-in, body data, and active intervention cycle.
- **Apple Watch**: execution surface. It receives the top action, due items, freshness status, and low-friction completion affordances.
- **Mac**: workstation for import, review, trace inspection, and longer agent workflows.
- **Web**: administrative, historical, and secondary views.
- **Backend**: source of truth for health state, safety rules, action ranking, intervention cycles, and auditability.

## Architecture

```text
Mobile / Watch / Mac / Web
        |
        v
FastAPI API + Auth + Audit
        |
        +--> Digital Health Twin
        +--> Safety Guardian
        +--> Orchestrator + Specialists
        +--> Health Agenda + ActionRanker
        +--> InterventionCycle + OutcomeMetric
        |
        v
PostgreSQL + Redis + Celery
        |
        v
Garmin / Withings / CGM / HealthKit / medical exams / environment / LLM providers
```

Primary architecture document: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Primary product document: [`docs/prd/reva-personal-health-os-prd.md`](docs/prd/reva-personal-health-os-prd.md).

Leverage-action product document: [`docs/prd/2026-06-16-health-leverage-action-os-pdd.md`](docs/prd/2026-06-16-health-leverage-action-os-pdd.md).

## Safety Boundary

Reva is a personal health management system, not a doctor, diagnostic device, prescription engine, or emergency triage replacement.

Hard boundaries:

- No prescribing.
- No autonomous medication dose changes.
- No diagnosis replacement.
- No "you are fine" conclusion for red-flag symptoms.
- No generalized claims from weak or missing data.
- High-risk medical paths must route through safety rules, human review, or clinician follow-up.

See [`docs/HEALTH_WORLDVIEW.md`](docs/HEALTH_WORLDVIEW.md), [`docs/HARNESS.md`](docs/HARNESS.md), and [`docs/governance/security.md`](docs/governance/security.md).

## Tech Stack

| Area | Stack |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, Pydantic, Celery |
| Database | PostgreSQL |
| Cache / jobs | Redis, Celery Beat |
| Mobile | Expo / React Native / TypeScript |
| Watch | Swift Package + watchOS app modules |
| Web | Next.js 14, React 18, TypeScript |
| LLM | TokenPlan/OpenAI-compatible providers, OpenAI, OpenClaw fallback, local dev providers |
| Knowledge / retrieval | Internal knowledge services and RAG paths |
| Deployment | `deploy.sh`, systemd, PM2, Nginx |

SQLite-era docs are historical. New database work must target PostgreSQL.

## Repository Map

```text
backend/        FastAPI app, models, services, agents, migrations, tests
mobile/         Expo mobile app and service clients
apps/watch/     Watch companion models, app, complication, tests
apps/mac/       Native Mac app workbench
frontend/       Next.js web app
docs/           Current architecture, PRD, plans, governance, reports, archive
scripts/        Migration, release, deployment, and verification helpers
openclaw-skills/ Public skill distribution assets
mcp-server/     MCP server integration
packages/       Workspace packages
```

## Local Development

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure backend/.env.
# Use PostgreSQL for development and production.

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Mobile

```bash
cd mobile
npm install
npx expo start
```

### Web

```bash
cd frontend
npm install
npm run dev
```

### Watch Core Tests

```bash
cd apps/watch
swift test
```

## Verification

Use focused verification for the surface you changed:

```bash
# Backend
cd backend
source venv/bin/activate
pytest tests/test_action_ranker.py tests/test_watch_summary.py
ruff check app tests

# Mobile
cd mobile
npx tsc --noEmit
npm test -- --runInBand

# Watch
cd apps/watch
swift test

# Repo hygiene
git diff --check
```

For architecture number drift:

```bash
python3 scripts/check_doc_drift.py
```

## Deployment

Project deployment is centralized in the root script:

```bash
./deploy.sh -f   # frontend
./deploy.sh -b   # backend
./deploy.sh -a   # all
./deploy.sh -s   # service status
./deploy.sh -l   # logs
```

Mobile JS/TS/UI-only changes should prefer:

```bash
scripts/mobile-ota.sh production "<message>"
```

Use EAS build/submit only for native config, dependencies, profiles, SDK upgrades, or TestFlight package changes.

## Documentation

Current docs live under `docs/`.

| Document | Purpose |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Current system architecture |
| [`docs/specs/reva-product-governance-spec.md`](docs/specs/reva-product-governance-spec.md) | Product-scope constitution and requirement admission gate |
| [`docs/prd/reva-personal-health-os-prd.md`](docs/prd/reva-personal-health-os-prd.md) | Canonical product PRD |
| [`docs/prd/2026-06-16-health-leverage-action-os-pdd.md`](docs/prd/2026-06-16-health-leverage-action-os-pdd.md) | Leverage action OS product layer |
| [`docs/HARNESS.md`](docs/HARNESS.md) | Product LLM harness methodology |
| [`docs/HEALTH_WORLDVIEW.md`](docs/HEALTH_WORLDVIEW.md) | Health philosophy, boundaries, red lines |
| [`docs/governance/security.md`](docs/governance/security.md) | Security governance |
| [`docs/governance/testing.md`](docs/governance/testing.md) | Testing governance |
| [`docs/governance/deploy.md`](docs/governance/deploy.md) | Deployment governance |
| [`docs/archive/`](docs/archive/) | Historical root-level fix reports and temporary implementation notes |

Root directory policy:

- Keep root for entrypoints, configs, package manifests, deploy scripts, and agent instructions.
- Put current product, architecture, and planning docs under `docs/`.
- Put old one-off fix reports under `docs/archive/`.
- Do not add new root-level `*_FIX.md`, `*_SUMMARY.md`, `*_GUIDE.md`, or deployment report files.

## Current Product Bet

The next financing-grade proof should not be more features. It should be a small paid cohort with:

- lab upload and biomarker normalization,
- active 8-12 week metabolic/recovery cycles,
- daily top-action completion,
- retest completion,
- noise-aware outcome deltas,
- safety and human-review cost,
- renewal or referral intent.

The product story is credible only when the system can show: "for this user, these actions were executed, these metrics moved, and the confidence boundary is explicit."
