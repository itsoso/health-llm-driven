# System Map v2 Admin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the generated System Map to a deterministic entity-relation model and expose it only through the existing Reva administrator API and `/admin/system-map` page.

**Architecture:** Keep `docs/_generated/system-map.json` as the canonical generated artifact, extend it with versioned entities, relations, and coverage, and preserve the existing count/roster fields. Serve the validated artifact through a FastAPI endpoint protected by `get_admin_user`; render it in the existing Next.js admin application with a dependency-free SVG graph and the existing `AuthContext` gate.

**Tech Stack:** Python 3.12, AST/JSON Schema, FastAPI, pytest, Next.js 16, React 18, TanStack Query, Vitest, Testing Library, SVG, pre-commit, GitHub Actions.

---

## Execution rules

- Work on `main`, but stage and commit only files named by the current task.
- Preserve all unrelated dirty files and concurrent-session changes.
- Follow red-green-refactor: every behavior change starts with a failing targeted test.
- Never pipe tests to `tail`; read the real exit code.
- Do not deploy while the tree is dirty or `main` is not the exact reviewed SHA.
- Re-run `git status --short` before every commit.

### Task 1: Make existing registry discovery hermetic

**Files:**

- Create: `backend/tests/test_system_map_generator.py`
- Modify: `scripts/check_doc_drift.py`
- Modify: `scripts/dump_system_map.py`

**Step 1: Write failing AST discovery tests**

Add tests that import `scripts/check_doc_drift.py` and assert that registry discovery no longer imports backend runtime modules:

```python
def test_specialist_roster_is_derived_from_registry_source() -> None:
    roster = cdd.specialist_roster()
    assert "SafetyGuardianSpecialist" in roster
    assert roster == sorted(roster)
    assert cdd.count_specialists() == len(roster)


def test_twin_partition_roster_is_derived_from_schema_source() -> None:
    roster = cdd.twin_partition_roster()
    assert "physiological" in roster
    assert "meta" not in roster
    assert "gene_config" not in roster
    assert cdd.count_twin_partitions() == len(roster)
```

Also monkeypatch `builtins.__import__` to fail if an `app.*` import occurs during either scanner.

**Step 2: Run the tests and verify RED**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_system_map_generator.py -q
```

Expected: FAIL because `specialist_roster` and `twin_partition_roster` do not exist and current count functions import backend modules.

**Step 3: Implement minimal AST scanners**

In `scripts/check_doc_drift.py`:

- Parse `_build_registry()` and its returned constructor calls from `backend/app/orchestrator/specialists.py`.
- Parse annotated fields of `class HealthTwin` from `backend/app/twin/schema.py`.
- Exclude `meta` and `gene_config` from Twin partitions.
- Make `count_specialists()` and `count_twin_partitions()` delegate to the rosters.
- Remove `_prime_env()` and runtime backend imports from these discovery paths.

In `scripts/dump_system_map.py`, replace `_specialist_roster()` and `_twin_partition_roster()` runtime imports with the shared scanners.

**Step 4: Run targeted tests and existing doc-drift tests**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_system_map_generator.py tests/test_doc_drift_narrative_counts.py tests/test_doc_drift_skill_contract.py -q
```

Expected: PASS.

**Step 5: Verify the current generated artifact still matches**

Run:

```bash
python3.12 scripts/dump_system_map.py --check
python3.12 scripts/check_doc_drift.py
```

Expected: both exit `0`; existing counts and rosters are unchanged.

**Step 6: Commit**

```bash
git add backend/tests/test_system_map_generator.py scripts/check_doc_drift.py scripts/dump_system_map.py
git commit -m "refactor(system-map): make registry discovery hermetic"
```

### Task 2: Add the v2 schema and deterministic entity graph

**Files:**

- Create: `scripts/system_map_contract.py`
- Create: `docs/system-map/declarations.json`
- Create: `docs/_generated/system-map.schema.json`
- Modify: `backend/tests/test_system_map_generator.py`
- Modify: `scripts/dump_system_map.py`
- Modify: `docs/_generated/system-map.json`

**Step 1: Write failing contract tests**

Add tests for the desired contract:

```python
def test_build_map_emits_v2_graph() -> None:
    result = dump_system_map.build_map()
    assert result["schema_version"] == "2.0"
    assert result["entities"] == sorted(result["entities"], key=lambda item: item["id"])
    assert result["relations"] == sorted(
        result["relations"], key=lambda item: (item["from"], item["type"], item["to"])
    )
    validate_system_map(result)


def test_validator_rejects_dangling_relation() -> None:
    graph = minimal_valid_graph()
    graph["relations"].append({
        "from": "component.mobile",
        "type": "dependsOn",
        "to": "resource.missing",
        "source": {"type": "declaration", "path": "fixture"},
    })
    with pytest.raises(SystemMapContractError, match="unknown target"):
        validate_system_map(graph)
```

