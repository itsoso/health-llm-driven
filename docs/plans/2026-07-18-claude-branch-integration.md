# Claude Branch Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate each currently unmerged `claude/*` branch into `main` only after source review, focused verification, safety review where required, and a final cross-branch regression gate.

**Architecture:** This is an integration-only change. Each source branch is cherry-picked in a dependency-aware order, then verified against the accumulated `main` state. A failed source item is fixed and retested before the next item begins; an unresolved blocker remains excluded from `main` and is recorded in the dossier.

**Tech Stack:** Git, Python/pytest, TypeScript/Jest, generated system-map drift checks, backend API and safety services.

---

### Task 1: Establish the integration baseline

**Files:**
- Modify: `docs/dossiers/2026-07-18-claude-branch-integration.md`

1. Confirm `main` equals `origin/main` and record pre-existing user work that must not be staged.
2. Inventory each unmerged Claude branch, its unique commits, file scope, dependencies, and risk class.
3. Run the relevant existing baseline tests before accepting source changes when a branch changes shared infrastructure.

### Task 2: Integrate low-coupling correctness changes

**Source branches:**
- `claude/nice-saha-fa4a3c`
- `claude/sweet-gould-b1c3c7`
- `claude/modest-golick-e58f3f`
- `claude/bold-swartz-79c816`
- `claude/quizzical-northcutt-8c66dc`
- `claude/thirsty-chandrasekhar-784f37`

1. Review the source diff and identify its focused regression tests.
2. Cherry-pick the source commit(s), resolving only mechanically necessary conflicts.
3. Run the focused test command against the accumulated codebase.
4. Record the test evidence and branch decision in the dossier.

### Task 3: Integrate safety and privacy chains

**Source branches:**
- `claude/bold-dirac-9ac246`
- `claude/competent-elbakyan-585f28` (supersedes `claude/recursing-ellis-bad3c5`)
- `claude/admiring-moore-1effbf`
- `claude/vigilant-euclid-a78ade`
- `claude/goofy-gagarin-d5f558`
- `claude/elastic-euler-d31f7b`
- `claude/genui-metric-table-safety`
- `claude/vigorous-hertz-e9070a`

1. Verify the privacy branch consumes the single drug-lexicon source rather than creating a competing source.
2. Review safety behavior at the public/read, notification, and GenUI boundaries.
3. Run focused tests plus the independent safety review for every safety, privacy, or health-advice change.
4. Run system-map generation and drift validation whenever a source changes derived architecture facts.

### Task 4: Integrate agent, memory, agenda, and transport changes

**Source branches:**
- `claude/causal-honesty-floor`
- `claude/recursing-mendeleev-5157cd`
- `claude/agitated-cerf-5c3abb`
- `claude/sweet-almeida-317556`

1. Verify causal-memory safeguards do not conflict with drug-confounding gates.
2. Verify agenda and interruption-budget changes preserve explicit write autonomy and quiet-hour rules.
3. Verify both streaming keepalive implementations preserve event ordering, client contracts, and failure signaling.
4. Regenerate API types only if the accumulated backend contract requires it, and test both client type surfaces.

### Task 5: Run the cross-branch release gate

**Files:**
- Modify: `docs/dossiers/2026-07-18-claude-branch-integration.md`

1. Review the final accumulated diff for duplicate rules, shadowed behavior, and missing user isolation.
2. Run backend targeted suites and the project integration suite in CI-compatible configuration.
3. Run mobile TypeScript and Jest suites affected by integrated changes.
4. Run document/system-map drift checks and inspect the main CI state.
5. Commit only the reviewed integration changes, push `main`, and record G3/G4 decisions. Deployment is explicitly outside this request and must not occur without a release request.

## Completion Record

- Tasks 1-4 were completed branch-by-branch on the accumulated `main` state. Duplicate, superseded, policy-blocked, and direct-cherry-pick-unsafe sources were excluded and recorded in the dossier rather than force-merged.
- Task 5 verification passed: backend safety/write-path, Agent/dynamic-view, timezone, outcome/migration, safety evaluator, Web, Mobile, Mac, generated API type, and system-map drift checks all have green evidence in the dossier.
- Independent review initially found four P1 integration gaps in the blood-pressure quick-record chain. The fixes added actual Mobile chat and Mac menu-bar rendering paths, kept Web Dashboard on the canonical response contract, and prevented streaming/interrupted/error assistant fragments from being written. Re-review: GO.
- Deployment and production validation remain intentionally out of scope for this integration request.
