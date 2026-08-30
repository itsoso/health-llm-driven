# Third-Party KBase Knowledge-to-Action Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Consume KBase `agent-package.v2` evidence packages as Health draft artifacts, preserve their provenance and evidence policy, and expose only manually approved claims to the existing reviewed System KB runtime.

**Architecture:** Extend the existing `DedaoKBaseReleaseClient` and draft workspace rather than adding a parallel RAG. The Health consumer validates only the v2 evidence contract needed for health review, ignores model/prompt/tool/UI execution policy, and keeps `draft/held/serving_allowed=false` until the existing claim review and publish gates complete. The existing `system_knowledge_evidence` card will carry the preserved provenance; no raw third-party body is added to user-facing payloads.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy services, pytest, JSON-compatible contract validation, existing System KB V2 artifact and review workspace.

---

### Task 1: Add failing v2 contract tests

**Files:**
- Modify: `backend/tests/test_dedao_kbase_release_consumer.py`
- Reference: `/Users/liqiuhua/work/personal/dedao-gui/contracts/agent-package-v2.schema.json`

**Step 1: Write the failing tests**

Add a v2 fixture containing the required package identity, pinned release, `evidence_policy`, evaluation report, and evidence-only safety policy. Add tests proving:

- a published v2 evidence package is accepted by `assess_agent_package_for_health`;
- missing `evidence_policy` is held with `invalid_evidence_policy`;
- a non-evidence-only release is held;
- package release roles must contain exactly one primary and at least one supporting release;
- `minimum_independent_sources`, `max_claims`, and `max_evidence_per_claim` are positive bounded values;
- model, prompt, tool, and UI policy fields are not copied into Health serving metadata;
- the projected claim preserves package lineage, policy snapshot, citation IDs, and `serving_allowed=false`.

**Step 2: Run tests to verify failure**

Run:

```bash
cd backend
./venv/bin/python -m pytest -q --no-cov tests/test_dedao_kbase_release_consumer.py -k 'v2 or evidence_policy' --tb=short
```

Expected: FAIL because the current consumer rejects `agent-package.v2` and does not validate or project `evidence_policy`.

### Task 2: Implement the Health-owned v2 validator and projection

**Files:**
- Modify: `backend/app/integrations/dedao_kbase_release_consumer.py`
- Test: `backend/tests/test_dedao_kbase_release_consumer.py`

**Step 1: Implement the minimum validator**

Keep v1 compatibility for existing fixtures. Add a v2 branch that validates only the Health boundary:

- schema version, package identity, lifecycle, pinned releases and release hashes;
- `safety_policy.usage_policy == evidence_only`;
- `evidence_policy.release_roles`, exactly one primary and at least one supporting role;
- positive bounded independent-source and claim/evidence limits;
- non-empty allowed verdicts and freshness policy;
- `report_schema == evidence-audit.v1`;
- evaluation identity, hash, thresholds and passed state.

Do not execute or import package model, prompt, tool, retrieval, or UI policy. Those remain KBase authoring metadata and are not trusted Health runtime controls.

**Step 2: Project policy safely**

Add a bounded `evidence_policy` snapshot to the draft package manifest and Claim metadata. Copy only release IDs, roles, source-count limits, freshness limits, allowed verdicts, report schema, and the package/release hashes. Never copy source bodies or execution policy.

**Step 3: Run focused tests**

Run:

```bash
cd backend
./venv/bin/python -m pytest -q --no-cov tests/test_dedao_kbase_release_consumer.py -k 'v2 or evidence_policy' --tb=short
```

Expected: all new v2 tests pass.

### Task 3: Add draft sync receipt and fail-closed regression coverage

**Files:**
- Modify: `backend/tests/test_dedao_kbase_release_consumer.py`
- Inspect/modify only if required: `backend/app/tasks/system_knowledge_lifecycle.py`

**Step 1: Add sync-level tests**

Cover the existing `sync_dedao_kbase_agent_packages_draft_once` path with a v2 package and assert:

- the package is written only to the isolated review workspace;
- the report gate remains `serving_allowed=false`;
- the cursor and package receipt are idempotent;
- malformed v2 policy is reported as held and cannot replace a prior valid projection;
- superseded or withdrawn packages do not remain serving candidates.

**Step 2: Run the sync tests**

Run:

```bash
cd backend
./venv/bin/python -m pytest -q --no-cov tests/test_dedao_kbase_release_consumer.py -k 'sync_dedao_kbase_agent_packages_draft_once or v2' --tb=short
```

Expected: all selected tests pass with no database or serving-index mutation.

### Task 4: Verify existing citation-card compatibility

**Files:**
- Test: `backend/tests/test_system_knowledge_phase0.py`
- Test: `backend/tests/test_agent_executor_system_knowledge_prompt.py`
- Inspect: `backend/app/services/system_knowledge_service.py`

**Step 1: Add a narrow regression test**

Use a reviewed synthetic v2-derived Claim and assert the existing evidence card includes the source URL, release ID, Claim ID, risk level, and review provenance without a raw source body.

**Step 2: Run the focused runtime tests**

```bash
cd backend
./venv/bin/python -m pytest -q --no-cov \
  tests/test_system_knowledge_phase0.py \
  tests/test_agent_executor_system_knowledge_prompt.py \
  --tb=short
```

Expected: existing card behavior remains green and no third-party body is serialized.

### Task 5: Update the implementation dossier and run release checks

**Files:**
- Modify: `docs/plans/2026-08-16-third-party-kbase-knowledge-to-action-design.md`
- Create/modify: `docs/dossiers/2026-08-17-third-party-kbase-knowledge-to-action.md`

Record the implementation state, Gate results, source-contract assumptions, and explicit non-goals. Do not claim a third-party pilot is live until an authorized source and an actual approved Claim exist.

Run:

```bash
cd backend
./venv/bin/python -m pytest -q --no-cov \
  tests/test_dedao_kbase_release_consumer.py \
  tests/test_system_knowledge_phase0.py \
  tests/test_agent_executor_system_knowledge_prompt.py \
  --tb=short
python -m py_compile app/integrations/dedao_kbase_release_consumer.py
git diff --check
```

Expected: all selected tests pass; compile and diff checks are clean. No deploy, OTA, App Store mutation, or production source ingestion is part of this implementation batch.