Cover duplicate IDs, unknown kinds, unknown relation types, missing source, and unsorted output.

**Step 2: Run and verify RED**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_system_map_generator.py -q
```

Expected: FAIL because the v2 fields and validator do not exist.

**Step 3: Implement the contract**

Define controlled values in `scripts/system_map_contract.py`:

```python
ENTITY_KINDS = {"component", "surface", "api", "resource", "job"}
RELATION_TYPES = {
    "partOf", "providesApi", "consumesApi", "dependsOn",
    "readsFrom", "writesTo", "publishesTo", "consumesFrom", "renders",
}
COVERAGE_VALUES = {"complete", "partial", "declaration"}
```

Keep the generator and graph-level contract on the Python standard library so discovery remains
independent of backend imports and machine-specific Pydantic versions. Check in
`docs/_generated/system-map.schema.json`, add semantic validation for unique IDs, unique
relations, resolved endpoints and deterministic sort order, and use the pinned `jsonschema`
runtime in Task 4 for Draft 2020-12 validation.

**Step 4: Add minimal declarations**

Create `docs/system-map/declarations.json` containing only stable component/resource/business-flow declarations that cannot be inferred safely. Do not include counts. Each declaration includes a source path and coverage mode.

Start with:

- Backend, Mobile, Frontend, Mac, Watch, MCP, Celery Worker and Celery Beat components.
- PostgreSQL, Redis, ChromaDB, APNs, HealthKit/Garmin and LLM provider resources.
- The stable high-level relations among those components and resources.

**Step 5: Extend the generator**

Update `build_map()` to:

- Preserve all existing count and roster fields.
- Load and validate declarations.
- Derive Web/Mobile surface entities from file routes.
- Derive Celery job entities from task decorators.
- Add source and coverage metadata.
- Sort entities and relations deterministically.
- Validate before serialization.

**Step 6: Run tests and generate artifacts**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_system_map_generator.py -q
cd .. && python3.12 scripts/dump_system_map.py
python3.12 scripts/dump_system_map.py --check
```

Expected: tests pass and the check confirms committed output equals fresh output.

**Step 7: Commit**

```bash
git add scripts/system_map_contract.py scripts/dump_system_map.py backend/tests/test_system_map_generator.py docs/system-map/declarations.json docs/_generated/system-map.schema.json docs/_generated/system-map.json
git commit -m "feat(system-map): generate v2 entity relations"
```

### Task 3: Add a hard check for the Mobile navigation graph

**Files:**

- Create: `scripts/test_mobile_nav_graph.py`
- Modify: `mobile/scripts/dump_nav_graph.py`

**Step 1: Write failing check-mode tests**

Import the navigation generator by file path and test a temporary committed output:

```python
def test_check_mode_does_not_write_and_fails_on_drift(tmp_path, monkeypatch) -> None:
    out = tmp_path / "mobile-nav-graph.json"
    out.write_text('{"stale": true}\n', encoding="utf-8")
    monkeypatch.setattr(nav, "OUT", out)
    before = out.read_bytes()
    assert nav.main(["--check"]) == 1
    assert out.read_bytes() == before
```

Add a matching-output success case.

**Step 2: Run and verify RED**

Run:

```bash
python3.12 -m pytest scripts/test_mobile_nav_graph.py -q
```

Expected: FAIL because `--check` currently rewrites the file and returns success.

**Step 3: Implement `--check`**

Add deterministic serialization and compare-without-write behavior matching
`scripts/dump_system_map.py --check`. Update the usage string.

**Step 4: Run tests and refresh the graph if required**

Run:

```bash
python3.12 -m pytest scripts/test_mobile_nav_graph.py -q
python3.12 mobile/scripts/dump_nav_graph.py --check
```

Expected: PASS and no file mutation in check mode.

**Step 5: Commit**

```bash
git add scripts/test_mobile_nav_graph.py mobile/scripts/dump_nav_graph.py docs/_generated/mobile-nav-graph.json
git commit -m "test(system-map): enforce mobile navigation drift"
```

### Task 4: Add the reproducible local verification harness

**Files:**

