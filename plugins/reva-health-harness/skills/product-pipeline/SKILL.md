---
name: product-pipeline
description: "Codex adapter for a Reva feature that must move from an admitted product need through PRD, planning, implementation, verification, release, and production validation. Invoke only when reva-workflow-router selects feature mode or the user explicitly requests this workflow."
---

# 复元 Product Pipeline

This is the **Codex adapter** for Reva's agent-neutral product lifecycle. It
does not redefine the lifecycle and must not become a second controller.

## Sources of truth

Read these repository-relative files before acting:

1. `docs/governance/agent-skill-registry.json` for ownership, lifecycle, and routing.
2. `docs/governance/agent-skill-governance.md` for the one-controller contract.
3. `docs/specs/product-pipeline-contract.md` for the two loops, six Gates, and Dossier rules.
4. `docs/specs/reva-product-governance-spec.md` for product admission and safety boundaries.
5. The feature's `docs/dossiers/<date>-<slug>.md`, if it already exists.

`AGENTS.md` and `docs/governance/*` remain hard constraints. If any adapter
text conflicts with them, follow the repository contract.

## Entry contract

- Use this skill only when Router output names `product-pipeline` as
  `primary_controller`, or when the user explicitly invokes it.
- Own exactly one parent workflow run and one Dossier. Do not start a competing
  plan, checkpoint system, or completion state.
- Treat safety, database, privacy, doc-drift, and release skills as overlays or
  terminal workflows. They may block this controller but never replace it.
- If this skill delegates implementation to `health-harness-orchestrator`, the
  harness operates as S5 child phases in the same run and returns evidence here.

## Codex execution

1. Read the Dossier and resume from its recorded stage; otherwise create it at S0.
2. Complete the definition loop: intake, source-backed discovery, G1 admission,
   PRD, implementation plan, and G2 feasibility/safety pressure test.
3. Stop for required human decisions. Never silently convert REJECT, REFRAME,
   BLOCK, or failed Gates into success.
4. Split S4 work into independently verifiable tasks. Use Codex collaboration
   only where parallel read-only investigation or isolated implementation
   materially helps; keep one writer for shared files.
5. Delegate S5 implementation to the harness without creating another parent
   run. Record branch, commit, test, review, and release evidence in the Dossier.
6. Enforce G3 test, G4 safety, G5 deployment health, and G6 production/user-path
   validation. Any failed Gate returns to its documented upstream stage.
7. Mark shipped only after production evidence closes the requested user loop.

For a recoverable delivery run, use the repository trace CLI and store only its
path in the Dossier:

```bash
python3 scripts/harness_workflow_trace.py init \
  --kind product-pipeline \
  --dossier docs/dossiers/<date>-<slug>.md \
  --budget-tokens <hard-limit> \
  --label "<short label>"
```

Use the trace's `spawn`, `verdict`, `event`, and `summary` operations for the
same run. Exit code `2` is a budget stop, not permission to continue.

## Non-negotiable feedback rules

- Preserve unrelated dirty-worktree changes and stage only owned files.
- Never hide a test exit code with `| tail`.
- Long builds, deploys, and mobile releases run asynchronously where supported.
- Interface changes update both sides and their tests in the same change.
- When the user pauses, stop edits, tests, commits, pushes, and deployments and
  preserve the current evidence.
