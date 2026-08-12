# Agent–Human System Map Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give every coding agent a bounded code-derived global System Map context plus a read-only task-specific graph query, while keeping the administrator graph and canonical JSON unchanged.

**Architecture:** docs/_generated/system-map.json remains the only canonical graph. Pure functions in scripts/system_map_context.py render a compact Markdown bootstrap and select bounded graph neighborhoods. scripts/dump_system_map.py writes and checks the bootstrap beside the canonical JSON, and the existing central gate validates both.

**Tech Stack:** Python 3.12, argparse, deterministic Markdown rendering, pytest, the existing JSON Schema/System Map contract, and repository documentation gates.

**Required protocols:** Read AGENTS.md, docs/system-map/INDEX.md, .claude/skills/system-map/SKILL.md, and docs/plans/2026-08-12-agent-human-system-map-context-design.md. Use @test-driven-development for behavior changes and @verification-before-completion before claiming success. Work on main per repository policy unless the user changes that choice. Stage only files listed for the current task and preserve unrelated dirty files.

---

### Task 1: Add the deterministic compact context renderer

**Files:**
- Create: scripts/system_map_context.py
- Create: backend/tests/test_system_map_agent_context.py

**Step 1: Write the failing renderer tests**

Create a minimal local graph fixture containing components, an API, a resource, a surface, relations, coverage limitations, and fake counts. Add tests equivalent to:

~~~python
from system_map_context import AGENT_CONTEXT_MAX_BYTES, render_agent_context

def test_render_agent_context_is_deterministic_and_global(minimal_graph):
    first = render_agent_context(minimal_graph)
    assert first == render_agent_context(minimal_graph)
    assert "DO NOT EDIT" in first
    assert "component.backend-api" in first
    assert "resource.postgresql" in first
    assert "agent-chat" in first
    assert "partial" in first
    assert "backend/app/api/main.py" in first
    assert "surface.mobile.home" not in first
    assert len(first.encode("utf-8")) <= AGENT_CONTEXT_MAX_BYTES

def test_render_agent_context_uses_canonical_counts(minimal_graph):
    text = render_agent_context(minimal_graph)
    for key, value in minimal_graph["counts"].items():
        assert f"{key}: {value}" in text
~~~

Keep fake counts inside the fixture. Never assert live architecture counts in narrative or tests.

**Step 2: Run tests and verify RED**

Run:

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_system_map_agent_context.py -q --no-cov
~~~

Expected: collection fails because scripts/system_map_context.py does not exist.

**Step 3: Implement the minimal pure renderer**

Create scripts/system_map_context.py with standard-library-only imports and these public contracts:

~~~python
ROOT = Path(__file__).resolve().parent.parent
SYSTEM_MAP_PATH = ROOT / "docs" / "_generated" / "system-map.json"
AGENT_CONTEXT_MAX_BYTES = 16 * 1024
GLOBAL_KINDS = {"component", "api", "resource"}

class SystemMapContextError(ValueError):
    pass

def render_agent_context(graph: dict[str, Any]) -> str:
    # Render evidence order, sorted global entities, sorted key flows,
    # coverage limitations, source paths, and canonical counts.
    # Exclude individual surface and job listings.
    # Raise SystemMapContextError when UTF-8 output exceeds the budget.
    ...
~~~

Every rendered entity and relation must include coverage and source metadata. The header must say the file is generated and behavior must be verified in code and tests. Sort entities by ID, relations by from/type/to, flows and coverage areas alphabetically, and counts by key.

**Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all renderer tests pass.

**Step 5: Add the hermetic import test**

Guard builtins.__import__ against app and app.* while importing and invoking system_map_context. Expected: rendering works without importing backend runtime modules.

**Step 6: Commit Task 1**

~~~bash
git add scripts/system_map_context.py backend/tests/test_system_map_agent_context.py
git commit -m "feat(system-map): render compact agent context"
~~~

---

### Task 2: Generate and drift-check the compact bootstrap