- Create: `scripts/system-map-requirements.txt`
- Create: `scripts/system-map-check.sh`
- Create: `scripts/check_system_map.py`
- Create: `scripts/test_system_map_harness.py`
- Modify: `.pre-commit-config.yaml`
- Modify: `.github/workflows/ci.yml`
- Modify: `scripts/validate.py`
- Modify: `backend/tests/test_harness_gate_wiring.py`

**Step 1: Write failing harness contract tests**

Assert that:

- The shell harness requires Python 3.12, creates/reuses `.venv`, and never uses system Python after activation.
- The central check calls System Map validation, generated equality, Mobile nav check and doc drift.
- pre-commit, CI and `scripts/validate.py` all call `scripts/check_system_map.py` or the wrapper rather than duplicating individual logic.

**Step 2: Run and verify RED**

Run:

```bash
python3.12 -m pytest scripts/test_system_map_harness.py backend/tests/test_harness_gate_wiring.py -q
```

Expected: FAIL because the harness files and wiring do not exist.

**Step 3: Add the minimal pinned harness environment**

Pin the single Draft 2020-12 validator used only by the System Map harness:

```text
jsonschema==4.23.0
```

`scripts/system-map-check.sh` must:

1. Resolve the repository root.
2. Require `python3.12` with an actionable error.
3. Create `.venv` if missing.
4. Install the pinned file only when its hash differs from a stamp in `.venv`.
5. Execute `.venv/bin/python scripts/check_system_map.py`.

It must not silently fall back to another Python version.

**Step 4: Implement the central checker**

`scripts/check_system_map.py` runs subprocesses without shell interpolation and propagates the first non-zero exit code:

```python
CHECKS = (
    ("system-map", [sys.executable, "scripts/dump_system_map.py", "--check"]),
    ("mobile-nav", [sys.executable, "mobile/scripts/dump_nav_graph.py", "--check"]),
    ("doc-drift", [sys.executable, "scripts/check_doc_drift.py"]),
)
```

Before subprocesses, load `system-map.json` and validate it with the shared contract.

**Step 5: Wire all local and CI gates**

- pre-commit: replace the direct doc-drift entry with `python3 scripts/check_system_map.py`.
- CI: rename the step to `Check System Map and doc drift` and run the same Python entry.
- `scripts/validate.py`: replace its doc-drift check with the central checker.

CI already installs backend dependencies; it must not bootstrap `.venv`. Only the human-facing shell wrapper bootstraps locally.

**Step 6: Run tests and the real wrapper**

Run:

```bash
python3.12 -m pytest scripts/test_system_map_harness.py backend/tests/test_harness_gate_wiring.py -q
./scripts/system-map-check.sh
```

Expected: all checks pass and a second wrapper run performs no dependency reinstall.

**Step 7: Commit**

```bash
git add scripts/system-map-requirements.txt scripts/system-map-check.sh scripts/check_system_map.py scripts/test_system_map_harness.py .pre-commit-config.yaml .github/workflows/ci.yml scripts/validate.py backend/tests/test_harness_gate_wiring.py
git commit -m "chore(system-map): add reproducible verification gate"
```

### Task 5: Add the admin-only System Map API

**Files:**

- Create: `backend/app/api/admin_system_map.py`
- Create: `backend/tests/test_admin_system_map.py`
- Modify: `backend/app/api/main.py`

**Step 1: Write failing permission and failure-mode tests**

Use the existing auth fixtures and an admin helper. Cover:

```python
def test_system_map_rejects_unauthenticated(client):
    assert client.get("/api/v1/admin/system-map").status_code == 401


def test_system_map_rejects_non_admin(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    assert client.get("/api/v1/admin/system-map", headers=headers).status_code == 403


def test_system_map_returns_valid_graph_to_admin(client, db):
    headers = _admin_headers(db)
    response = client.get("/api/v1/admin/system-map", headers=headers)
    assert response.status_code == 200
    assert response.json()["schema_version"] == "2.0"
```

Monkeypatch the artifact path for missing and invalid JSON cases; require an explicit `503`, never `{}` or a stale fallback.

**Step 2: Run and verify RED**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_admin_system_map.py -q
```

Expected: FAIL with route not found.

**Step 3: Implement the endpoint**

Create a router with a route-level admin dependency:

```python
router = APIRouter(dependencies=[Depends(get_admin_user)])

@router.get("", summary="获取管理员系统地图")
async def get_system_map(admin: User = Depends(get_admin_user)) -> dict:
    return load_validated_system_map()
```

Load the repository artifact with UTF-8 JSON, validate the top-level v2 contract, log failures without file contents, and raise `HTTPException(503, "系统地图暂不可用")` on missing/corrupt/invalid data.

Register the router under `/admin/system-map` in `backend/app/api/main.py`.

**Step 4: Run tests**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_admin_system_map.py -q
```

