# Health Platform Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close confirmed production security gaps without changing the explicitly accepted two-year JWT lifetime.

**Architecture:** Protect every personal-health boundary with authenticated server-side identity, then centralize API-key and Agent write authorization before hardening rendering, credentials, backups, dependencies, and production infrastructure. Each batch is independently testable and deployable; a failed safety or CI gate blocks the next deployment.

**Tech Stack:** FastAPI, SQLAlchemy, Pytest, Next.js/React, React Native, Swift, PostgreSQL, Nginx, systemd, GitHub Actions.

## Execution Status (2026-07-22)

| Task | Status | Remaining gate |
|---|---|---|
| 1. Anonymous/cross-user access | Implemented and locally verified | Branch/main CI |
| 2. API-key scopes | Implemented and locally verified | Branch/main CI |
| 3. Agent write authority | Implemented, locally verified, G4 GO | Branch/main CI |
| 4. Rendering/client credentials | Code complete and locally verified | Native signed Mobile/Mac release for Keychain changes |
| 5. Secrets/backups | Code complete and locally verified, including authenticated HMAC manifests | Configure independent integrity key and run a real off-host download/decrypt/restore drill |
| 6. Dependencies | Audits currently report no known production vulnerabilities | Branch/main audit jobs |
| 7. Infrastructure/privacy exits | Repository configuration complete | Install and verify Nginx/systemd/UFW on production |
| 8. Defense in depth/release | Partial; proxy revocation, bounded report ingress, exact-SHA rollback containment and runtime schema probes are locally verified; independent safety review G4 GO | Least-privilege PostgreSQL roles, broad RLS design, green main CI, G5/G6 smoke verification |

The accepted two-year JWT lifetime remains unchanged. No production deployment is allowed while Task 8 blockers remain.

---

### Task 1: Block anonymous and cross-user health access

**Files:**
- Create: `backend/tests/test_legacy_health_route_security.py`
- Modify: `backend/app/api/diseases.py`
- Modify: `backend/app/api/daily_health.py`
- Modify: `backend/app/api/data_collection.py`
- Modify: `backend/app/api/diet_recommendation.py`
- Modify: `backend/app/api/garmin_analysis.py`
- Modify: `backend/app/api/daily_recommendation.py`
- Regenerate: `frontend/src/types/api.generated.ts`
- Regenerate: `mobile/types/api.generated.ts`

1. Add parameterized tests proving every legacy personal-health route returns `401` without credentials.
2. Run the tests and verify they fail with the current `200`/database behavior.
3. Require an approved user on all routes, reject explicit cross-user access for non-admin users, and filter object lookups by owner.
4. Run the focused tests, auth tests, OpenAPI/type generation, and backend route tests.
5. Commit as an isolated security fix and deploy only after the safety gate passes.

### Task 2: Enforce API-key scopes globally

**Files:**
- Modify: `backend/app/api/deps.py`
- Modify: `backend/app/api/user_api_key.py`
- Modify: health write route dependencies
- Create: `backend/tests/test_api_key_scope_enforcement.py`

1. Add failing tests proving a read-only key cannot write health data, change passwords, manage family access, or perform admin actions.
2. Attach authentication type, key ID, and normalized scopes to `request.state`.
3. Introduce explicit read/write/high-risk scope dependencies; high-risk account and medication operations reject API keys by default.
4. Remove token/API-key prefixes from logs and run authentication regression tests.

### Task 3: Make user authorization the only Agent write authority

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/app/services/write_intent_service.py`
- Modify: `backend/app/api/write_intents.py`
- Create: `backend/tests/test_agent_write_authority.py`

1. Add failing prompt-injection and model-argument tests for `confirmed=true`, update, and delete operations.
2. Strip model-generated authorization fields at the shared write choke point.
3. Allow execution only from deterministic current-turn user intent or a source-bound, unexpired WriteIntent/client confirmation event.
4. Route update/delete through the same receipt and audit mechanism and run cross-family capstone tests.

### Task 4: Close Web rendering and client credential exposure

**Files:**
- Modify: `frontend/src/components/assistant/ActionCardPanel.tsx`
- Modify: `frontend/src/contexts/AuthContext.tsx`
- Modify: `mobile/modules/shared-keychain/ios/SharedKeychainModule.swift`
- Modify: `apps/mac/Sources/HealthAgentMac/App/AppServices.swift`
- Add frontend and native security regression tests.

1. Add failing stored-XSS tests for action-card Markdown/table content.
2. Replace raw HTML assembly with a sanitized renderer and add a restrictive CSP.
3. Move Web sessions away from persistent script-readable bearer storage.
4. Migrate Mobile and Mac to Keychain-only storage and delete historical UserDefaults copies.
5. Keep the accepted JWT duration unchanged.

### Task 5: Repair secret and backup handling

**Files:**
- Modify: `.gitignore`
- Modify: `deploy.sh`
- Modify: `backend/scripts/backup_db.sh`
- Modify: `backend/scripts/verify_backup.sh`
- Add deployment shell tests.

1. Move local runtime environment backups outside the repository and add secret-scan gates.
2. Set production `.env` to `0600` and rotate credentials if external copying cannot be excluded.
3. Move database backups outside the Git worktree so `git stash -u` cannot remove them.
4. Make backup and health-check failures block deployment.
5. Add encrypted off-host retention and automated restore verification.

### Task 6: Remove critical/high dependency exposure

**Files:**
- Modify frontend, mobile, mini-program lockfiles and backend production dependency lock.
- Modify `.github/workflows/ci.yml`.

1. Upgrade Next.js, Axios, Pillow, python-multipart, Starlette, PyJWT dependencies without changing token lifetime.
2. Patch or replace vulnerable mobile Markdown dependencies.
3. Upgrade or isolate the inactive mini-program build.
4. Add production-only npm/pip audit gates and deterministic hashed Python locks.

### Task 7: Harden production infrastructure and privacy exits

**Files:**
- Version Nginx/systemd/firewall configuration.
- Modify notification and logging choke points.

1. Restrict Prometheus, Node Exporter, Grafana, database, Redis, and MCP to loopback/VPN.
2. Run backend and workers as dedicated non-root users with systemd sandboxing.
3. Enforce lock-screen privacy centrally for medication, supplement, diagnosis, and lab reminders.
4. Remove health text/share tokens from logs; add persistent audit events for exports and privileged changes.
5. Add per-user/global Agent concurrency and cost admission controls.

### Task 8: Defense in depth and release gate

1. Separate PostgreSQL migration owner and runtime roles; expand RLS across L3 tenant tables.
2. Add bounded streaming uploads, MIME/magic checks, defused XML parsing, and parsing quotas.
3. Run full PostgreSQL tests, dependency scans, secret scans, safety/privacy review, restore drill, and concurrent abuse tests.
4. Require a green main CI and production smoke verification before returning a GO verdict.
