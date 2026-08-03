# Agent Busy And Diet Correction Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | in_progress |
| current_stage | Seventh G4 NO-GO remediated; fresh G4 review pending |
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

### G3 Tests: PASS

Failure-first evidence was observed before implementation:

- Mobile treated the Backend 409 JSON response as a successful empty SSE
  stream, then polled a turn that had never been admitted.
- Numeric fractions, whitespace fractions, invalid fractions and truthful
  no-nutrition corrections failed their new Backend assertions.
- Ambiguous, missing and failed diet lookups entered three model rounds instead
  of terminating after one deterministic lookup.
- Busy retries triggered three haptics for one user submission before the
  final feedback-deduplication guard was added.

Fresh verification after the final implementation commit:

- Mobile critical path after the seventh G4 remediation: 3 suites / 170 tests passed.
- Mobile full regression: 289 suites / 2,287 tests passed.
- Mobile TypeScript: `npx tsc --noEmit` passed.
- Mobile lint: 0 errors; 92 pre-existing warnings outside this change remain.
- Backend focused, stream integration, diet API and photo-context regression after the seventh G4 remediation: 254 tests passed with 7 dependency/
  framework deprecation warnings.
- Backend Ruff and Python compilation passed.
- Dossier consistency: 98 dossiers passed.
- Generated system-map drift check passed.
- `git diff --check` passed.

### G4 Safety Review: NO-GO -> REMEDIATED -> RE-REVIEW PENDING

The first independent review found no Critical issue and three Important
release blockers:

1. arbitrary non-2xx HTTP `detail` text could reach the chat UI;
2. a later turn could bypass a busy queue head during its backoff window; and
3. signed or malformed ratios such as `-1/2`, `1/-2` and `1//2` could be
   misparsed or persisted as replacement food text.

All three were reproduced with failing tests and remediated. HTTP error details
now use an allowlisted canonical busy message and other non-2xx bodies never
enter SSE/UI parsing. New turns append whenever a queue already exists. Signed,
decimal and malformed ratio-like input fails closed before any write. The
stale correction-normalizer docstring was also updated.

The second independent reviewer confirmed those fixes but found two further
Important blockers: Unicode/full-width ratio characters could still bypass the
guard, and a completed nutrition correction could be multiplied again by a
later turn. Both were reproduced with failing tests. Fraction input now
normalizes only recognized Unicode digits/slashes/signs before validation, and
the stored portion marker is used as the previous ratio: repeating the same
ratio is idempotent, while changing it applies `new / previous` to the stored
nutrition. The food description is preserved byte-for-byte apart from replacing
the generated suffix.

The third independent reviewer confirmed those fixes but found one further
Important blocker and one Minor boundary: common unsupported portion forms
(`50%`, `0.5`, `½`, `二分之一`) could fall through to food replacement, and a
busy turn could exceed its ten-minute TTL by one final backoff request. Both
were reproduced with failing tests and remediated. Unsupported portion-like
input now fails closed before any diet write. Busy retry delay is capped at the
remaining TTL, and the queue head is expired before network dispatch when the
TTL is reached.

The fourth independent reviewer confirmed those fixes but found three further
Important blockers. Identical independent submissions could share one turn ID
and the second could be removed from the busy FIFO; questions, negations and
contradictory ratios could be treated as factual corrections; and explicitly
supplied unchanged nutrition (including `1/1` or zero-valued nutrients) could
be erased when the generated portion marker changed food text. Each issue was
reproduced with a failing test and remediated. Independent queued submissions
now always receive distinct IDs while retries retain the original ID. Unsafe or
multi-ratio language terminates before lookup/write. Deterministic portion
updates carry an internal source marker so the diet API preserves explicitly
calculated values without relaxing stale-nutrition invalidation for ordinary
food edits.

The fifth independent reviewer found two further Important blockers. The
parser accepted the first ratio before running whole-utterance safety checks,
so additional contradictory ratios and several question/negation particles
could still reach an update. It also found that the internal source marker was
a public request field and therefore forgeable. Whole-utterance validation now
runs before any fraction is accepted, with explicit no-write coverage for the
additional adversarial forms. The public source marker was removed. Exact
deterministic portion updates now use a one-shot server-side fingerprint and an
HMAC over owner, record and canonical payload in an internal-only header; the
diet API verifies that signature before preserving explicit unchanged/zero
nutrients. A public client spoof remains on the ordinary stale-invalidation
path.

The sixth independent reviewer confirmed the authenticated update path but
found two further Important blockers. Full-utterance validation still scanned
only after the first partial-meal signal, so an earlier ratio, an unseparated
question particle, a later retraction, scientific notation and contradictory
photo-context ratios could still select the first supported fraction. Mobile
could also reverse FIFO order when turn B entered the local queue while turn A
was in flight and A's delayed response then returned 409. Both issues were
reproduced before remediation. Text and photo correction paths now share a
whole-utterance ratio guard that requires one exact supported factual ratio and
rejects ambiguous, uncertain, retracted or unsupported forms. The busy path
always restores the already-in-flight turn at the queue head. Positive
regressions retain legitimate language such as `没吃那么多，只吃了1/2`. The
reviewer's non-blocking HMAC replay-hardening suggestion remains documented;
the header is not returned to clients and still requires valid owner auth. A
fresh independent reviewer then found two more Important cancellation gaps.
Question particles followed by helper words and explicit trailing cancellation
language could still trigger text or photo corrections. In addition, a 409
arriving after new-chat or unmount cleanup could revive the old turn because
the catch path did not know that its queue generation was cancelled. Both were
reproduced before remediation. The shared utterance guard now recognizes
standalone question particles without misclassifying `那么`, and rejects
cancel/retract language independent of word order. Mobile captures a queue
generation per request and invalidates it on new chat, unmount and explicit
cancellation; a stale busy response is rejected instead of re-queued. A fresh
independent reviewer must issue GO before deployment.

### G5 Deployment Health: PENDING

Backend has not yet been deployed for this change.

### G6 Production Verification: PENDING

Mobile OTA and end-to-end production verification have not yet run.