Expected: PASS for `401`, `403`, `200`, missing file and corrupt file cases.

**Step 5: Commit**

```bash
git add backend/app/api/admin_system_map.py backend/app/api/main.py backend/tests/test_admin_system_map.py
git commit -m "feat(admin): expose protected system map API"
```

### Task 6: Build and test the SVG graph primitive

**Files:**

- Create: `frontend/src/app/admin/system-map/types.ts`
- Create: `frontend/src/app/admin/system-map/graphLayout.ts`
- Create: `frontend/src/app/admin/system-map/graphLayout.test.ts`
- Create: `frontend/src/app/admin/system-map/SystemMapGraph.tsx`
- Create: `frontend/src/app/admin/system-map/SystemMapGraph.test.tsx`

**Step 1: Write failing deterministic layout tests**

Test that the same graph always produces the same coordinates, filtered-out nodes remove their incident relations, and unknown relation endpoints do not crash rendering.

**Step 2: Run and verify RED**

Run:

```bash
cd frontend && npm test -- src/app/admin/system-map/graphLayout.test.ts
```

Expected: FAIL because the module does not exist.

**Step 3: Implement the minimal layout**

Use fixed columns by kind and stable alphabetical ordering inside each column. Return a small view model:

```typescript
export interface PositionedEntity extends SystemMapEntity {
  x: number;
  y: number;
}
```

Do not implement zoom physics or a force simulation.

**Step 4: Write failing component tests**

Cover node labels, relation lines, coverage badges, selection callback and empty data.

**Step 5: Implement the SVG component**

Follow `KnowledgeGraphView.tsx`: pure SVG, controlled colors by entity kind, clickable nodes, accessible labels, and a details callback. Keep labels truncated visually but retain full names in `<title>` and accessibility text.

**Step 6: Run component tests**

Run:

```bash
cd frontend && npm test -- src/app/admin/system-map/graphLayout.test.ts src/app/admin/system-map/SystemMapGraph.test.tsx
```

Expected: PASS.

**Step 7: Commit**

```bash
git add frontend/src/app/admin/system-map/types.ts frontend/src/app/admin/system-map/graphLayout.ts frontend/src/app/admin/system-map/graphLayout.test.ts frontend/src/app/admin/system-map/SystemMapGraph.tsx frontend/src/app/admin/system-map/SystemMapGraph.test.tsx
git commit -m "feat(admin): add system map graph primitive"
```

### Task 7: Add `/admin/system-map` and retire the duplicate page

**Files:**

- Create: `frontend/src/app/admin/system-map/page.tsx`
- Create: `frontend/src/app/admin/system-map/page.test.tsx`
- Create: `frontend/src/app/admin/architecture/page.test.tsx`
- Modify: `frontend/src/app/admin/page.tsx`
- Modify: `frontend/src/app/admin/page.test.tsx`
- Replace: `frontend/src/app/admin/architecture/page.tsx`

**Step 1: Write failing page access tests**

Cover:

- Loading state renders no graph.
- Anonymous user redirects to `/login` and never calls the API.
- Non-admin redirects to `/` and never calls the API.
- Admin calls `/admin/system-map` and renders returned entities.
- API failure renders a visible retryable error.

**Step 2: Run and verify RED**

Run:

```bash
cd frontend && npm test -- src/app/admin/system-map/page.test.tsx
```

Expected: FAIL because the page does not exist.

**Step 3: Implement the page shell**

Use existing `useAuth`, `useRouter`, `useQuery` and `api`. Enable the query only when the authenticated user is an administrator:

```typescript
enabled: isAuthenticated && !!user?.is_admin
```

Add four tabs: system overview, dependency graph, business flows and map quality. Reuse the same graph data with tab-specific filters; do not create four independent data sources.

**Step 4: Add node details and filters**

Support entity kind, coverage, owner and data class filters. Selecting a node shows source path, coverage, upstream and downstream relations. The business-flow tab renders only declared flow groups and their related entities.

**Step 5: Replace the legacy architecture page**

Replace its hard-coded content with a server redirect:

```typescript
import { redirect } from 'next/navigation';

export default function ArchitectureRedirect() {
  redirect('/admin/system-map');
}
```

Test the redirect.

**Step 6: Update the Admin entry**

Change the Admin button label to `系统地图` and route to `/admin/system-map`. Extend `frontend/src/app/admin/page.test.tsx` to assert the admin-only entry uses the new path.

