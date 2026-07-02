# Dedao Authority Pack Dry Run

## Purpose

`dedao-kbase` can export `health_authority_pack_v1` JSONL for review. `health-llm-driven` treats that data as educational source material only; it does not write System KB rows or promote claims automatically.

## Import Boundary

Use `dry_run_import_dedao_authority_pack(lines)` from `app.services.system_kb.dedao_authority_import` to validate JSONL before any future reviewer workflow. The report separates `accepted_for_review`, `blocked`, `duplicates`, `invalid`, and `missing_source_refs`.

The importer accepts both legacy flat source fields (`book_id`, `citations`, `source_hash`) and enriched `source_refs` from dedao-kbase. Review candidates preserve `review_status`, `risk_reason`, and `entity_candidates` for reviewer triage.

Use `dry_run_import_dedao_authority_pack_from_kbase(base_url, token)` or the CLI report to pull the live dedao-kbase export. The pull report is read-only, sanitizes errors, and does not include Bearer tokens in output.

Use `evaluate_dedao_authority_pull_gate(report)` when the caller needs an unattended pass/warn/fail decision. The gate is still read-only: it wraps the pull report, counts findings, and emits redacted issue refs without raw Dedao record payloads.

## Safety Rules

- Unknown contract versions are invalid.
- Missing `claim_id`, `book_id`, `source_hash`, or citations cannot enter review.
- Records with `review_status = blocked` are blocked even if source refs are present.
- Dedao-only records that request diagnosis, treatment, dosage, medication changes, emergency guidance, or generic action support are blocked.
- Dry run is side-effect free and always returns `would_write = False`.

## Verification

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
```

Generate a live dry-run report:

```bash
DEDAO_KBASE_BASE_URL=https://kbase.executor.life \
DEDAO_KBASE_TOKEN=... \
backend/venv/bin/python scripts/dedao_authority_pull_report.py --json
```

Generate a redacted gate artifact for automation:

```bash
DEDAO_KBASE_BASE_URL=https://kbase.executor.life \
DEDAO_KBASE_TOKEN=... \
backend/venv/bin/python scripts/dedao_authority_pull_report.py --gate --redacted-json
```

Write the same redacted gate artifact to a file for CI or scheduled jobs:

```bash
DEDAO_KBASE_BASE_URL=https://kbase.executor.life \
DEDAO_KBASE_TOKEN=... \
backend/venv/bin/python scripts/dedao_authority_pull_report.py \
  --redacted-output artifacts/dedao-authority-gate.json
```

Add `--fail-on-warn` when a CI caller should reject packs with blocked, duplicate, or missing-source records even if accepted review candidates are present.
