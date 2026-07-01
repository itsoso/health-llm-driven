# Reva Health Harness Plugin

Repo-local Codex plugin for the `health-llm-driven` product and delivery harness.

It packages the project-level `product-pipeline` and `health-harness-orchestrator`
skills plus the workflow trace, memory prime, friction scan, and LLM live-change
gate CLIs. The source of truth remains the repo contracts under `docs/`,
`AGENTS.md`, `.claude/skills/`, and `scripts/`; update this package when those
contracts change.

Install from the repo marketplace:

```bash
codex plugin marketplace add .agents/plugins
codex plugin add reva-health-harness@reva-health
```

Start a new Codex thread after reinstalling so newly packaged skills are loaded.
