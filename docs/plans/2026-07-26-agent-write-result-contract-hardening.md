# Agent Write Result Contract Hardening Plan

## Goal

Make every deterministic pre-dispatch rejection from a registered write tool
machine-readable, so Agent Runtime never mistakes local validation for an
ambiguous remote write.

## Invariants

- Local validation and policy failures return `status=rejected`,
  `success=false`, and `dispatch_started=false`.
- Once an HTTP, database, or external-service dispatch may have started, a
  missing verified receipt remains `uncertain`.
- Runtime records local rejection as `failed/tool_rejected`; it never opens
  reconciliation or pauses unrelated writes.
- Legacy prose classification remains temporarily available and observable,
  but new adapter code does not depend on wording.
- No health content is added to Runtime control-plane logs.

## Delivery

1. Add failing unit and Runtime tests for representative registered write
   adapters.
2. Add one shared structured local-rejection builder.
3. Migrate deterministic pre-dispatch adapter exits to the builder.
4. Add content-free observability when the legacy prose fallback is used.
5. Run focused, Runtime, write-safety, and integration regression suites.
6. Update the Dossier, commit, push, deploy, and verify production health.
