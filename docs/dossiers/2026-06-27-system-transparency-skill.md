# Dossier: System Transparency Skill

> Status: implementation
> Date: 2026-06-27
> Branch: `codex/system-transparency-skill`
> Worktree: `/Users/liqiuhua/.config/superpowers/worktrees/health-llm-driven/system-transparency-skill`

## S0 Intake

User request:

> 按照你的规划实现一遍，注意Claude也在实现，你实现之后，再跟他做下对比，产出最优方案，独立一个分支开干。

Goal: implement a system transparency layer that lets Codex, Claude, and other
coding agents quickly understand the system goal, product capabilities, roadmap,
multi-surface product map, business/system flows, and requirement-to-deploy
workflow.

## S1 Discovery

Existing anchors:

- `AGENTS.md` defines Codex workflow preferences and the product pipeline entry.
- `docs/specs/product-pipeline-contract.md` defines the agent-neutral
  requirement-to-deploy contract.
- `docs/specs/reva-product-governance-spec.md` defines product admission,
  surface ownership, and first-class product objects.
- `docs/ARCHITECTURE.md` defines current implementation layers and CI.
- `.claude/skills/product-pipeline/SKILL.md` implements the product pipeline for
  Claude Code.

Gap: there was no single machine-readable map linking system goal, capabilities,
surfaces, implementation files, tests, and deploy routes.

## G1 Admission

```yaml
RequirementAdmission:
  request: system transparency skill and map
  classification: infrastructure
  first_user_fit: coding agents and product operators maintaining Reva
  core_loop_step: supports safer changes to the full data-to-action-to-verification loop
  first_class_objects:
    - HealthAgendaItem
    - LeverageAction
    - SafetyGuardian
    - HealthTwin
    - ExecutionEvent
  target_surface: docs-agent
  source_of_truth: docs/system-map.json
  safety_level: governance
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: repo source-of-truth docs and code paths
  claim_hedging: n/a
  verification_window: per commit
  success_metric: check_system_map and validate.py pass
  added_user_burden: none
  non_goals:
    - change runtime health behavior
    - replace product-pipeline-contract
    - add third-party parser dependency
  smallest_end_to_end_slice: map + skill + workflow + validation script
  stale_surface_to_remove_or_archive: none
  spec_required: no
```

Decision: PASS as governance/infrastructure work.

## S2/S3 Plan

1. Add a machine-readable `docs/system-map.json`.
2. Add a human-readable `docs/product-map.md`.
3. Add `docs/workflows/requirement-to-deploy.md` as the map-bound workflow view
   of the existing product pipeline contract.
4. Add `.claude/skills/system-transparency/SKILL.md`.
5. Add `scripts/check_system_map.py` and tests.
6. Wire the check into `scripts/validate.py`.
7. Compare with Claude WIP and capture the best merge direction.

## Gate Log

| Gate | Result | Evidence |
|---|---|---|
| Baseline validation | PASS | `backend/venv/bin/python scripts/validate.py` passed after installing Python 3.12 deps |
| RED test | PASS | `scripts/test_check_system_map.py` failed before `scripts/check_system_map.py` existed |
| GREEN test | PASS | `backend/venv/bin/python -m pytest scripts/test_check_system_map.py -q` |
| System map validation | PASS | `backend/venv/bin/python scripts/check_system_map.py` |
| Structural validation | PASS | `backend/venv/bin/python scripts/validate.py` |
| Claude comparison | PASS | No Claude system-map implementation was visible; best solution is this map layer plus existing `.claude/skills/product-pipeline` |

## Open Follow-Up

If Claude later produces a richer system-map artifact, compare it against
`docs/reports/2026-06-27-system-transparency-comparison.md` and merge only the
parts that improve capability coverage, validation strength, or maintenance
cost.
