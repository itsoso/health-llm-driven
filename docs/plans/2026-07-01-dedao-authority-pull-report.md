# Dedao Authority Pull Report Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only health-side pull report for live dedao-kbase Health Authority Pack JSONL.

**Architecture:** Extend the existing `dedao_authority_import` service with a fetch-and-dry-run wrapper, using stdlib `urllib` and dependency injection for tests. Add a thin CLI script that reads environment variables, calls the wrapper, and prints sanitized JSON or text.

**Tech Stack:** Python dataclasses, stdlib `urllib.request`, pytest, existing `scripts/check_doc_drift.py`.

---

### Task 1: Pull Report Service

**Files:**
- Modify: `backend/app/services/system_kb/dedao_authority_import.py`
- Modify: `backend/tests/services/test_dedao_authority_import.py`

**Step 1: Write failing tests**

Add tests that call `dry_run_import_dedao_authority_pack_from_kbase` with fake openers:

```python
def test_pull_report_fetches_jsonl_and_preserves_token_privacy():
    report = dry_run_import_dedao_authority_pack_from_kbase(
        "https://kbase.example",
        "secret-token",
        opener=fake_success_opener,
    )
    assert report.status == "ok"
    assert report.import_report.accepted_for_review
    assert "secret-token" not in json.dumps(report.to_dict())
```

Also cover HTTP 401 and invalid JSONL.

**Step 2: Run RED**

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
```

Expected: fail because the pull wrapper does not exist.

**Step 3: Implement minimal service**

Add:

- `DedaoAuthorityPullReport`
- `build_dedao_authority_pack_export_url`
- `fetch_dedao_authority_pack_jsonl`
- `dry_run_import_dedao_authority_pack_from_kbase`

Return sanitized errors such as `http_401`, `missing_base_url`, or `missing_token`.

**Step 4: Run GREEN**

Run the same pytest command. Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/system_kb/dedao_authority_import.py backend/tests/services/test_dedao_authority_import.py
git commit -m "feat(kb): pull dedao authority pack dry run"
```

### Task 2: CLI Report

**Files:**
- Create: `scripts/dedao_authority_pull_report.py`
- Modify: `docs/plans/2026-06-30-dedao-authority-import.md`

**Step 1: Write CLI script**

The script should:

- insert `backend/` into `sys.path`;
- read `DEDAO_KBASE_BASE_URL` and `DEDAO_KBASE_TOKEN`;
- support `--base-url`, `--token`, `--limit`, `--json`;
- call the pull wrapper;
- print a sanitized report.

**Step 2: Verify CLI import/help**

```bash
/Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python scripts/dedao_authority_pull_report.py --help
```

Expected: exit 0 and no token output.

**Step 3: Commit**

```bash
git add scripts/dedao_authority_pull_report.py docs/plans/2026-06-30-dedao-authority-import.md
git commit -m "feat(kb): add dedao authority pull report cli"
```

### Task 3: Verification

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python scripts/check_doc_drift.py
/Users/liqiuhua/work/personal/health-llm-driven/backend/.venv/bin/python scripts/dedao_authority_pull_report.py --help
git diff --check
```

Then push `codex/health-authority-pack-import`.
