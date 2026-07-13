# Dossier: KBase Verification Packets

| Field | Value |
|---|---|
| slug | `kbase-verification-packets` |
| stage | S5 release |
| status | complete |
| owner | Codex |

## Intake

Continue the Dedao KBase-to-Health loop after claim-level adjudication. Give the
reviewer a consistent machine-generated verification brief without allowing a
model to approve, finalize, or publish medical knowledge.

## G1 Admission

**PASS.** Production currently has unresolved Release claims and a fail-closed
serving gate. Verification packets reduce reviewer work while preserving the
existing authority boundary.

## G2 Feasibility and Risk

**PASS.** The design reuses the persistent workspace lock, fingerprint, atomic
replacement, adjudication endpoint, and KBAudit. Packets are advisory,
fingerprint-bound, strict-schema, and invalidated by claim changes. The old
evidence-pull branch is not merged because it predates immutable Releases and
would create a competing ingestion path.

## Delivery Gates

- G3 tests: **PASS.** `103 passed` across the KBase importer, immutable Release
  consumer, verification domain, and admin API suites; `241 passed` across all
  frontend Vitest suites; the Next.js production build completed successfully.
- G4 review: **PASS.** Review found one medium-risk unbounded duplicate packet
  read. It was fixed by returning only the latest unique packets with a hard
  50-item response bound, with a regression test. No path auto-adjudicates,
  finalizes, or publishes.
- Contract and drift gates: **PASS.** Web and mobile OpenAPI clients include the
  verification routes; all pre-commit hooks and `git diff --check` pass.
- G5 deployment health: **PASS.** PR #246 restored the pre-merge backend
  contracts and PR #245 bounded the verification audit operation names. Both
  PRs passed the full CI matrix before merge. Production deployed merge commit
  `bf8b02875`; the deployment score was `60/60`, the frontend and backend were
  online, and the local/remote Skills manifests matched at `22/22`.
- G6 production verification: **PASS.** The original shadow packet was reused,
  not regenerated. It remains the only packet for the unresolved claim and is
  `ready`, current (`stale=false`), and non-serving with two citation IDs. The
  missing metadata audit was reconciled idempotently with the schema-safe
  `dedao_kbase_verification_generated` operation (34 characters). Production
  now has exactly one matching generated audit and zero applied audits. No
  packet application, claim finalization, or publication was invoked.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-verification-packets-design.md`
- Plan: `docs/plans/2026-07-13-kbase-verification-packets.md`
- Domain and workspace: `backend/app/services/kbase_claim_verification.py`,
  `backend/app/services/kbase_review_workspace.py`
- Admin surface: `backend/app/api/system_knowledge.py`,
  `frontend/src/app/admin/knowledge/DedaoReleaseReviewPanel.tsx`
