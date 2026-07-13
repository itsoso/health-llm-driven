# KBase Claim Adjudication Design

## Problem

The persistent Dedao review workspace is now deployment-safe, but its approval
surface is still release-wide. The current draft contains medical claims backed
only by the source article at evidence level C. A reviewer must not be forced to
promote every extracted claim merely to finish the Release.

## Decision

Add claim-level adjudication to the existing System KB Review Console. A draft
claim can be approved, held for evidence, or excluded from Health serving.
Approval and publication remain separate commands; the console in this slice
can finalize a reviewed Release and preview publication, but cannot publish it.

## Adjudication Model

- `approve`: keep the claim, optionally append structured external evidence,
  and mark it reviewed.
- `needs_evidence`: keep the claim draft and record why it remains blocked.
- `reject`: remove the claim from the publish candidate.
- `background_only`: remove the claim from Health serving while retaining the
  decision in the workspace ledger; the original source remains in KBase.

Only claims require manual decisions. Release entity/page containers are marked
reviewed during finalization after no unresolved claims remain. Relations are
reviewed when both endpoints remain, or removed when an endpoint is excluded.

## Persistence and Concurrency

Every mutation requires the exact workspace fingerprint returned by the latest
read. Under the existing shared workspace lock, the service copies the
workspace to a sibling candidate, mutates JSONL files and an
`adjudications.jsonl` ledger, refreshes manifest counts, validates the candidate,
then atomically replaces the workspace. A canonical-base rebuild intentionally
invalidates prior decisions and requires review again; incremental Release sync
preserves the workspace and ledger.

The ledger stores identifiers, decision, reviewer, note, evidence metadata, and
timestamp, but never duplicates article bodies. KBAudit records the same
decision for operational traceability.

## Safety Gates

Finalization fails while any claim is draft or marked `needs_evidence`. It then
resolves generated containers/relations, marks the manifest reviewed, and
revalidates the serving gate. The legacy bulk-approval path becomes a finalize
operation; it must not silently promote unresolved claims. Publishing remains a
separate authenticated endpoint and is not exposed by the new panel.

## Admin Experience

The existing `/admin/knowledge` page gains a compact Release Review section:

- release/fingerprint status and unresolved count;
- claim list with evidence level, source count, confidence, and decision;
- selected-claim detail with provenance and structured evidence inputs;
- explicit approve, needs-evidence, reject, and background-only commands;
- finalize and publication dry-run only when all claims are resolved.

The layout is a dense two-pane operations surface consistent with the current
dark System KB console. Errors and stale-fingerprint conflicts remain visible.

## Verification

Backend tests cover each decision, evidence validation, stale fingerprints,
atomic failure preservation, relation/container resolution, unresolved
finalization rejection, dry-run separation, and audit records. Frontend tests
cover claim selection, decision payloads, disabled finalization, stale reload,
and the absence of a publish command. Production rollout stops after preview;
human review is still required before any later publish.
