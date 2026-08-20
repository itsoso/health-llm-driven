---
name: health-harness-orchestrator
description: "Codex adapter for implementing, debugging, verifying, reviewing, and delivering an already-defined Reva change. Invoke only when reva-workflow-router selects implementation or incident mode, or when product-pipeline delegates its S5 child phases."
---

# 复元 Health Harness — Codex Orchestrator

This thin **Codex adapter** executes the project-managed delivery harness. The
agent-neutral rules live in:

- `docs/governance/agent-skill-registry.json`
- `docs/governance/agent-skill-governance.md`
- `docs/design-agent-operating-harness.md`
- `AGENTS.md` and `docs/governance/*`

Read the relevant system-map context, source files, nearby tests, and active
Dossier before planning implementation.

## Controller boundary

- Run as `primary_controller` only when Router selects
  `health-harness-orchestrator` for implementation or incident mode.
- When invoked by `product-pipeline`, remain a delegated S5 child phase in the
  parent's run. Do not create a second Dossier, ledger, plan, or finish state.
- Capabilities such as systematic debugging, TDD, and verification add
  discipline; overlays such as safety or database review can block progress;
  neither category owns the workflow.
- A release terminal is selected by target and occurs only after its Gates pass.

## Codex-native workflow

1. **Scope:** inspect `AGENTS.md`, `docs/system-map/INDEX.md`, generated context,
   the active Dossier, dirty files, open PRs, and exact acceptance evidence.
2. **Plan:** define the smallest coherent tasks and cross-surface contracts.
   Keep one writer per shared file set.
3. **Implement:** use Codex subagents only for independent bounded work.
   Read-only investigators and reviewers may run in parallel; stateful writers
   need disjoint ownership or isolated worktrees.
4. **Incremental QA:** test each completed slice. For a real defect, establish
   the cause and a failing test before changing production behavior. LLM-facing
   changes also pass `scripts/harness_llm_change_gate.py` and any required live
   regression gate.
5. **Safety review:** sensitive health data, medication, genetics, safety rules,
   authentication, notifications, and write paths require the selected safety
   overlay. BLOCK returns to implementation and requires re-review.
6. **Release:** hand off to exactly one target-specific release workflow only
   after tests and review pass. Native changes are not mobile OTA changes.
7. **Validate:** prove the actual production/user path and return evidence to the
   parent controller or close this run when operating independently.

For multi-agent, interruptible, or adversarial-review work, keep one trace:

```bash
python3 scripts/harness_workflow_trace.py init \
  --kind health-harness \
  --dossier docs/dossiers/<date>-<slug>.md \
  --budget-tokens <hard-limit> \
  --label "<short label>"
```

When delegated, reuse the parent run instead of calling `init`. Record subagent
starts with `spawn`, Gate decisions with `verdict`, checkpoints with `event`, and
resume from `summary`. Exit code `2` means stop and reduce scope or seek a human
decision.

## Completion discipline

- Do not claim success from edits alone; report fresh command output and user-path evidence.
- Do not suppress exceptions, test failures, security blocks, or missing production proof.
- Preserve unrelated changes; stage and publish only the files owned by this run.
- If the user says pause, immediately preserve state and stop all mutating or release actions.
