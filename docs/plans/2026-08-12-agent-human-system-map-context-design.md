# Agent–Human System Map Context Design

> Status: approved
> Date: 2026-08-12
> Scope: make the existing code-derived System Map a shared global context for coding agents and administrators without turning it into a substitute for source code.

## 1. Decision

System Map is a dual-consumer transparency layer:

- administrators inspect the complete graph through `/admin/system-map`;
- coding agents use a compact generated summary for global orientation, query a task-specific graph slice, and then verify every material conclusion in source code and tests.

Both consumers use the same checked-in `docs/_generated/system-map.json`. The design does not create a second architecture database, an agent-only truth source, or another permission system.

The evidence order is fixed:

1. executable code, tests, runtime contracts, and registries;
2. code-derived System Map facts;
3. reviewed declarations with explicit coverage labels;
4. freshness-dated narrative documents.

The map is an index and context input. It is never sufficient evidence for runtime behavior by itself.

## 2. Problem

The complete graph is useful to humans but too large to preload into every agent context. Reading only a hand-written overview is cheap but can drift and does not expose task-specific upstream and downstream effects. Agents nevertheless need enough global context to avoid locally correct changes that break another client, flow, trust boundary, or data path.

The system therefore needs two generated views over one graph:

- a bounded global bootstrap view loaded for every task;
- a bounded task-specific neighborhood queried on demand.

## 3. Architecture

```text
source code + reviewed declarations
                  |
                  v
       dump_system_map.py
                  |
        +---------+-------------------+
        |                             |
        v                             v
system-map.json          system-map-agent-context.md
        |                             |
        |                    every agent bootstrap
        |
        +--> system_map_context.py --> scoped graph slice
        |
        +--> protected admin API --> /admin/system-map
```

### 3.1 Canonical graph

`docs/_generated/system-map.json` remains the canonical generated graph. Its schema, semantic validation, deterministic ordering, source metadata, and coverage metadata remain authoritative for everything that the generator claims to cover.

### 3.2 Compact global bootstrap

Add `docs/_generated/system-map-agent-context.md`. It is generated during the same operation as the canonical graph and must not be edited by hand.

The bootstrap contains only the information needed to understand the whole system:

- system-level components and their owner, source, data classes, lifecycle, and trust boundary;
- stable APIs, data stores, queues, caches, and external resources;
- key cross-component flows;
- coverage status and limitations;
- code-derived counts referenced directly from the canonical graph;
- an explicit instruction that agents must verify behavior in code and tests.

It does not enumerate every UI surface or background job. Those stay in the canonical graph and are retrieved through scoped queries.

The generated bootstrap has a hard size budget of 16 KiB. Exceeding the budget fails verification instead of silently dropping content.

### 3.3 Scoped graph query

Add a read-only CLI, `scripts/system_map_context.py`, with selectors for:

```bash
python3.12 scripts/system_map_context.py --path backend/app/api/
python3.12 scripts/system_map_context.py --entity component.mobile
python3.12 scripts/system_map_context.py --flow agent-chat
python3.12 scripts/system_map_context.py --keyword notification
```

The query result contains:

- matched entities;
- one layer of upstream and downstream relations by default, with an explicit maximum of two;
- associated flows, data classes, trust boundaries, and coverage labels;
- source paths and symbols that the agent should open next;
- coverage warnings for `partial` and `declaration` facts.

Results are deterministically ordered. The query tool reads the validated checked-in artifact and never writes repository files.

## 4. Agent context flow

Every coding agent follows this startup sequence:

1. read `AGENTS.md` for hard engineering rules;
2. read `docs/system-map/INDEX.md` for the navigation contract;
3. read the generated compact bootstrap for global context;
4. select a task-specific neighborhood by path, entity, flow, or keyword;
5. open the returned source paths, nearby tests, and relevant runtime contracts;
6. form a plan or make a judgment only after source verification.

This sequence is bound in `AGENTS.md`, `CLAUDE.md`, `docs/agent-skill-binding.md`, and `.claude/skills/system-map/SKILL.md` so Claude, Codex, Cursor, and other repository agents receive the same instructions.

No repository check can prove that a model read a document. The workflow contract can be made universal, while CI can only prove that the required artifacts and wiring are present and current. Documentation must state that distinction rather than claiming impossible enforcement.

## 5. Human context flow

Administrators continue to use `/admin/system-map`, protected by the existing administrator dependency. The page reads the complete canonical graph through the existing protected API and retains its filters, graph views, source details, and coverage display.

Agents read checked-in local artifacts and do not call the administrator API. This avoids coupling repository work to a running server or administrator credentials.

The generated bootstrap may also be read by humans, but it is optimized for bounded agent context rather than replacing the administrator graph.

## 6. Failure handling

### 6.1 Missing, invalid, or stale bootstrap

The agent must not use it. Run `./scripts/system-map-check.sh`. If verification fails, treat the map as unavailable and investigate code, tests, and registries directly. Do not continue reasoning from an older generated artifact.

### 6.2 Query has no match

Exit non-zero with an explicit “not indexed” result and suggest code search. Do not return an empty success response or invent a likely relation. The agent falls back to `rg` and source inspection.

### 6.3 Partial or declared coverage

Return the fact with a prominent warning and its `source.path`. The agent must verify the source before relying on the relation. A declared relationship is useful global context, but it is weaker evidence than a code-derived fact.

### 6.4 Result exceeds the context budget

Fail and ask the caller to narrow the selector. Never truncate nodes or relations silently, because truncation can hide an affected downstream system.

### 6.5 Newly discovered stable structure

When an agent changes a stable structure that is not yet modeled, it must add an appropriate code scanner or reviewed declaration, regenerate the artifacts, and pass the central gate. Merely mentioning the discovery in prose is insufficient.

## 7. Verification and tests

`./scripts/system-map-check.sh` remains the single blocking entry point and expands to verify:

- the compact bootstrap equals a fresh deterministic rendering of the canonical graph;
- the bootstrap remains within its size budget;
- component, resource, flow, coverage, and source sections are deterministically ordered;
- path, entity, flow, and keyword selectors return the expected neighborhood;
- default and maximum traversal depth are enforced;
- no-match, ambiguous, and oversized results fail explicitly;
- `partial` and `declaration` results include warnings;
- every returned fact provides a source path;
- agent bootstrap instructions remain wired through the repository agent entry points.

Existing JSON Schema, graph semantic validation, canonical artifact equality, Mobile navigation drift, and narrative-count checks remain in the same gate.

## 8. Security and privacy

- The compact bootstrap and query output expose structural metadata only, matching the canonical artifact.
- They must not include secrets, credentials, user records, health-record values, or environment contents.
- Human access to the complete graph remains administrator-only in the running product.
- Local agent access follows repository access and does not add an authentication mechanism.
- Coverage and source metadata remain visible so an agent can distinguish evidence strength and trust boundaries.

## 9. Rollout

1. Add failing tests for summary rendering, query behavior, budgets, and bootstrap wiring.
2. Extract pure graph rendering and query functions without changing the canonical graph schema.
3. Generate and commit the compact bootstrap.
4. Add the read-only query CLI.
5. Wire both outputs into the central System Map gate.
6. Update agent entry points and System Map documentation.
7. Run the central gate and focused backend tests, then verify the administrator view still consumes the canonical graph unchanged.

## 10. Non-goals

- Replacing source-code inspection with documentation retrieval.
- Loading the complete graph for every task.
- Adding embeddings, a vector database, or an LLM-generated architecture summary.
- Recording whether an agent actually read the bootstrap.
- Exposing the administrator graph to normal users.
- Creating a separate agent architecture schema or truth source.
