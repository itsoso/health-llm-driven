# Agent Runtime Canary Control Plane Implementation Plan

> Execute test-first. Do not enable production canary traffic in this plan.

## Task 1: Rollout policy contract

**Files**
- Modify: `backend/app/config.py`
- Create: `backend/app/services/agent_runtime_rollout.py`
- Create: `backend/tests/test_agent_runtime_rollout.py`

**Steps**
1. Add failing tests for valid modes, stable bucketing, allowlist precedence, percentage
   boundaries and invalid configuration.
2. Add failing tests for `off`, selected/non-selected `canary`, `enforce` and paused
   circuit decisions.
3. Implement immutable rollout decisions and configuration validation.
4. Run the focused rollout policy tests.

## Task 2: Persistent circuit and audit ledger

**Files**
- Modify: `backend/app/models/agent_runtime.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/managed/20260720_120000_agent_runtime_rollout.postgresql.sql`
- Create: `backend/migrations/managed/20260720_120000_agent_runtime_rollout.sqlite.sql`
- Modify: `backend/tests/test_managed_migrations.py`
- Modify: `backend/tests/test_agent_runtime_rollout.py`

**Steps**
1. Add failing model and migration tests for singleton state, finite status/reason fields,
   append-only control audit and privacy constraints.
2. Add PostgreSQL/SQLite managed migrations and ORM models.
3. Implement transactional state creation, pause, resume and evaluation persistence.
4. Run migration and model tests on SQLite.

## Task 3: Admission and existing Run continuity

**Files**
- Modify: `backend/app/api/agent.py`
- Modify: `backend/tests/test_agent_runtime_api.py`
- Modify: `backend/tests/test_agent_runtime_resilience_api.py`

**Steps**
1. Add failing API tests proving stable canary admission and legacy bypass.
2. Add failing tests proving status/cancel remain available for existing managed Runs
   in `canary` and while paused.
3. Route `_admit_agent_runtime` through the rollout policy without changing the existing
   managed coordinator.
4. Run focused API, replay and SSE tests.

## Task 4: Aggregate metrics and automatic pause

**Files**
- Modify: `backend/app/services/agent_runtime_rollout.py`
- Modify: `backend/app/tasks/maintenance.py`
- Modify: `backend/app/celery_app.py`
- Create or modify: focused maintenance tests.

**Steps**
1. Add failing tests for aggregate-only snapshots, minimum sample, rate thresholds,
   hard reconciliation/stale-lease signals and duplicate-pause suppression.
2. Add failing tests proving recovery runs in `canary` and continues while paused.
3. Implement the bounded-window snapshot and evaluator.
4. Schedule evaluation after recovery and keep `off` as a no-op.
5. Run maintenance and Celery schedule tests.

## Task 5: Administrator controls

**Files**
- Modify: `backend/app/api/monitoring.py`
- Create or modify: monitoring API tests.

**Steps**
1. Add failing tests for unauthenticated, non-admin and admin access.
2. Add failing tests for aggregate response privacy and idempotent pause/resume audit.
3. Implement rollout status, pause and resume endpoints.
4. Run monitoring and authorization tests.

## Task 6: Cross-database and system verification

**Files**
- Modify: Runtime Feature Spec and Dossier.
- Regenerate: `docs/_generated/system-map.json` if architecture counts change.

**Steps**
1. Run focused SQLite suites for policy, models, API, maintenance and monitoring.
2. Run all managed migrations twice where idempotency is required.
3. Run real PostgreSQL Runtime state, concurrency, recovery and rollout tests using a
   disposable test database.
4. Run Agent conversation, ToolGateway, receipt, SSE and image-diet cross-regressions.
5. Run Ruff on changed Python files, `git diff --check`, system-map drift and Dossier
   consistency checks.
6. Perform an independent code review and resolve all P0/P1 findings.

## Task 7: Delivery with rollout disabled

1. Commit only files owned by this worktree and push the feature branch.
2. Open a PR and require all repository checks to pass.
3. Merge to `main` only after G3/G4 pass.
4. Deploy migrations and backend from a clean worktree with
   `agent_runtime_mode=off`.
5. Verify public health, database migration, Celery worker/beat and admin aggregate
   endpoint.
6. Record G5/G6 evidence. Do not change production mode or canary percentage.

