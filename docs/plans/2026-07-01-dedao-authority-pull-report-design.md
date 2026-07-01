# Dedao Authority Pull Report Design

## Goal

Give `health-llm-driven` a repeatable way to pull the live Dedao Health Authority Pack and produce a dry-run validation report for Aheng. This closes the gap between `dedao-kbase` export and Health System KB review without adding any write path.

## Scope

Add a small health-side pull layer that:

- reads a dedao-kbase base URL and Bearer token from caller-provided arguments or environment variables;
- fetches `/api/projects/health/authority-pack/export?format=jsonl`;
- feeds the JSONL into the existing `dry_run_import_dedao_authority_pack`;
- returns a structured report with accepted, blocked, duplicate, invalid, and missing-source counts;
- never writes System KB tables and never prints tokens.

## Data Flow

```
dedao-kbase authority-pack JSONL
  -> health pull function
  -> dry_run_import_dedao_authority_pack
  -> structured dry-run report
  -> CLI JSON/text output for CI or operator use
```

## Error Handling

HTTP failures should return a report with `status = fetch_failed`, `http_status` when known, and no token-bearing details. Invalid JSONL remains an import-level finding, not a fetch failure.

## Testing

Use TDD with fake HTTP responses. Cover success, authorization header attachment, token non-leakage, HTTP 401, invalid JSONL, and blocked upstream records.
