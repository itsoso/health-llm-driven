# Dedao Authority Pull Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a deterministic, read-only gate for live Dedao Health Authority Pack pull reports.

**Architecture:** Keep the existing fetch and dry-run importer as the source of truth. Add a small evaluator that converts a `DedaoAuthorityPullReport` into `pass`, `warn`, or `fail`, plus a redacted artifact safe for CI logs. Extend the CLI with gate and redacted-output flags without changing the default read-only behavior.

**Tech Stack:** Python dataclasses, existing `urllib` pull wrapper, pytest, existing `scripts/check_doc_drift.py`.

---

### Task 1: Gate Service

**Files:**
- Modify: `backend/app/services/system_kb/dedao_authority_import.py`
- Modify: `backend/tests/services/test_dedao_authority_import.py`

**Step 1: Write failing service tests**

Add tests that construct pull reports from fake openers and evaluate them:

```python
def test_pull_gate_passes_clean_report():
    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=lambda request, *, timeout: _FakeHTTPResponse(_line()),
    )
    gate = evaluate_dedao_authority_pull_gate(report)
    assert gate.status == "pass"
    assert gate.reasons == []
```

Add coverage for fetch failure, invalid JSONL, blocked-only records, and mixed accepted plus blocked records.

**Step 2: Run RED**

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
```

Expected: fail because `evaluate_dedao_authority_pull_gate` does not exist.

**Step 3: Implement minimal service**

Add:

```python
@dataclass(frozen=True)
class DedaoAuthorityPullGate:
    status: str
    reasons: list[str]
    fail_count: int
    warn_count: int
    pull_report: DedaoAuthorityPullReport

    def to_redacted_dict(self) -> dict[str, Any]:
        ...


def evaluate_dedao_authority_pull_gate(report: DedaoAuthorityPullReport) -> DedaoAuthorityPullGate:
    ...
```

Rules:

- `fail` if `report.status != "ok"`;
- `fail` if `invalid` has entries;
- `fail` if `accepted_for_review` is empty;
- `warn` if `blocked`, `duplicates`, or `missing_source_refs` has entries;
- `pass` otherwise.

Redaction must include only counts and issue refs: `claim_id`, `reason`, `line_no`.

**Step 4: Run GREEN**

Run the same pytest command. Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/system_kb/dedao_authority_import.py backend/tests/services/test_dedao_authority_import.py
git commit -m "feat(kb): add dedao authority pull gate"
```

### Task 2: CLI Gate Output

**Files:**
- Modify: `scripts/dedao_authority_pull_report.py`
- Modify: `docs/plans/2026-06-30-dedao-authority-import.md`

**Step 1: Write failing CLI tests or targeted callable checks**

Because this repo has no existing CLI test harness for this script, add small pure helpers if needed:

```python
def _exit_code_for_gate(status: str, *, fail_on_warn: bool) -> int:
    ...
```

Then test exit behavior through service tests, or keep CLI logic minimal enough to validate with `--help` plus service tests.

**Step 2: Implement CLI flags**

Add:

- `--gate`: print gate output instead of raw pull report;
- `--redacted-json`: print `gate.to_redacted_dict()` as JSON;
- `--fail-on-warn`: return non-zero for `warn`, not only `fail`.

Default behavior stays compatible: without `--gate`, the script prints the existing pull report.

**Step 3: Verify CLI help**

Run:

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python scripts/dedao_authority_pull_report.py --help
```

Expected: exit 0 and list the new flags.

**Step 4: Commit**

```bash
git add scripts/dedao_authority_pull_report.py docs/plans/2026-06-30-dedao-authority-import.md
git commit -m "feat(kb): expose dedao authority pull gate cli"
```

### Task 3: Verification

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
PATH=/Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin:$PATH python3 scripts/check_doc_drift.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python scripts/dedao_authority_pull_report.py --help
git diff --check
```

If the hook environment lacks Python dependencies, commit with the same venv path prepended so `python3 scripts/check_doc_drift.py` uses the verified interpreter.

### Task 4: Push

Push the existing branch:

```bash
git push origin codex/health-authority-pack-import
```
