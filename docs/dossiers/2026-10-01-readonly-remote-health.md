# Read-only remote health MCP/OAuth

| Field | Value |
|---|---|
| date | 2026-10-01 |
| status | release_in_progress |
| current_stage | G3 local PASS; G4 implementation PASS; CI forward repair pending |
| owner_surface | Backend / Web consent |

Owner: delegated implementation and release. The user subsequently authorized PR, CI, review and backend/web code release, with the feature disabled. Real client registration, persistent access enablement and real user grants remain outside authorization.

Base: `01e8ddb6c` (includes independently owned PR265). Worktree: `health-remote-mcp`, branch `codex/health-readonly-remote-mcp`. Original dirty repository and other worktrees untouched.

Controllers: `reva-workflow-router` implementation mode; `health-harness-orchestrator`; safety and database overlays. [Feature contract](../specs/active/2026-10-01-readonly-remote-health.md).

## Evidence and gates

### G1 Product Admission: PASS

The user explicitly approved implementation and testing of a read-only remote connection. It supports observation/verification with existing records and reduces export/key-paste burden. Requirement admission and the bounded HealthTwin/ExecutionEvent mapping are recorded in the linked feature contract. It adds no clinical verdict or health write authority.

### G2 Feasibility And Risk: PASS

Existing first-party cookie login and owner-scoped record models are reusable. Official MCP SDK OAuth/Streamable HTTP behavior was inspected and exercised with synthetic clients. The implementation remains default-off; deployment, actual authorization and target-client compatibility are separate gates. Authentication and database changes require independent safety review and PostgreSQL evidence.

### G3 Local Tests: PASS

- RED: provider/queries/UI tests failed on missing implementations before their implementation.
- G3 local synthetic QA: 169 passed and one PostgreSQL-only concurrency test skipped in SQLite, covering real SDK OAuth/HTTP, consent, projections, isolation, bounds, date semantics, revocation, replay and privacy plus existing auth/date/migration regressions.
- PostgreSQL: 55 passed, including real replay/revocation/logging fixes, migration replay and concurrent code redemption; all 55 passed again after final dependency locking and GET-stream refusal. Synthetic local cluster only. Initial SQL_ASCII fixture error was corrected by creating a UTF-8 test database before the passing run.
- Frontend: 14 consent/connection Vitest cases plus dashboard/navigation regressions, 19 passed together on current main. Focused ESLint and whole frontend TypeScript check passed.
- System Map verification and LLM change gate passed; no live LLM call required by path gate.
- The production requirements lock was regenerated with hashes. All 169 SQLite regression cases passed again against the exact lock; `pip check` passed and `pip-audit --require-hashes` found no known vulnerabilities. This is a point-in-time advisory check, not a guarantee of absence of vulnerabilities.
- Pydantic schema changes required regeneration of both checked-in API clients. Generation drift check and whole frontend/mobile TypeScript checks passed after regeneration.

### G4 Safety Review: PASS

- G4 first independent review: NO-GO. Findings: public-client revoke compatibility, SDK input logging, HTTP replay revocation, credential storage cleanup and owner route bounds. Fixes and regression tests were added.
- Fresh independent reviewer returned GO for local implementation safety at `c414c0ebf`, relative to `01e8ddb6c`, with no concrete exploitable auth, isolation, token-logging or boundedness blocker. Reviewer independently ran 54 tests successfully with one PostgreSQL-only skip and inspected installed SDK PKCE, callback and stateless-lifecycle behavior. Final lock/type regeneration received the implementer's dependency and type checks above; these generated changes were outside that review snapshot.
- A second independent release review returned GO at `f365a1c7a` against `e8fa94a9f`, including final dependencies and generated types; 169 tests passed with one PostgreSQL-only skip. Required CI and production verification remain separate gates.
- G5/G6: pending required CI repair, review and verified default-off release.

### Forward repair after push deviation

The initial push unintentionally updated main to `f365a1c7a` before the requested PR. Its CI run [36835438871](https://github.com/itsoso/health-llm-driven/actions/runs/36835438871) failed because the three new remote-health suites were missing from the shard coverage catalog. The later PR266 main CI skipped release invariants, so its green result does not resolve this failure. No production release followed the deviation.

The user explicitly accepted retaining main and authorized forward correction. The repair branch starts from `c6f1eb999`, preserving PR265, PR266 and PR267. It adds the suites to the existing `r-other` shard and the PostgreSQL semantic job, with a regression contract requiring their PostgreSQL execution. Both omissions were reproduced locally before repair. Pushes must use explicit full source and destination refs after a dry-run confirms only the intended feature branch; upstream defaults and shared Git configuration are not changed. Release requires the repaired invariants to actually execute and pass, independent review, exact main CI and normal deployment verification.

Evidence logs: `/tmp/remote-health-locked-backend.log`, `/tmp/remote-health-locked-postgres.log`, `/tmp/remote-health-final-frontend.log`, `/tmp/remote-health-ui-lint.log`, `/tmp/remote-health-ui-types-locked.log`, `/tmp/remote-health-mobile-types-locked.log`, `/tmp/remote-health-api-types-final.log`, `/tmp/remote-health-dependency-audit.log`, `/tmp/remote-health-map-check.log`.

Dependency checks: [MCP 1.30.0](https://security.snyk.io/package/pip/mcp/1.30.0) and [Pydantic 2.12.5](https://security.snyk.io/package/pip/pydantic/2.12.5) have no direct findings in Snyk on 2026-10-01 (not a transitive audit). Official [session-bound advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-84m7-p3x7-pcfv) lists 1.30.0 as patched; this integration additionally uses stateless HTTP and 16 KB request limits. SDK public revocation and log-input behaviors found in local review have adapter regressions.

## Compatibility and handoff

The documented ChatGPT developer-mode custom MCP flow is web-only per official current help. Dot-mobile is unverified. Target client support for public OAuth pre-registration must be confirmed before enabling this version. Setup and exact discovery proxy requirements are in [operator instructions](../remote-health-connection.md).

No secret files or pasted keys were read. All token issuance occurred only in isolated synthetic tests. The temporary local PostgreSQL test server was stopped before handoff.
