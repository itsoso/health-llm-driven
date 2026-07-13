# KBase Persistent Review Workspace Design

## Problem

Dedao Knowledge Releases are currently compiled into the repository-owned
`backend/data/system_kb_v2_seed` directory. A later deployment replaces that
directory from Git while the database cursor still records the Release as
consumed. The draft then disappears and incremental sync incorrectly reports
`up_to_date`.

## Decision

Use a dedicated persistent review workspace, configured by
`DEDAO_KBASE_REVIEW_ARTIFACT_DIR`. The repository seed remains the canonical
base and is never mutated by Release sync. The review workspace stores the
merged base plus immutable Releases until review and publication complete.

Every successful sync records both the Release cursor and a deterministic
fingerprint of the canonical base. A sync performs a full rebuild when the
workspace is missing, its metadata is invalid, or the canonical fingerprint
changes. Rebuild starts from the current canonical seed and replays all
published Releases from the beginning. Otherwise the consumer fetches only
records after the last cursor.

## Data Flow

1. Hash the canonical artifact files.
2. Read the latest successful KBAudit cursor and workspace metadata.
3. Choose incremental sync only when workspace and base fingerprint agree.
4. For rebuild, compile all Releases against the canonical seed into a
   temporary sibling directory, then atomically replace the workspace.
5. Write draft metadata and KBAudit only after the workspace is complete.
6. Validate every required JSONL file against manifest counts before treating a
   workspace as incremental-safe; reject an all-empty workspace.
7. Review returns an exact content fingerprint. Approval must submit that same
   fingerprint and rechecks it while holding the workspace lock.
8. Review and publish APIs operate on the persistent workspace. Serving tables
   remain unchanged until explicit approval and publish.

## Failure Behavior

- Network, schema, compilation, or filesystem failures do not advance cursor.
- A missing workspace never returns `up_to_date`; it triggers replay.
- A failed rebuild leaves the previous workspace intact.
- Interrupted replacement is recovered from a sibling backup under the shared
  review/sync/publish lock.
- A stale review fingerprint fails approval and requires a fresh preview.
- A review workspace resolving to the canonical seed or overlapping its path
  tree is rejected.
- No Release feedback is emitted merely because a draft was synchronized.

## Production Layout

- Canonical seed: `/opt/health-app/backend/data/system_kb_v2_seed`
- Persistent review workspace: `/var/lib/health-app/dedao-kbase-review`
- Cursor and fingerprint: `KBAudit` plus workspace metadata

## Verification

Tests cover workspace deletion, canonical base change, audit/workspace cursor
drift, manifest-count corruption, incremental idempotency, failed rebuild
preservation, replacement recovery, cross-service locking, stale review
fingerprints, path alias rejection, review-path selection, and
deployment-independent configuration. Production verification must sync,
restart/redeploy, and prove the draft and cursor remain available before
approval.
