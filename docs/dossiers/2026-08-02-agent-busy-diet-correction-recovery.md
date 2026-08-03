# Agent Busy And Diet Correction Recovery

| Field | Value |
|---|---|
| date | 2026-08-02 |
| status | in_progress |
| current_stage | G4 GO; deployment pending |
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

- Mobile critical path after the ninth G4 remediation: 3 suites / 156 tests passed.
- Mobile full regression after rebasing onto the latest `origin/main`: 292 suites /
  2,399 tests passed.
- Mobile TypeScript: `npx tsc --noEmit` passed.
- Mobile lint: 0 errors; 92 pre-existing warnings outside this change remain.
- Backend focused, stream integration, diet API and photo-context regression
  after rebasing onto the latest `origin/main`: 531 tests passed with 7
  dependency/framework deprecation warnings.
- Backend Ruff and Python compilation passed.
- Dossier consistency: 99 dossiers passed.
- Generated system-map drift check passed.
- `git diff --check` passed.

### G4 Safety Review: PASS (FINAL GO)

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
independent reviewer then confirmed the Mobile generation cancellation and
authenticated owner-scoped write paths, but found that several cancellation,
negation, uncertainty and question forms could still be read as factual diet
corrections. The shared text/photo utterance guard now defaults to factual-only
semantics: it permits the narrow explicit shortfall phrases `没吃那么多`,
`没有全吃完` and `没吃完`, while residual negation, retraction, uncertainty or
question language fails closed before lookup or write. Twenty-four new text
and photo regression cases cover `撤回`, `反悔`, `先不改`, `并非`, `应该`,
`好像`, `估计`, `差不多` and sentence-final `吧`. The next independent review
found that this was still a blacklist rather than an actual positive grammar:
hypothetical, quoted, demonstrative, prospective, contradictory and uncommon
cancellation wording could still reach a write. It also found that
`stopStreaming` and `cancelActiveTurn` did not remove a retry already waiting
in the busy queue. Both blockers were reproduced before remediation. Text and
photo portions now have narrow anchored positive grammars which must consume
the entire normalized utterance as an explicit completed-consumption fact;
anything outside the allowed meal/date, shortfall, exact ratio and write
phrases fails closed. Fifty text/photo adversarial cases cover the reviewer's
bypasses plus future-intent forms. Stop and cancel now remove the logical busy
queue head, cancel pending image acceptance, record an interrupted terminal
state and leave any later independent turn eligible to continue. Three Mobile
cancellation race tests cover scheduled and delayed-409 paths. The next
independent reviewer found one remaining fail-open boundary: unsupported or
cancelled fraction language without the narrow positive grammar could fall
through to the generic text food-replacement parser, while the contextual
photo path could still auto-save the whole meal after rejecting its fraction.
Both paths were reproduced with real zero-write assertions before remediation.
Any fraction-like named-meal correction not consumed by the positive grammar
now terminates before generic replacement. The photo path marks the turn as
fraction-blocked before asset or record creation, gives the model an explicit
no-write instruction, and independently rejects both diet create and update
tool calls for the turn. Positive decimal food quantities and ordinary
high-confidence photo capture remain covered. A fresh independent reviewer
then confirmed those guards but found three remaining blockers. Standalone
unsupported portions such as `50%`, `0.5`, `½` and `二分之一` were not treated
as portion-like without a preceding consumption verb; full-width ratio symbols
were not normalized before the photo gate; and a legitimate signed portion
update containing `meal_type` failed with HTTP 500 because the JSON-mode enum
had already become a string. All were reproduced with failure-first tests. The
shared detector now normalizes symbols at its boundary, recognizes percent,
decimal, vulgar fraction, Chinese percentage, `成` and `比` forms regardless
of a consumption prefix, while preserving decimal quantities followed by a
measurement unit such as `鸡胸肉71.4克`. Unsafe photo cases assert zero diet
records, zero photo assets and zero drafts. Diet updates now accept the
JSON-mode meal-type string and restore typed meal-time assignment; a real
signed API update including the meal type returns 200 and preserves the
explicit nutrition. A final pre-review adversarial probe also found bare `半`,
compact `百分50`, and colon ratios such as `1:2`/`１：２` could still fall
through in text or auto-save a contextual photo. Boundary-aware unsupported
portion recognition now closes those forms while preserving the concrete food
replacement `半只鸡`; real photo tests again assert zero records, assets and
drafts. The next independent reviewer confirmed all specified cases and 177
selected regressions, but found five Unicode/Chinese-equivalent bypasses:
`1÷2`, `0点5`, spaced `百分之 50`, `一比二`, and `1∶2`. Each was reproduced as
both a generic text replacement and a high-confidence photo auto-save. Symbol
normalization now maps division and ratio glyphs to their canonical forms, and
the shared unsupported-portion detector recognizes Chinese decimals, spaced
percentages, and Chinese numeral ratios. Ten new real-path cases assert the
same text/photo zero-write invariant. A final root-cause probe removed the
remaining dependence on recognizing a portion at all: explicit `取消`/`莫`/`勿`/
`别再` write cancellations now veto both text and photo diet writes before
portion parsing, close the create/update/delete adapters, and produce a
truthful cancellation acknowledgement. Eight no-fraction cancellation cases
assert zero lookup and zero record/asset/draft writes. The next independent
reviewer found the cancel word still had to be adjacent to the write verb:
`别帮我记录`, `不要给我记录`, and `别把它记录下来` therefore auto-saved real
photos, while their portion-bearing forms used the less truthful ambiguous-
fraction reason. The cancellation grammar now permits a bounded sequence of
common helper and object phrases (`再`, `帮我`, `给我`, `把它`/`将这餐`) before
the explicit write verb, without treating unrelated free text as cancellation.
The three no-portion and two portion-bearing photo cases now produce a
`cancelled` reason and zero records/assets/drafts; matching text cases perform
zero lookup. The final independent reviewer issued GO after 150 focused
regressions, two real API cases and 31 real ORM database cancellation/portion
variants. Every unsafe case produced zero diet records, photo assets and
drafts; create/update/delete adapters stopped before downstream dispatch.
Positive signed portion updates, ordinary photo capture, explicit food
quantities, owner/HMAC binding, unique targeting, no-nutrition markers and
verified receipts all remained functional.

After the implementation was rebased onto the latest remote `main`, a fresh
independent reviewer rechecked the material executor conflict resolution and
issued `G4: GO` for commit `64eee6c460a442014819cca0fdb8746cb01660b9`.
The review confirmed both the upstream destructive/sync intent guard and the
local deterministic diet terminal exclusion are preserved. It passed 150
Backend safety regressions, 108 Mobile queue regressions and 31 real ORM
cancel/photo variants with zero diet records, assets or drafts. Owner-bound
HMAC probes, a signed real PUT returning 200, verified receipt truthfulness,
stable FIFO retry IDs and cancellation generation invalidation also passed.

### G5 Deployment Health: PENDING

Backend has not yet been deployed for this change.

### G6 Production Verification: PENDING

Mobile OTA and end-to-end production verification have not yet run.
