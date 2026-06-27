# System Transparency Comparison

> Date: 2026-06-27
> Codex branch: `codex/system-transparency-skill`
> Compared Claude artifacts: `.claude/skills/product-pipeline/SKILL.md` and
> currently visible `.claude/worktrees/*`

## 1. What Was Available To Compare

I searched current Claude worktrees and the main workspace for:

- `system-map`
- `product-map`
- `system transparency`
- `系统透明`
- `check_system_map`

No Claude worktree contained a new system-map implementation at the time of this
comparison. The three Claude worktrees with uncommitted changes only had
`mobile/node_modules` as untracked files. The meaningful Claude-side artifact to
compare against is therefore the existing `.claude/skills/product-pipeline`
implementation.

## 2. Claude Product Pipeline Strengths

Claude's existing `product-pipeline` Skill is strong at lifecycle orchestration:

- clear double-loop model: definition loop and delivery loop;
- six gates from requirement admission to live verification;
- Dossier as resumable state spine;
- explicit safety, deploy, and verification gates;
- good routing to existing deploy, OTA, TestFlight, and safety skills.

It should remain the source of truth for end-to-end product delivery flow.

## 3. Missing Layer

The existing pipeline does not give an agent a single machine-readable answer to:

- what capabilities exist;
- which surfaces own each capability;
- which PRD/spec/plan governs it;
- which code and tests implement it;
- which deploy path applies;
- whether a capability is implemented, partial, planned, gap, or deprecated.

Agents can infer these by searching, but that repeats work and makes cross-agent
handoff fragile.

## 4. Codex Implementation

This branch adds the missing horizontal map:

- `docs/system-map.json`: machine-readable system, surface, capability,
  workflow, source-of-truth, test, and deploy map;
- `docs/product-map.md`: human-readable product map;
- `docs/workflows/requirement-to-deploy.md`: map-bound view of the existing
  product pipeline contract;
- `.claude/skills/system-transparency/SKILL.md`: agent read/update workflow;
- `scripts/check_system_map.py`: fail-loud validation for map shape and path
  references;
- `scripts/test_check_system_map.py`: regression tests for the validator;
- `scripts/validate.py`: adds `system-map` as a blocking structural gate;
- `AGENTS.md`: makes the map a Codex-readable entry point.

## 5. Best Combined Solution

The best solution is not to replace Claude's `product-pipeline`. The best
solution is:

```text
AGENTS.md
  -> docs/system-map.json
  -> docs/product-map.md
  -> docs/specs/reva-product-governance-spec.md
  -> docs/specs/product-pipeline-contract.md
  -> .claude/skills/product-pipeline
  -> .claude/skills/system-transparency
  -> scripts/check_system_map.py + scripts/validate.py
```

Division of responsibility:

| Layer | Owner |
|---|---|
| Engineering hard rules | `AGENTS.md` and `docs/governance/*` |
| Product admission | `docs/specs/reva-product-governance-spec.md` |
| Requirement-to-deploy lifecycle | `docs/specs/product-pipeline-contract.md` |
| Claude delivery orchestration | `.claude/skills/product-pipeline/SKILL.md` |
| System capability/surface map | `docs/system-map.json` |
| Agent read/update workflow | `.claude/skills/system-transparency/SKILL.md` |
| Drift prevention | `scripts/check_system_map.py` and `scripts/validate.py` |

This keeps the existing lifecycle gates intact and adds the missing transparent
map layer agents need for fast, repeatable implementation.

## 6. Recommendation

Adopt this branch as the base implementation. If Claude later produces a richer
system-map artifact, merge only the parts that improve:

- capability coverage;
- per-surface ownership accuracy;
- source-of-truth references;
- validation strength;
- lower maintenance burden.

Avoid accepting prose-only expansions that cannot be checked by
`scripts/check_system_map.py`.
