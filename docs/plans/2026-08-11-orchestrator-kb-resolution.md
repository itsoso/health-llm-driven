# Orchestrator Turn-Scoped KB Resolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make each non-lite Orchestrator turn resolve system knowledge once, reuse the same snapshot for finding evidence and synthesis, remove healthy-path cross-review duplication, and expose stage latency without changing medical or routing behavior.

**Architecture:** Add a backward-compatible precomputed-result seam to `EvidenceResolver`, split System KB rendering into a pure lookup-result formatter, and create one turn-scoped KB resolution in both non-streaming and streaming Orchestrator paths. Represent cross-review as `None | "" | rendered block`, resolve failures once before synthesis, and record actual Twin/KB/cross-review/IQS wall time in the existing performance audit.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Pydantic, asyncio, pytest, pytest-asyncio.

---

### Task 1: Make EvidenceResolver perform at most one lookup per batch

**Files:**
- Modify: `backend/tests/test_system_knowledge_v2_pipeline.py`
- Modify: `backend/app/services/evidence_resolver.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_v2_pipeline.py`

**Step 1: Write failing lookup-cardinality tests**

Add tests that spy on `lookup_for_twin` and assert:

```python
assert lookup_calls == 1  # two applicable findings
assert both_findings_have_expected_resolution_metadata
```

Also add parameterized cases for an empty list and all-`not_applicable` findings; both must keep `lookup_calls == 0`.

**Step 2: Write the failing precomputed-zero-hit test**

Pass `lookup_result={"claims": []}` to `attach_system_knowledge_evidence` and make the lookup spy raise if called. Assert the finding remains `model_inference`, `unsupported=True`, and no retry occurs. This proves the implementation uses `is None`, not truthiness.

**Step 3: Run the exact tests to verify RED**

Run:

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_system_knowledge_v2_pipeline.py \
  -k 'single_lookup or precomputed_zero_hit or not_applicable_without_lookup' \
  -q --no-cov
```

Expected: FAIL because the optional lookup-result API does not exist and multiple applicable findings perform multiple queries.

**Step 4: Implement lazy single lookup and compatibility seam**

Add an optional `lookup_result` argument to `resolve_for_finding`, `apply_to_findings`, and `attach_system_knowledge_evidence`.

Implementation requirements:

- only `lookup_result is None` may trigger a lookup;
- `apply_to_findings` lazily looks up on the first applicable finding and reuses the result;
- empty/all-not-applicable batches do not query;
- existing metadata, ordering, deduplication, and item-level evidence propagation remain unchanged;
- return stats may add lookup/resolution counts but must preserve current keys.

**Step 5: Run the focused tests to verify GREEN**

Run the command from Step 3. Expected: all selected tests pass.

### Task 2: Extract a pure System KB prompt formatter

**Files:**
- Modify: `backend/tests/test_system_knowledge_v2_pipeline.py`
- Modify: `backend/app/services/system_knowledge_service.py`
- Test: `backend/tests/test_system_knowledge_v2_pipeline.py`

**Step 1: Write failing formatter-equivalence tests**

Build a fixed lookup result and assert the new pure formatter:

- matches the existing wrapper output;
- preserves result input unchanged;
- preserves claim order and `CLAIM_BOUNDARY`;
- obeys `max_claims` and `max_chars`;
- returns `""` for empty claims.

**Step 2: Run the exact tests to verify RED**

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_system_knowledge_v2_pipeline.py \
  -k 'format_system_knowledge_result' \
  -q --no-cov
```

Expected: FAIL because `format_system_knowledge_result_for_prompt` does not exist.

**Step 3: Extract the pure formatter**

Implement:

```python
def format_system_knowledge_result_for_prompt(
    result: dict[str, Any],
    max_claims: int = 6,
    max_chars: int = 1500,
) -> str:
    ...
```

Keep `format_system_knowledge_for_prompt(db, twin, ...)` as the public DB wrapper and delegate to the pure function after one `lookup_for_twin` call.

**Step 4: Run the formatter and existing System KB tests**

Run the Step 2 command, then:

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_system_knowledge_v2_pipeline.py \
  -q --no-cov
```

Expected: all tests pass.

### Task 3: Encode cross-review's three states without losing failure recovery

**Files:**
- Create: `backend/tests/test_orchestrator_context_reuse.py`
- Modify: `backend/app/orchestrator/orchestrator.py`
- Test: `backend/tests/test_orchestrator_context_reuse.py`

**Step 1: Write failing three-state prompt tests**

Call `_build_synthesis_prompt` with:

- `None`: fallback detector called exactly once;
- `""`: detector never called and no conflict block appears;
- a non-empty rendered block: detector never called and the block appears unchanged.

**Step 2: Write the failing detection-exception test**

Make the initial `detect_conflicts` raise. Assert `_run_cross_review_and_arbitration` returns `None`, not `""`. Then resolve the fallback to a final string and assert the same final string is supplied to both prompt construction and the parallel-synthesis call seam.

**Step 3: Run the exact tests to verify RED**

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_orchestrator_context_reuse.py \
  -k 'cross_review' \
  -q --no-cov
```

Expected: FAIL because empty precomputed results currently trigger detection and errors are collapsed into empty strings.

**Step 4: Implement the three-state contract**

- Change `_build_synthesis_prompt(..., conflict_arb_block: Optional[str] = None)`.
- Run fallback only when `conflict_arb_block is None`.
- Extract the current rule-layer fallback into a reusable helper.
- Return `None` from `_run_cross_review_and_arbitration` on detection failure and `""` on successful no-conflict detection.
- In both Orchestrator entry paths, resolve `None` before mega/parallel/shadow synthesis receives the block.