**Files:**
- Modify: scripts/dump_system_map.py:23-30,220-240
- Modify: scripts/check_system_map.py:15-45
- Modify: backend/tests/test_system_map_generator.py:85-96
- Modify: backend/tests/test_system_map_agent_context.py
- Create: docs/_generated/system-map-agent-context.md

**Step 1: Write failing artifact tests**

Monkeypatch both output paths into tmp_path and assert that one writer creates canonical JSON and Markdown derived from that JSON:

~~~python
def test_write_artifacts_writes_json_and_agent_context(monkeypatch, tmp_path):
    graph_out = tmp_path / "system-map.json"
    context_out = tmp_path / "system-map-agent-context.md"
    monkeypatch.setattr(dsm, "OUT", graph_out)
    monkeypatch.setattr(dsm, "AGENT_CONTEXT_OUT", context_out)

    graph = dsm.build_map()
    dsm.write_artifacts(graph)

    assert json.loads(graph_out.read_text()) == graph
    assert context_out.read_text() == render_agent_context(graph)
~~~

Add a check-mode test that changes one byte in the Markdown artifact and expects a non-zero result with a regeneration instruction.

**Step 2: Run focused tests and verify RED**

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_system_map_generator.py   backend/tests/test_system_map_agent_context.py -q --no-cov
~~~

Expected: FAIL because AGENT_CONTEXT_OUT and write_artifacts do not exist.

**Step 3: Integrate both generated outputs**

In scripts/dump_system_map.py import render_agent_context and add:

~~~python
AGENT_CONTEXT_OUT = ROOT / "docs" / "_generated" / "system-map-agent-context.md"

