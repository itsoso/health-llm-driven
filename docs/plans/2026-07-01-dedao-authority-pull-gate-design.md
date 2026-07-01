# Dedao Authority Pull Gate Design

## Goal

Turn the existing Dedao Authority Pull Report into a deterministic gate that Aheng can run without a human in the loop. The gate should decide whether the current `dedao-kbase` Health Authority Pack is safe enough to enter review workflows.

## Scope

Add a read-only gate layer in `health-llm-driven` that:

- wraps the existing pull report and dry-run importer;
- returns `pass`, `warn`, or `fail` with explicit reasons;
- emits a redacted machine-readable artifact for CI or operators;
- exits non-zero only when configured gate rules fail;
- never writes System KB rows and never exports Dedao source text or Bearer tokens.

## Gate Rules

The first version should be conservative:

- `fail` when the pack cannot be fetched, has invalid records, or has no accepted review candidates.
- `warn` when records are blocked, duplicated, or missing source references but at least one review candidate is usable.
- `pass` when fetch succeeds and all parsed records are acceptable for review.

Callers can choose stricter failure behavior with CLI flags, but the default should avoid blocking on warnings while still making them visible.

## Data Flow

```
dedao-kbase JSONL export
  -> existing pull report
  -> existing dry-run importer
  -> pull gate evaluator
  -> redacted JSON/text output
  -> optional CI exit code
```

## Artifact Contract

The redacted output should include:

- gate status and reason list;
- fetch status and HTTP status;
- total, accepted, blocked, duplicate, invalid, and missing-source counts;
- compact issue refs with `claim_id`, `reason`, and `line_no`;
- no raw record payloads, source excerpts, authorization headers, or tokens.

## Error Handling

Fetch errors remain sanitized as `http_401`, `network_error`, `missing_base_url`, or `missing_token`. Invalid JSONL is an import finding and should become a gate failure without hiding valid line-level findings.

## Testing

Use TDD around the service evaluator and CLI:

- success produces `pass` and exit code `0`;
- fetch failure produces `fail` and exit code `1`;
- invalid JSONL produces `fail`;
- blocked-only input produces `fail` because no accepted candidate exists;
- mixed accepted plus blocked records produces `warn` by default;
- redacted JSON does not include secret tokens or raw record text.
