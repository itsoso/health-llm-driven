# Remaining local change integration and release

| Field | Value |
|---|---|
| status | building |
| current_stage | S5 · integration and verification |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |
| Scope | Reconcile explicitly authorized local unique changes onto current main; verify and release |

## Authorization and preservation

User requested all remaining local work be merged into main and released after
the read-only inventory. Preserve original dirty checkout at
`/Users/thomas/work/personal/health-llm-driven`; integrate into the already-used
task checkout, never replace current main with old local main. No App Review
submission is authorized by this continuation; mobile delivery is TestFlight.

## Run and baseline

- Run: `docs/_generated/harness-runs/fba4d0426bc4.jsonl` (32000 allocated-token cap).
- Initial canonical baseline: `dbad4e66c`; source local main: `9fb13ee63`.
- Local inventory: 21 tracked modifications, 13 untracked files; three original
  voice commits and HTML rendering runtime are already represented upstream.
- Integration slices: share-location backend; mobile location editor and privacy
  disclosures; medication-status prompt-only delta; reconcile historical audit
  documentation without rewriting current completion claims.
- Gates remain open: new fixed-candidate safety review, fresh CI-mode/full CI,
  live prompt evaluation, AMap/Redis configuration validation, native simulator
  acceptance and reviewed production/TestFlight lifecycle.

## G1 · Authorized reconciliation

裁决：PASS。User explicitly authorized integrating the inventoried local work into
main and publishing. Existing feature definitions govern each slice; this is
reconciliation, not new product scope. Original checkout remains untouched.

## Findings / release boundaries

Original GPS feature dossier requires actual AMap configuration, quota/license
and live integration verification before enabling the client. Missing configuration
must be explicit and fail closed; mocks do not establish provider availability.
Do not revive the previously rejected medication validator exception.

## Verification and delivery

- Client slice committed as `6954cc185`; backend and prompt are staged for a
  fixed-candidate independent review. No push, production mutation or vendor task.
- Location backend RED missing-module then GREEN 51 tests, four new modules
  coverage 96.19%; actual provider and Redis Lua remain unverified.
- Client RED missing modules then GREEN 63 focused tests; full mobile suite
  3272 passed / 1 skipped. Both client TypeScript checks passed after OpenAPI
  generation. No native build or simulator GPS acceptance is claimed.
- Prompt RED 7 failures / 18 pass; two failures additionally exposed absent Pi
  dependencies. Installed exact committed Pi graph with its standard installer;
  prompt/panel GREEN 67 tests without changing test doubles or safety validator.
- Combined project CI shard (prompt/panel/medical/composed-read/location/privacy)
  258 passed, exit 0. This is local integration, not remote full CI.
- Current map generated and checked; dossier consistency (172), secret scan and
  skill governance passed. OpenAPI regenerated both clients using locked deps.
- Live LLM gate failed: offline inventories passed, orchestrator 0/5 because
  local TokenPlan credential is absent and fallback recipient is undisclosed.
  Did not grant disclosure or set a passing attestation. Production has a
  TokenPlan key, but has no AMap key; presence checks disclosed no secret values.
  Isolated synthetic server evaluation and GPS availability decision requested.
- Evidence logs: `/tmp/reva-voice-release.Jtlenr/integration-*` on this machine.

## G4 / G5 / G6

Independent fixed-candidate review pending. Live evaluation, exact remote CI,
provider readiness, backend and native TestFlight gates remain open; do not
interpret these local results or imported historical records as release success.
