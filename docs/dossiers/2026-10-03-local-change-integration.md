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
- Initial local live LLM gate failed: offline inventories passed, orchestrator 0/5 because
  local TokenPlan credential is absent and fallback recipient is undisclosed.
  Did not grant disclosure or set a passing attestation. Production has a
  TokenPlan key, but has no AMap key; presence checks disclosed no secret values.
  Isolated synthetic server evaluation and GPS availability decision requested.
- Evidence logs: `/tmp/reva-voice-release.Jtlenr/integration-*` on this machine.

## G4 / G5 / G6

Independent read-only source review of `77017fbfff4c8fb4a4e487763142a9fa6a7b7ea3`
against `dbad4e66c29f31c0ae149fecefa6c0d4f3e45283`: **GO**, no confirmed code-level
safety/privacy blocker. Reviewer independently ran backend location/medication
tests (66 passed) and mobile location service/editor (31 passed, two suites),
all exit 0; diff whitespace check passed. Logs are
`independent-integration-{backend,mobile}77017.log` in the evidence directory.

The initial live LLM block was resolved by the explicitly authorized isolated
synthetic evaluation (see update below). Source review does not clear provider
readiness or native acceptance. No deployment or TestFlight task has been
started by this integration run. Original source worktree changes remain preserved.

Read-only concurrency check found a separate backend-only trusted release
`37100225023` running for canonical `dbad4e66c`; its CI `37098891748` is green,
but neither run contains this integration. Do not seize that operation/lease.
The user subsequently authorized isolated synthetic evaluation and requested
testing the provider first, hiding unavailable lookup controls, and assessing
alternatives to AMap.

## 2026-10-03 · Live evidence and fail-closed availability follow-up

- Exact `c487d834fb25f79ace21c7a1cf6c8cc137cb4aeb` isolated live evaluation
  passed: invariants 12, core 50, orchestrator 5 (average 0.92), trajectory 12,
  goldens 9. No production database access. Result evidence is
  `/tmp/reva-isolated-live-eval-c487d834-result.json`, SHA-256
  `dc00b4766094fb119b5199091c2cd387d43a2c5cd9951ddfcf9eb159717f3940`.
- This exact revision was fast-forward pushed to main with its passing live
  attestation. Remote full CI `37101325279` is now completed/success. This is
  not deployment or TestFlight evidence and does not cover the follow-up below.
- AMap personal account / backend Web-service key created; key remains absent
  from production configuration and client code. Console still reports no
  technical service usage license; test success does not authorize public use.
- Three bounded live requests from the existing backend host used only a public
  landmark's synthetic coordinates/query: coordinate conversion, reverse
  geocoding, and text search all returned HTTP 200, status 1 / infocode 10000,
  with nonempty results. Key passed transiently in memory/SSH stdin; no key
  value, user location or health data was logged or stored. Temporary loopback
  test bridge stopped after verification; no production configuration changed.
- Follow-up implementation: `SHARE_LOCATION_ENABLED=false` by default;
  authenticated, no-store availability endpoint checks explicit rollout approval,
  key presence and Redis health without calling AMap or using lookup quota.
  Enabling requires provider testing, applicable public-use permission and
  acceptance evidence. The boolean is an operator rollout gate, not automated
  legal verification or a continuous upstream-health guarantee.
- Client hides provider consent/GPS/search while readiness is unknown/false or
  a lookup fails. Manual input stays available. Availability calls neither read
  GPS nor imply query consent. Late replies after cancel, unmount, identity
  change or backgrounding cannot enable the controls. Foreground return checks
  readiness again and requires fresh query consent.
- RED: backend missing endpoint/flag (4 failures), service missing availability
  helper (6 failures), UI visibility/lifecycle tests (6 failures). GREEN:
  project CI-mode backend location/Redis privacy 55 passed; mobile share-flow
  regression 12 suites / 235 passed; mobile and frontend TypeScript passed.
  Both API clients regenerated; System Map and secret scan passed.
- Follow-up remains local/uncommitted, pending fixed-candidate independent
  safety review, exact revision full CI, simulator acceptance and release gates.
  No new deployment/upload is claimed. Existing harness delegation budget is
  only 500 tokens; no additional agent fan-out or budget reset was performed.
- Alternative recommendation (not implemented): evaluate iOS MapKit POI search
  against the same public-place sample before switching providers. System
  reverse geocoding can supply city/street but is not exact restaurant evidence.
  Any provider switch must revise the explicit disclosure/consent recipient;
  do not silently send a failed AMap request to another provider.
