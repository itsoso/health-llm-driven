# Persistent release key — implementation dossier

| 字段 | 值 |
| --- | --- |
| 状态 | shipping |
| 当前阶段 | S6 |

## G1 — maintenance admission

裁决: PASS

The user explicitly requested removal of mandatory eight-hour key renewal,
approved implementation and subsequently requested deployment. This is bounded
release-infrastructure maintenance with no Health OS object or medical behavior change.

## Scope

- Request: remove mandatory eight-hour renewal and allow reuse of the dedicated
  release key. Preserve version, CI, command, audit and failure boundaries.
- Baseline: `644b6a2ded140d8eff45d6a4e063b9575103768c` (fetched origin/main).
- Initial scope was source-only. The user subsequently requested deployment on
  2026-10-01, authorizing delivery of this change and migration of the release
  authorization. No unrelated application or mobile release is included.
- Controller: `health-harness-orchestrator`; overlay: `safety-gate`.
- Trace: local ignored `docs/_generated/harness-runs/8b23150f7c2a.jsonl`.
- Spec: [Persistent release identity](../specs/active/2026-10-01-persistent-release-key.md).

## Evidence

- RED: new lifetime tests failed on the original behavior (5 failures, 4 passes).
- Initial GREEN: bootstrap and server suites passed, 233 tests, before additional
  CLI and persistent-loopback cases were added.
- System Map check passed; these scripts are not indexed by the path selector,
  so conclusions are based on direct source and adjacent tests.
- Expanded regression: **815 passed, 9 skipped, 84 subtests passed**, exit 0,
  361.45 seconds. The skipped cases require isolated Linux SSH/systemd or a
  dedicated PostgreSQL integration URL; these are not claimed as locally passed.
- Interpreter: `/Users/liqiuhua/work/personal/health-llm-driven/.venv/bin/python`;
  invocation: `-m pytest --noconftest --no-cov -q --tb=short` over the bootstrap,
  trusted release server/gate/workflow/receipt, trusted OTA server/OTA, TestFlight,
  contained/review-maintenance/partial-Laya/native retirement, lost-closure
  acknowledgment, admin-key pause, frontend rebuild and review-reset test modules.
- Final `./scripts/system-map-check.sh` and `git diff --check`: passed.
- Reviewed tracked diff SHA256:
  `aeadba4997adf460bbc2578989b8c5e9531a9b9f8c4f2667d4efb2410ad6a070`.
- Independent `release_key_safety` reviewer: **G4 GO for source changes** on the
  above fixed diff. No blocking finding. Reviewer independently inspected source,
  tests and documentation; the expanded test receipt is producer evidence, not
  a second test execution. This is not a production migration or release GO.
- Source implementation complete; release preparation now in progress in the isolated worktree.

## Release boundary

Source completion does not recover the expired production authorization. After a
separately authorized reviewed release, the operator must migrate through canonical
bootstrap rotation; unchanged cloud key means no GitHub Secret replacement needed.
Local macOS verification does not substitute for Linux native gates or exact-SHA CI.