**Step 7: Run targeted frontend tests**

Run:

```bash
cd frontend && npm test -- src/app/admin/system-map src/app/admin/architecture/page.test.tsx src/app/admin/page.test.tsx
```

Expected: PASS.

**Step 8: Commit**

```bash
git add frontend/src/app/admin/system-map frontend/src/app/admin/architecture/page.tsx frontend/src/app/admin/architecture/page.test.tsx frontend/src/app/admin/page.tsx frontend/src/app/admin/page.test.tsx
git commit -m "feat(admin): add protected system map page"
```

### Task 8: Update System Map documentation and skill contract

**Files:**

- Modify: `docs/system-map/INDEX.md`
- Modify: `docs/system-map/product-map.md`
- Modify: `.claude/skills/system-map/SKILL.md`
- Modify: `docs/agent-skill-binding.md` only if its existing system-map binding needs a command update
- Modify: `backend/tests/test_doc_drift_skill_contract.py`

**Step 1: Write a failing skill-contract test**

Assert that the skill documents:

- `schema_version` plus entities and relations.
- `/admin/system-map` as the administrator view.
- `./scripts/system-map-check.sh` as the local entry.
- The boundary between generated structure and narrative.

**Step 2: Run and verify RED**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_doc_drift_skill_contract.py -q
```

Expected: FAIL because the existing skill still describes only counts and roster.

**Step 3: Update docs without manual live counts**

- Explain that v2 generated facts include typed entities, relations and coverage.
- Add the admin-only view to the read order.
- Document `system-map-check.sh`, Mobile nav hard check and coverage limitations.
- Remove the absolute “zero drift for the whole map” wording; scope it to generated fields.
- Update `last-reviewed` only on documents actually reviewed.

**Step 4: Run contract and drift tests**

Run:

```bash
cd backend && venv/bin/python -m pytest tests/test_doc_drift_skill_contract.py tests/test_doc_drift_narrative_counts.py -q
cd .. && ./scripts/system-map-check.sh
```

Expected: PASS.

**Step 5: Commit**

```bash
git add docs/system-map/INDEX.md docs/system-map/product-map.md .claude/skills/system-map/SKILL.md docs/agent-skill-binding.md backend/tests/test_doc_drift_skill_contract.py
git commit -m "docs(system-map): document v2 admin workflow"
```

Only include `docs/agent-skill-binding.md` if it actually changed.

### Task 9: Full verification, review, push and guarded deployment

**Files:** No planned source edits; fix only failures attributable to this feature.

**Step 1: Inspect scope before verification**

Run:

```bash
git status --short
git diff --stat HEAD~8..HEAD
```

Confirm no unrelated file was staged or committed by this work.

**Step 2: Run System Map and backend gates**

Run:

```bash
./scripts/system-map-check.sh
cd backend && venv/bin/python -m pytest tests/test_system_map_generator.py tests/test_admin_system_map.py tests/test_doc_drift_narrative_counts.py tests/test_doc_drift_skill_contract.py tests/test_harness_gate_wiring.py -q
```

Expected: PASS with zero failures.

**Step 3: Run frontend tests and production build**

Run:

```bash
cd frontend && npm test -- src/app/admin/system-map src/app/admin/architecture/page.test.tsx src/app/admin/page.test.tsx
npm run build
```

Expected: tests pass and Next production build exits `0`.

**Step 4: Run repository structural validation**

Run:

```bash
python3.12 scripts/validate.py
git diff --check
```

Expected: all blocking checks pass and no whitespace errors.

**Step 5: Perform a focused code review**

Review:

- Anonymous/non-admin denial is enforced server-side.
- No System Map response contains sensitive data.
- Generated order is deterministic.
- Dynamic discovery limitations are marked partial.
- The old page no longer duplicates architecture facts.
- No test hides a failure with a permissive fallback.

**Step 6: Push only when safe**

Before pushing, require:

- Clean working tree, or only explicitly acknowledged unrelated user files that are not part of the commits.
- Review the commits that are ahead of `origin/main`; do not push unrelated unknown commits automatically.
- `git fetch origin` and confirm no remote divergence.

If the branch is safe:

```bash
git push origin main
```

Otherwise stop and report the exact blocker.

**Step 7: Deploy only from a clean, exact main**

After push and only if the existing deployment preconditions pass:

```bash
./deploy.sh
```

Verify backend health, frontend health, administrator `200`, non-admin `403`, and the rendered `/admin/system-map` page. Do not perform Mobile OTA; this feature changes Web and Backend only.
