# Dedao Authority Pack Dry Run

## Purpose

`dedao-kbase` can export `health_authority_pack_v1` JSONL for review. `health-llm-driven` treats that data as educational source material only; it does not write System KB rows or promote claims automatically.

## Import Boundary

Use `dry_run_import_dedao_authority_pack(lines)` from `app.services.system_kb.dedao_authority_import` to validate JSONL before any future reviewer workflow. The report separates `accepted_for_review`, `blocked`, `duplicates`, `invalid`, and `missing_source_refs`.

## Safety Rules

- Unknown contract versions are invalid.
- Missing `claim_id`, `book_id`, `source_hash`, or citations cannot enter review.
- Dedao-only records that request diagnosis, treatment, dosage, medication changes, emergency guidance, or generic action support are blocked.
- Dry run is side-effect free and always returns `would_write = False`.

## Verification

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/services/test_dedao_authority_import.py -q --no-cov
```