**Step 5: Run the tests to verify GREEN**

Run the command from Step 3. Expected: all selected tests pass.

### Task 4: Add turn-scoped KB resolution and non-streaming metrics

**Files:**
- Modify: `backend/tests/test_orchestrator_context_reuse.py`
- Modify: `backend/app/orchestrator/orchestrator.py`
- Test: `backend/tests/test_orchestrator_context_reuse.py`

**Step 1: Write the failing non-stream integration test**

Use two deterministic applicable findings and a lookup spy. Capture `log_orchestrator_run(..., perf_breakdown=...)`. Assert:

```python
assert lookup_calls == 1
assert perf["kb_lookup_count"] == 1
assert perf["kb_lookup_ok"] is True
assert perf["kb_claim_count"] >= 0
assert perf["kb_lookup_reuse_count"] >= 1
assert "twin_wall_ms" in perf
assert "cross_review_ms" in perf
assert "iqs_ms" in perf
```

Also assert each finding's evidence resolution and the prompt KB block derive from the same lookup result.

**Step 2: Write the failing lite-path test**

Force no specialists and assert lookup count/reuse/count claims are zero while the existing lite prompt path remains intact.

**Step 3: Run the exact tests to verify RED**

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_orchestrator_context_reuse.py \
  -k 'nonstream or lite' \
  -q --no-cov
```

Expected: FAIL because the Orchestrator still performs per-finding plus prompt lookups and lacks the metrics.

**Step 4: Implement `_TurnKBResolution` and non-stream wiring**

- Measure `build_twin` wall time without replacing `twin.meta.build_ms`.
- Compute `lite_mode = not specialists` at the existing semantic boundary.
- Resolve the KB once on the healthy path using a caller-bind-compatible, independently owned Session; allow at most one controlled exception retry without rolling back the caller Session.
- Treat service import and Twin-payload mapping failures as zero-attempt fail-soft results.
- Pass the result to evidence attachment and the pre-rendered text to the prompt builder.
- Record KB, cross-review, and IQS metrics in `perf` and the single-line operational log.
- Do not log query text, Twin values, claims, or other health content.

**Step 5: Run the tests to verify GREEN**

Run the Step 3 command. Expected: all selected tests pass.

### Task 5: Apply identical reuse and metrics to streaming

**Files:**
- Modify: `backend/tests/test_orchestrator_context_reuse.py`
- Modify: `backend/tests/test_orchestrator_stream_persistent.py`
- Modify: `backend/app/orchestrator/orchestrator.py`
- Test: `backend/tests/test_orchestrator_context_reuse.py`
- Test: `backend/tests/test_orchestrator_stream_persistent.py`

**Step 1: Write the failing stream parity test**

Drain one stream turn and parse SSE. Capture both the `done` payload and `log_orchestrator_run`. Assert:

- exactly one healthy-path lookup for multiple applicable findings;
- `done.perf` and audit carry the same KB/Twin/cross-review/IQS fields;
- a successful empty cross-review result is not detected twice;
- stream output and terminal event shape remain unchanged.

**Step 2: Run the exact test to verify RED**

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_orchestrator_context_reuse.py \
  tests/test_orchestrator_stream_persistent.py \
  -k 'stream and (kb or perf or cross_review)' \
  -q --no-cov
```

Expected: FAIL because stream has no centralized KB snapshot or new stage metrics.

**Step 3: Implement stream parity**

Reuse the same helper and metric definitions in `_background_task`. Keep background-session ownership, SSE ordering, persistence, safety wrapping, and disconnect behavior unchanged.

**Step 4: Run the tests to verify GREEN**

Run the Step 2 command. Expected: all selected tests pass.

### Task 6: Run focused and repository gates

**Files:**
- Modify: `docs/dossiers/2026-08-11-orchestrator-kb-resolution.md`

**Step 1: Run focused behavior suites**

```bash
cd backend
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/pytest \
  tests/test_orchestrator_context_reuse.py \
  tests/test_orchestrator.py \
  tests/test_orchestrator_stream_persistent.py \
  tests/test_orchestrator_parallel_synthesis.py \
  tests/test_system_knowledge_v2_pipeline.py \
  tests/test_cross_review.py \
  -q --no-cov
```

Expected: all tests pass.

**Step 2: Run static and document gates**

```bash
git diff --check
/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m compileall -q \
  backend/app/orchestrator/orchestrator.py \
  backend/app/services/evidence_resolver.py \
  backend/app/services/system_knowledge_service.py
PATH="/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin:$PATH" \
  python3 scripts/check_doc_drift.py
PATH="/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin:$PATH" \
  python3 backend/scripts/check_dossier_consistency.py
```

Expected: every command exits 0.

**Step 3: Update the Dossier with exact evidence**

Record RED/GREEN tests, regression counts, review findings, commit SHA, and the fact that push/deploy remained blocked until the other Sessions released their windows. Do not claim G5/G6 before actual deployment and production verification.

**Step 4: Request an independent code review**

Ask a read-only reviewer to inspect the final diff for safety-semantic changes, duplicate lookup regressions, cross-review failure behavior, metric accuracy, and concurrency conflicts. Resolve material findings with new failing tests first.

**Step 5: Commit only this slice**

Stage only the files listed in this plan and commit with:

```bash
git commit -m "perf(orchestrator): reuse turn-scoped knowledge"
```

Do not push, merge, or deploy until the release Session confirms its production/EAS lock is released and the semantic-query Session's integration state has been rechecked.
