---
doc: architecture/dedao-kbase-reva-sync
last-reviewed: 2026-06-27
---

# dedao-kbase -> Reva System KB Sync

## Decision

`dedao-kbase` is an authoring and compiler plane. Reva remains the reviewed serving plane.

Do not wire health agents to query `dedao-kbase` raw notes, Obsidian pages, or MCP search at runtime. Runtime health guidance must read from Reva's reviewed System KB tables through the existing `system_knowledge_service` paths.

## Source Boundary

The only supported cross-repo input for this path is:

```text
<dedao-kbase>/artifacts/system_kb_export.json
```

The same export may also be fetched over the private kbase HTTP service:

```text
https://kbase.executor.life/api/system-kb/export
Authorization: Bearer <DEDAO_KBASE_AUTH_TOKEN>
```

The HTTP path is a transport for the reviewed export contract, not a runtime search authority. Health agents still serve from Reva's reviewed local System KB tables after import and review.

The importer intentionally does not scan the rest of the repo. This avoids accidental ingestion of:

- raw Dedao course text;
- Obsidian working notes;
- personal/L3 health material;
- sidecar artifacts that were not explicitly exported for System KB review.

`ak-kbase` and `down-dedao` can both play the `dedao-kbase` role if they emit this export contract.

## Export Contract

Recommended top-level fields:

```json
{
  "type": "system_kb_v2_export",
  "schema_id": "llm-wiki-v2-system-kb-export",
  "version": "git-or-compiler-version",
  "source": "dedao-kbase",
  "source_repo": "git@github.com:owner/dedao-kbase.git",
  "source_commit": "abcdef0",
  "compiled_at": "2026-06-27T10:00:00+00:00",
  "license_scope": "internal_transformed_claims",
  "pages": [],
  "entities": [],
  "claims": [],
  "relations": []
}
```

Each document should carry enough provenance to audit it later:

- `source_file` or `source_path`
- `sources`
- `content_hash`
- `evidence_level`
- `confidence`
- `metadata.license_scope`

The Reva importer normalizes every row with:

- `metadata.origin = dedao-kbase-export`
- `metadata.source_repo`
- `metadata.source_commit`
- `metadata.source_path`
- `metadata.review_status = draft`

## Reva Import Flow

Dry-run. The CLI default source is `DEDAO_KBASE_ROOT` or `/Users/liqiuhua/work/personal/down-dedao`; pass `--source-root` for another kbase repo.

```bash
cd /Users/liqiuhua/work/personal/health-llm-driven
DATABASE_URL=sqlite:///./backend/dedao_kbase_export_ingest_cli.db \
PYTHONPATH=backend \
backend/venv/bin/python backend/scripts/ingest_dedao_kbase_export.py \
  --source-root /Users/liqiuhua/work/personal/down-dedao \
  --artifact-dir backend/data/system_kb_v2_seed \
  --json-summary
```

Write draft artifacts:

```bash
DATABASE_URL=sqlite:///./backend/dedao_kbase_export_ingest_cli.db \
PYTHONPATH=backend \
backend/venv/bin/python backend/scripts/ingest_dedao_kbase_export.py \
  --source-root /Users/liqiuhua/work/personal/down-dedao \
  --artifact-dir backend/data/system_kb_v2_seed \
  --write \
  --json-summary
```

Promote after human review:

```bash
DATABASE_URL=sqlite:///./backend/dedao_kbase_export_ingest_cli.db \
PYTHONPATH=backend \
backend/venv/bin/python backend/scripts/ingest_dedao_kbase_export.py \
  --source-root /Users/liqiuhua/work/personal/down-dedao \
  --artifact-dir backend/data/system_kb_v2_seed \
  --write \
  --promote-reviewed \
  --reviewer clinician:<reviewer-id> \
  --json-summary
```

Online kbase mode. This is the preferred production transport when the kbase server is deployed at `kbase.executor.life`.

```bash
DATABASE_URL=sqlite:///./backend/dedao_kbase_export_ingest_cli.db \
PYTHONPATH=backend \
DEDAO_KBASE_AUTH_TOKEN="<private-token>" \
backend/venv/bin/python backend/scripts/ingest_dedao_kbase_export.py \
  --export-url https://kbase.executor.life/api/system-kb/export \
  --artifact-dir backend/data/system_kb_v2_seed \
  --write \
  --json-summary
```

Scheduled online sync. Reva can also poll the private kbase export on a weekly Celery beat. This task only writes draft artifacts and a KB audit row; it does not promote anything into serving without the existing human review and release gate.

Required settings:

```text
DEDAO_KBASE_EXPORT_URL=https://kbase.executor.life/api/system-kb/export
DEDAO_KBASE_AUTH_TOKEN=<private-token>
SYSTEM_KB_ARTIFACT_DIR=/opt/health-app/backend/data/system_kb_v2_seed
```

Task:

```text
app.tasks.system_knowledge_lifecycle.sync_dedao_kbase_export_draft
```

Then run the normal release gate:

```bash
DATABASE_URL=sqlite:///./backend/system_kb_release_gate.sqlite3 \
SECRET_KEY=test-secret-key-32-chars-minimum!! \
GARMIN_ENCRYPTION_KEY=mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU= \
PYTHONPATH=backend \
backend/venv/bin/python backend/scripts/run_external_health_knowledge_release_gate.py \
  --artifact-dir backend/data/system_kb_v2_seed \
  --reset-db \
  --json
```

## MCP Role

An MCP server for `dedao-kbase` is useful only as a control plane:

- compile export;
- list changed sources;
- fetch manifest and source commit;
- open review items.

It must not become a runtime medical authority. Runtime agent tools should continue to wrap Reva's reviewed local KB, not third-party or raw-kbase search.

## Implementation Anchors

- Import service: `backend/app/services/dedao_kbase_export_importer.py`
- CLI: `backend/scripts/ingest_dedao_kbase_export.py`
- Scheduled draft sync: `backend/app/tasks/system_knowledge_lifecycle.py`
- Draft/review gate: `backend/app/services/system_knowledge_ingest.py`
- Serving import gate: `backend/app/services/system_knowledge_importer.py`
- Serving lookup filter: `backend/app/services/system_knowledge_service.py`
- Tests: `backend/tests/test_dedao_kbase_export_importer.py`
