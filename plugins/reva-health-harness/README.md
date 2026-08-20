# Reva Health Harness Plugin

Repo-local Codex plugin for governed work in `health-llm-driven`.

It packages one implicitly available `reva-workflow-router` plus explicit,
Codex-native `product-pipeline` and `health-harness-orchestrator` adapters. The
Router chooses the smallest sufficient Skill set and guarantees at most one
primary controller. Workflow trace, memory prime, friction scan, and LLM
live-change gate CLIs remain bundled for the selected workflow.

The agent-neutral sources of truth are:

- `docs/governance/agent-skill-registry.json`
- `docs/governance/agent-skill-governance.md`
- `docs/specs/product-pipeline-contract.md`
- `AGENTS.md` and `docs/governance/*`

Claude and Codex adapters may use platform-native collaboration primitives, but
must preserve the same routing, Gate, safety, and completion semantics.

Install the committed `main` marketplace (recommended):

```bash
codex plugin marketplace add itsoso/health-llm-driven --ref main
codex plugin add reva-health-harness@reva-health
```

Run `codex --version` first and use the Codex binary bundled with the desktop
app if an obsolete shell wrapper cannot start. A local checkout may be added
only for adapter development; do not persist a temporary worktree as the
installed marketplace source.

Start a new Codex thread after reinstalling so newly packaged skills are loaded.
The Router is the only plugin Skill eligible for implicit invocation; invoke the
two controller adapters only when the Router selects them or when explicitly
requested for an already-classified task.
