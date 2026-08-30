---
name: reva-workflow-router
description: "Route Reva repository work to the smallest governed Skill set before planning or editing. Use for analysis, quick fixes, features, implementation, incidents, and releases so the task has at most one controller and only relevant overlays."
---

# Reva Workflow Router

This is the **Codex routing adapter**. It selects workflow ownership; it does
not perform the requested engineering work itself.

Canonical policy:

- `docs/governance/agent-skill-registry.json`
- `docs/governance/agent-skill-governance.md`

## Route first

1. Classify the task as exactly one mode:
   `analysis`, `quick_fix`, `feature`, `implementation`, `incident`, or `release`.
   `planning` and `verification` are workflow phases, not mode values.
2. Add only overlays actually triggered by the changed surface. Use canonical
   overlay IDs from the registry; do not invent aliases.
3. Add a canonical `capability-trigger` only when the task actually authors a
   Skill or Codex plugin. Capabilities never become controllers.
4. For release mode, identify exactly one release target.
5. Run the deterministic recommender from the repository root:

```bash
python3.12 scripts/check_agent_skill_governance.py recommend \
  --mode <mode> \
  [--overlay <canonical-id>] \
  [--capability-trigger <canonical-id>] \
  [--release-target <target>]
```

Repeat `--overlay` when needed. Unknown modes, overlays, and release targets are
blocking errors. Do not guess around them.

## Apply the recommendation

- At startup, load only IDs in `immediate_skills`.
- When work enters a named phase, load only that phase's IDs from
  `deferred_by_phase`; `on_demand` activates only when its trigger is actually
  needed, and an S5 delegate activates inside the existing parent run.
- `activation_skills` and `activation_skill_details` are the ordered complete
  activation union for audit and deterministic comparison, not loading.
- Preserve the v1 non-delegate selection in `selected_skills` and
  `selected_skill_details`. **selected_skills cannot be used as a preload list**.
- Preserve the v1 delegate-only compatibility view in `deferred_skills` and
  `deferred_skill_details`; phase loading comes only from `deferred_by_phase`.
- There must be zero or one `primary_controller`. If output contains more, stop
  and run the governance check; do not choose by intuition.
- `analysis` and `quick_fix` deliberately have no controller.
- `feature` is owned by `product-pipeline`.
- `implementation` and `incident` are owned by
  `health-harness-orchestrator`; incident also receives debugging capability.
- `release` is owned by exactly one target-specific terminal workflow.
- When Product Pipeline delegates S5 to Health Harness, reuse the same parent
  run and Dossier. Delegation does not create a second controller.
- Overlays may block a Gate but never own planning, checkpoints, or completion.

Before starting, state the selected mode and minimal Skill set in one concise
update. Then follow the selected adapter and repository hard rules. Do not
directly activate project-deprecated controllers such as `using-superpowers` or
`executing-plans`.