def write_artifacts(graph: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(_serialize(graph), encoding="utf-8")
    AGENT_CONTEXT_OUT.write_text(render_agent_context(graph), encoding="utf-8")

def check_artifacts(graph: dict) -> tuple[bool, str]:
    if not OUT.exists() or not AGENT_CONTEXT_OUT.exists():
        return False, "System Map generated artifact missing"
    if json.loads(OUT.read_text(encoding="utf-8")) != graph:
        return False, "system-map.json differs from code"
    if AGENT_CONTEXT_OUT.read_text(encoding="utf-8") != render_agent_context(graph):
        return False, "system-map-agent-context.md differs from canonical graph"
    return True, ""
~~~

Make main call these helpers. Check mode must stay read-only.

In scripts/check_system_map.py compare the committed Markdown with render_agent_context(artifact) inside the blocking contract check. Handle SystemMapContextError alongside existing validation errors.

**Step 4: Run focused tests and verify GREEN**

Run Step 2. Expected: PASS.

**Step 5: Generate and validate the artifacts**

~~~bash
python3.12 scripts/dump_system_map.py
./scripts/system-map-check.sh
wc -c docs/_generated/system-map-agent-context.md
git diff -- docs/_generated/system-map.json docs/_generated/system-map-agent-context.md
~~~

Expected: the Markdown stays within 16 KiB and the central gate passes. The canonical JSON should change only if this task legitimately changed its source facts. Stop if unrelated dirty work altered it.

**Step 6: Commit Task 2**

~~~bash
git add scripts/dump_system_map.py scripts/check_system_map.py   backend/tests/test_system_map_generator.py   backend/tests/test_system_map_agent_context.py   docs/_generated/system-map-agent-context.md
git commit -m "feat(system-map): generate agent bootstrap"
~~~

Add docs/_generated/system-map.json only when this task itself legitimately changed it.

---

### Task 3: Add bounded graph queries

**Files:**
- Modify: scripts/system_map_context.py
- Modify: backend/tests/test_system_map_agent_context.py

**Step 1: Write failing query tests**

Cover all selectors and failure modes:

~~~python
def test_entity_query_includes_one_hop_neighbors(minimal_graph):
    result = query_graph(minimal_graph, entity="component.mobile")
    assert {item["id"] for item in result.entities} == {
        "component.mobile", "api.health-v1"
    }
    assert result.relations
    assert result.sources

def test_flow_query_selects_only_that_flow(minimal_graph):
    result = query_graph(minimal_graph, flow="agent-chat")
    assert all("agent-chat" in rel.get("flows", []) for rel in result.relations)

def test_path_query_matches_source_prefix(minimal_graph):
    assert query_graph(minimal_graph, path="mobile/").entities

def test_keyword_query_is_case_insensitive(minimal_graph):
    assert query_graph(minimal_graph, keyword="POSTGRES").entities

def test_declared_evidence_warns(minimal_graph):
    text = render_query_result(
        query_graph(minimal_graph, entity="component.mobile")
    )
    assert "VERIFY SOURCE" in text

def test_no_match_fails(minimal_graph):
    with pytest.raises(SystemMapContextError, match="not indexed"):
        query_graph(minimal_graph, keyword="does-not-exist")

def test_depth_above_two_fails(minimal_graph):
    with pytest.raises(SystemMapContextError, match="depth"):
        query_graph(minimal_graph, entity="component.mobile", depth=3)

def test_oversized_result_fails_instead_of_truncating(minimal_graph):
    with pytest.raises(SystemMapContextError, match="narrow"):
        query_graph(minimal_graph, keyword="component", max_entities=1)
~~~

**Step 2: Run tests and verify RED**

Run the Task 1 focused command. Expected: FAIL because query functions do not exist.

**Step 3: Implement deterministic bounded traversal**

Add:

~~~python
@dataclass(frozen=True)
class QueryResult:
    entities: tuple[dict[str, Any], ...]
    relations: tuple[dict[str, Any], ...]
    sources: tuple[str, ...]
    warnings: tuple[str, ...]

def query_graph(
    graph: dict[str, Any],
    *,
    path: str | None = None,
    entity: str | None = None,
    flow: str | None = None,
    keyword: str | None = None,
    depth: int = 1,
    max_entities: int = 50,
) -> QueryResult:
    # Require exactly one selector.
    # Select seeds strictly from canonical fields.
    # Traverse only existing relation endpoints for 0, 1, or 2 layers.
    # Sort IDs and relation keys before returning.
    # Raise on no seeds or too many entities; never infer or truncate.
    ...
~~~

Implement render_query_result as deterministic Markdown containing entity metadata, relations, unique source paths, and warnings. Every entity or relation whose coverage is not complete adds a VERIFY SOURCE warning.

**Step 4: Add the read-only CLI**

Use argparse with one required mutually exclusive selector, depth choices 0/1/2, and max-entities. Load the checked-in JSON, call validate_system_map, print Markdown to stdout, and return exit code 2 for expected context/contract errors. Do not catch unexpected exceptions and never write files.

**Step 5: Verify unit and CLI behavior**

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_system_map_agent_context.py -q --no-cov

python3.12 scripts/system_map_context.py --entity component.mobile
python3.12 scripts/system_map_context.py --flow agent-chat
python3.12 scripts/system_map_context.py --path backend/app/api/
python3.12 scripts/system_map_context.py --keyword notification
python3.12 scripts/system_map_context.py --keyword __not_indexed__
test $? -ne 0
~~~

Expected: known queries print bounded source-linked context; the unknown query exits non-zero with an explicit not-indexed message.

**Step 6: Commit Task 3**

~~~bash
git add scripts/system_map_context.py backend/tests/test_system_map_agent_context.py
git commit -m "feat(system-map): query bounded agent context"
~~~

---

### Task 4: Wire the bootstrap into every agent entry path

**Files:**
- Modify: backend/tests/test_doc_drift_skill_contract.py:6-30
- Modify: AGENTS.md:616-635
- Modify: CLAUDE.md:5-18
- Modify: docs/agent-skill-binding.md:1-64
- Modify: docs/system-map/INDEX.md:1-55
- Modify: .claude/skills/system-map/SKILL.md

**Step 1: Write the failing wiring contract**

Add paths for AGENTS.md, CLAUDE.md, and docs/agent-skill-binding.md. Assert every entry point contains docs/_generated/system-map-agent-context.md. Assert INDEX and the System Map skill contain scripts/system_map_context.py, a code-and-test verification rule, and the evidence order. Never assert live architecture counts.

**Step 2: Run the contract test and verify RED**

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_doc_drift_skill_contract.py -q --no-cov
~~~

Expected: FAIL because the generated bootstrap path is not wired everywhere.

**Step 3: Update the startup protocol**

Document this exact sequence:

1. Read AGENTS.md.
2. Read docs/system-map/INDEX.md.
3. Read docs/_generated/system-map-agent-context.md for bounded global context.
4. Query the relevant neighborhood with scripts/system_map_context.py.
5. Open returned source paths and tests before planning or deciding.

Also state:

- compact Markdown and query results are derived views, not truth sources;
- complete JSON remains canonical;
- CI verifies freshness and wiring but cannot prove a model read a file;
- missing/stale context triggers scripts/system-map-check.sh and direct code investigation;
- administrators use /admin/system-map while coding agents read local artifacts.

Bump last-reviewed on changed narrative documents. Do not add manual live counts.

**Step 4: Run contract and narrative drift tests**

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_doc_drift_skill_contract.py   backend/tests/test_doc_drift_narrative_counts.py -q --no-cov
~~~

Expected: PASS.

**Step 5: Commit Task 4**

~~~bash
git add AGENTS.md CLAUDE.md docs/agent-skill-binding.md   docs/system-map/INDEX.md .claude/skills/system-map/SKILL.md   backend/tests/test_doc_drift_skill_contract.py
git commit -m "docs(system-map): require global agent bootstrap"
~~~

---

### Task 5: Run the complete gate and review the result

**Files:**
- Modify only if a verified gap exists: scripts/check_system_map.py
- Modify only if a verified gap exists: backend/tests/test_harness_gate_wiring.py
- No planned product runtime changes.

**Step 1: Check central gate wiring**

Inspect backend/tests/test_harness_gate_wiring.py. Reuse existing assertions proving pre-commit, CI, and scripts/validate.py reach the central System Map check. Add a failing assertion only if the compact context is not actually reached through that path.

**Step 2: Run the focused backend suite**

~~~bash
env DATABASE_URL='sqlite:///:memory:' SKIP_DB_INIT=1   backend/venv/bin/python -m pytest   backend/tests/test_system_map_generator.py   backend/tests/test_system_map_agent_context.py   backend/tests/test_admin_system_map.py   backend/tests/test_doc_drift_narrative_counts.py   backend/tests/test_doc_drift_skill_contract.py   backend/tests/test_harness_gate_wiring.py -q --no-cov
~~~

Expected: PASS. Administrator API tests prove the protected endpoint still serves the validated canonical graph.

**Step 3: Run reproducible and repository gates**

~~~bash
./scripts/system-map-check.sh
python3.12 scripts/validate.py
git diff --check
git status --short
~~~

Expected: all blocking checks pass. Existing ruff report-only output does not fail the gate. Confirm unrelated dirty files remain unstaged.

**Step 4: Self-review**

Verify that:

- canonical JSON is still the only graph truth source;
- the bootstrap contains no hand-written live facts;
- traversal never invents edges or silently truncates;
- every query result includes source paths;
- partial/declaration evidence warns the agent;
- no credentials, user records, health values, or environment contents are rendered;
- the administrator endpoint remains unchanged.

**Step 5: Commit any final gate-only correction**

If a real gap required changes:

~~~bash
git add scripts/check_system_map.py backend/tests/test_harness_gate_wiring.py
git commit -m "test(system-map): enforce agent context gate"
~~~

Do not create an empty commit.

**Step 6: Refresh and push main safely**

~~~bash
git fetch origin
git rev-list --left-right --count origin/main...HEAD
git log --oneline origin/main..HEAD
git log --oneline HEAD..origin/main
~~~

Push only if there is no remote divergence and the ahead commits are exactly the reviewed System Map commits:

~~~bash
git push origin main
~~~

No backend/web deployment or Mobile OTA is required because this plan changes repository tooling, generated documentation, tests, and agent instructions only. Re-evaluate this if the implementation diff later contains product runtime code.
