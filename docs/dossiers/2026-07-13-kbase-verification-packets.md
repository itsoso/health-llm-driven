# Dossier: KBase Verification Packets

| Field | Value |
|---|---|
| slug | `kbase-verification-packets` |
| stage | S4 implementation |
| status | in_progress |
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

- G3 tests: pending.
- G4 review: pending.
- G5 deployment health: pending.
- G6 production verification: pending; shadow generation only, with no apply,
  finalization, or publication.

## Artifacts

- Design: `docs/plans/2026-07-13-kbase-verification-packets-design.md`
- Plan: `docs/plans/2026-07-13-kbase-verification-packets.md`
