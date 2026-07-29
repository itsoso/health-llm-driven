# Runtime Medical Reconciliation Write Outage

| Field | Value |
|---|---|
| date | 2026-07-29 |
| status | in_progress |
| current_stage | G5 passed; G6 pending synthetic write verification |
| owner_surface | Agent Runtime / health writes |

## Incident

Production Agent turns could read health data, but diet creation and other
health writes were rejected with a temporarily unavailable response. The
incident was global to Runtime-managed writes rather than specific to food
recognition, image upload, the model provider or the diet database path.

## Root Cause

An older `upload_medical_exam_text` operation ended after its write boundary
without a verified receipt. Runtime correctly moved the operation to
`reconciliation_required` and paused the global write circuit.

The pause persisted because the medical report path had three missing pieces:

- fixed-resource tools did not derive their reconciliation resource type from
  the single declared receipt type;
- the Runtime operation identity was not persisted as an opaque medical exam
  source fingerprint;
- automatic and manual owner-scoped reconciliation supported diet records but
  not medical exams.

The deployment health score also ignored the Runtime circuit state, so a
deployment could report healthy while every managed health write was paused.

This dossier intentionally records only content-free Run, operation, resource
type and circuit state. It excludes report text, medical findings, food
content and other health payloads.

## Change

- Derive reconciliation resource types for fixed single-receipt write tools.
- Pass the Runtime operation ID only to the local medical import handler.
- Persist a domain-separated HMAC fingerprint rather than the raw operation ID.
- Reconcile medical exams by owner and opaque fingerprint.
- Allow audited manual medical exam reconciliation only after owner
  verification.
- Emit a content-free `CRITICAL` log when the write circuit transitions to
  paused.
- Make a paused or unacknowledged Runtime circuit a critical deployment health
  failure.

The global circuit remains fail-closed. No write bypass, broad fallback or
unverified automatic resume is introduced.

## Recovery Plan

1. Inspect only whether an owner-scoped medical exam record exists in the
   incident time window; do not read report content.
2. Resolve the legacy operation through the audited administrator endpoint as
   either `verified_effect` with the owned record ID or
   `verified_no_effect`.
3. Confirm no unresolved write operation remains.
4. Resume using the exact current reconciliation generation.
5. Deploy through `deploy.sh`.
6. Verify Runtime is active, generation equals acknowledged generation,
   health scoring passes and a synthetic diet write produces one receipt and
   one card.

## Gates

### G1 Product Admission: GO

**Decision**: PASS

This restores an existing Agent-native health write capability and adds
operational protection. It introduces no new health claim, user workflow or
data category.

### G2 Feasibility And Risk: GO

**Decision**: PASS

Production control-plane evidence isolates the outage to a paused Runtime
circuit and one legacy uncertain medical write. The implementation extends the
existing receipt and reconciliation design instead of bypassing it.

### G3 Tests: GO

**Decision**: PASS

- Targeted tests failed before implementation for missing medical owner
  verification and invalid pause telemetry.
- Runtime operations, reconciliation, write adapters, resilience, health
  score, receipt identity and rollout: `200 passed`.
- Ruff and Python compilation pass for all changed files.
- `git diff --check` passes.

### G4 Safety Review: GO

**Decision**: PASS

- The persisted reconciliation key is an opaque HMAC, not report content or a
  raw internal operation identifier.
- Every lookup is scoped by `user_id`.
- Manual verified-effect resolution checks both registered receipt type and
  resource ownership.
- Unknown effects remain paused and require explicit reconciliation.
- Logs and health output contain only status, reason and generation counters.

### G5 Deployment Health: GO

**Decision**: PASS

The legacy operation was resolved as `verified_effect` against owner-scoped
medical exam record `48`. The exact reconciliation generation was acknowledged,
the Runtime circuit returned to `active`, unresolved reconciliation count is
zero, and deployment health passed at `60/60` on commit `ad85cd66`.

### G6 Production Verification: BLOCKED

**Decision**: BLOCK

Pending one non-duplicating synthetic diet write after the strengthened
Runtime circuit health gate is deployed.
