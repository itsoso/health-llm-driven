---
name: system-transparency
description: "Use when changing product scope, planning capabilities, comparing PRD to implementation, onboarding an agent to Reva, or tracing a feature from system goal through surfaces, code, tests, CI, deployment, and verification."
---

# System Transparency

## Overview

Use the system map as the first operating surface before product or architecture
work. The map connects system goal, capabilities, surfaces, flows, code, tests,
deployment, and verification so agents do not re-discover the same context from
scratch.

## Required Read Order

1. Read `AGENTS.md` for hard engineering rules.
2. Read `docs/system-map.json` for capability, surface, code, test, and deploy
   anchors.
3. Read `docs/product-map.md` for human product context.
4. Read the capability source-of-truth docs listed in `source_of_truth`.
5. Read `docs/workflows/requirement-to-deploy.md` for implementation workflow.

If a feature is absent from `docs/system-map.json`, add it as `planned` or
`partial` before implementation, or explain why it is out of scope.

## Workflows

| Task | Do |
|---|---|
| Orient to the system | Summarize system goal, affected capability, owning surfaces, code paths, tests, deploy route. |
| Compare PRD and implementation | List PRD/Plan capabilities missing from `docs/system-map.json` or code/tests. |
| Plan a feature | Fill RequirementAdmission, bind it to a capability id, and name source-of-truth surface. |
| Implement a feature | Follow tests first, update code, update map, run system-map and structural gates. |
| Review another agent's work | Compare their files against `docs/system-map.json`; keep the version with stronger traceability and fewer new sources of truth. |
| Close out work | Run `python scripts/check_system_map.py` and `python scripts/validate.py`; report changed capability ids. |

## Capability Rules

Each capability in `docs/system-map.json` must have:

- `id`, `name`, `status`, `surfaces`, `source_of_truth`, `safety_level`, and
  `deploy_paths`;
- at least one PRD reference;
- code and test references when status is `implemented` or `partial`;
- surfaces that exist in the map;
- only paths that exist in the repo unless they are external URLs.

Status meanings:

| Status | Meaning |
|---|---|
| `implemented` | Working code, tests, and docs exist. |
| `partial` | Working slice exists, but product or coverage gaps remain. |
| `planned` | Accepted PRD/Plan exists; implementation not durable yet. |
| `gap` | Needed by strategy but not accepted or implemented yet. |
| `deprecated` | Exists but should not own new daily-loop behavior. |

## Failure Rules

- Missing source-of-truth path means STOP and update or remove the map entry.
- Product behavior without first-class object or core-loop mapping must be
  reframed before code.
- Sensitive health, medication, genotype, lab, CGM, symptom, red-flag, auth,
  CORS, or write-path changes still require the safety gate.
- Do not create a second workflow if `docs/specs/product-pipeline-contract.md`
  already governs it; link to it and add only map-specific guidance.

## Verification

Run:

```bash
python scripts/check_system_map.py
python scripts/validate.py
```

For Python worktrees without dependencies, create a Python 3.12 venv before
running structural gates:

```bash
/usr/local/bin/python3.12 -m venv backend/venv
backend/venv/bin/pip install -r backend/requirements.txt
backend/venv/bin/python scripts/validate.py
```
