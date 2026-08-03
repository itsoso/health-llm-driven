# Agent Busy And Diet Correction Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | in_progress |
| current_stage | G2 design approved; implementation planning |
| owner_surface | Mobile chat / Backend agent runtime |

## Problem

A production Mobile follow-up was presented as a network send failure while the
Backend was actually serializing it behind an earlier active turn. The same
follow-up requested a `1/2` diet-record correction that the deterministic
parser did not recognize, and a matching record without nutrition entered
repeated model/tool rounds before refusing the write.

## Evidence

- The user supplied the production screenshot and selected complete recovery
  option A on 2026-08-02.
- Production logs show `POST /api/v1/agent/stream -> 409`, followed by owner-
  scoped status checks for the never-admitted new turn returning 404.
- The 409 response detail states that the preceding message is still running;
  it is not a transport outage.
- Later tool traces show one diet candidate with
  `record_has_no_scalable_nutrition` repeatedly returning to the model loop.
- Code inspection confirms the explicit partial-meal parser supports Chinese
  tokens but not numeric `numerator/denominator` input.

No prompt content, meal content, image or credential is copied into production
diagnostic records beyond the user-provided reproduction phrase required for a
regression test.

## Decision

Implement the approved design in
`docs/plans/2026-08-02-agent-busy-diet-correction-recovery-design.md` and the
feature contract in
`docs/specs/active/2026-08-02-agent-busy-diet-correction-recovery.md`:

- fail loudly on non-2xx stream responses and classify Backend busy distinctly;
- locally queue text follow-ups with the same turn ID and bounded retry;
- parse `1/2` as a partial-consumption correction;
- scale existing nutrition or preserve food text with a truthful portion marker
  when nutrition is absent; and
- terminate missing/ambiguous correction paths with one clarification.

## Gates

### G1 Product Admission: PASS

This repairs the existing Mobile chat -> WriteIntent -> owner-scoped diet
ExecutionEvent loop. It introduces no new first-class product object, medical
claim or autonomous action. The smallest end-to-end slice is one queued
follow-up followed by one deterministic write or one clarification.

### G2 Feasibility And Risk: PASS

The production request sequence and both relevant code paths were inspected.
The change needs no schema migration. Main risks are duplicate turn admission,
unbounded retry, changing the wrong meal, inventing missing nutrition and
leaking health content in diagnostics. Stable client turn IDs, one bounded FIFO
pump, owner-scoped deterministic selection, fail-closed ambiguity and
content-free logs address those risks. G3 regression tests and G4 independent
health-write safety review remain mandatory.

### G3 Tests: PENDING

Failure-first regression tests and verification have not run yet.

### G4 Safety Review: PENDING

Required because this path changes health records.

### G5 Deployment Health: PENDING

Backend has not yet been deployed for this change.

### G6 Production Verification: PENDING

Mobile OTA and end-to-end production verification have not yet run.
