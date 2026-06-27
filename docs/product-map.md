# Reva Product Map

> Status: v1 baseline
> Updated: 2026-06-27
> Machine entry: `docs/system-map.json`
> Validation: `python scripts/check_system_map.py`

This document is the human-readable companion to `docs/system-map.json`. It does
not replace the PRD, architecture, or product pipeline contract. It gives humans
and coding agents one place to understand the current product map before making
product or architecture changes.

## 1. System Goal

Reva is a Personal Health OS. Its long-term goal is to help at least 10 million
people improve their health through a daily loop of real personal data, safe
interpretation, executable actions, and outcome verification.

The durable asset is not chat history or dashboard usage. It is the per-user
causal ledger:

```text
what was observed
  -> what was recommended
  -> what was safety-gated
  -> what was executed
  -> what changed
  -> what should be tried next
```

## 2. Product Capability Map

| Capability | Status | Owning surfaces | Source of truth |
|---|---|---|---|
| Requirement admission and product governance | Implemented | Docs/Agent | `docs/specs/reva-product-governance-spec.md` |
| Health Agenda and high-leverage action loop | Partial | Backend, Mobile, Watch | `backend/app/services/agenda_service.py` |
| Fast capture for diet, exercise, meds, supplements, symptoms, measurements | Partial | Backend, Mobile, Watch, External agents | `backend/app/api/quick_record.py`, `mobile/app/(tabs)/record.tsx` |
| Chat plus dynamic UI cards | Partial | Backend, Mobile, Web | `backend/app/services/agent_executor.py`, `mobile/app/reva.tsx` |
| Apple Watch ask Reva and quick record loop | Partial | Backend, Watch, Mobile | `backend/app/api/watch.py`, `apps/watch/` |
| HealthKit automatic import and wearable routing | Partial | Backend, Mobile | `backend/app/services/device_adapters/healthkit.py` |
| Deterministic Safety Guardian | Implemented | Backend, clients, external agents | `backend/app/agents/safety_guardian/` |
| System transparency map and workflow | Implemented | Docs/Agent | `docs/system-map.json`, `.claude/skills/system-transparency/SKILL.md` |

Status vocabulary:

| Status | Meaning |
|---|---|
| Implemented | Has code, tests, and source-of-truth docs in the system map. |
| Partial | Has a working slice but still has known product or coverage gaps. |
| Planned | Has accepted PRD/Plan but no durable implementation yet. |
| Gap | Needed by the product thesis but not accepted or implemented yet. |
| Deprecated | Still exists but should not receive new daily-loop ownership. |

## 3. Surface Map

| Surface | Role | Owns | Must not own |
|---|---|---|---|
| Backend | Product source of truth | Health Twin, Safety Gate, Agenda, WriteIntent, audit, data ownership | Client-local health decisions |
| Mobile | Primary daily product | Today, Agenda, Capture, Programs, Review, consent/settings | Admin-heavy debugging or long file triage |
| Apple Watch | Low-friction execution | top action, due item, confirm/later/skip, quick voice/food/symptom/exercise | long reports, complex editing, independent recommendations |
| Mac | Workbench | file/lab import, long agent workflows, trace review, release ops | replacing the mobile daily loop |
| Web | Admin/history/doctor/family | reports, history, compatibility, operations | primary consumer daily loop |
| External agents | Controlled extension | documented skills/APIs with auth and audit | bypassing safety or unmanaged writes |
| Docs/Agent | Operating map | PRD, plans, architecture, workflows, system transparency, validation gates | stale prose that cannot be checked |

## 4. Business Flow

```text
Personal data
  -> Health Twin
  -> deterministic Safety Gate
  -> leverage action ranking
  -> Agenda / Watch / Mobile execution
  -> ExecutionEvent
  -> retest or outcome review
  -> next action with better personal evidence
```

Every non-trivial feature should strengthen at least one step in this flow. If
it does not, it should be reframed as infrastructure, archived, or rejected.

## 5. System Flow

```text
Requirement
  -> RequirementAdmission
  -> Feature Spec or PRD/Plan
  -> docs/system-map.json capability update
  -> implementation across owning surfaces
  -> tests and safety gates
  -> CI/deploy/OTA/TestFlight route
  -> production or device verification
  -> update product map and Dossier
```

The machine-readable contract for this flow is `docs/system-map.json`. The
implementation workflow is `docs/workflows/requirement-to-deploy.md`.

## 6. How Agents Should Use This Map

1. Read `AGENTS.md` first for hard engineering rules.
2. Read `docs/system-map.json` to locate the affected capability, surfaces,
   code paths, tests, and deploy route.
3. Read `docs/product-map.md` for the human product context.
4. Read the capability source-of-truth docs listed in the map.
5. If adding or changing a non-trivial product behavior, update the map in the
   same branch and run `python scripts/check_system_map.py`.

If a capability exists in PRD or Plan but cannot be represented in
`docs/system-map.json`, the work is not transparent enough for autonomous
implementation.
