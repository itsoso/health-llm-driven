# Sleep oxygen read scope repair (maintenance note)

## Scope and admission

Maintenance of the existing HealthTwin read/answer loop, not a new diagnosis,
write, sync, notification, or native-client capability. Reproduce the request
“分析最近一周的睡眠血氧情况，给出你的建议” with synthetic users only.
Original baseline: `7e6313f85c06028d64f626a3c3e9e10286d47b89`.
Integration baseline: `1f4ff88a4e99fff07f1af6c5f90a4156f7d4d737`.

The parallel read-intent fix already binds explicit recent analysis through the
longitudinal resolver. Integration reuses that resolver, avoiding a second
rolling-window implementation or duplicate oxygen query. The oxygen reader is
unified at the calendar dispatch: `daily_metrics`/`daily_sources` retain daily
facts and per-field provenance, while `sample_summaries` retain separate source
observations. Both original test suites preserve owner/date/source/precision
assertions against this internal tool-result contract. No public API changes.

## Contract

- Consume the entire scope and advice clause; unknown filters, foreign owners,
  cancelled reads, unbounded windows, and model-authored scope changes stay blocked.
- Resolve an explicit recent interval against the authenticated turn clock and
  timezone, once. Bind both sleep and oxygen to identical inclusive dates.
- A compound sleep-oxygen request authorizes sleep and oxygen observations,
  not sleep-stage correlation, another person's data, writes, or synchronization.
- Query each table with owner and date predicates. Never replace a requested
  interval with the latest available night or substitute excluded Garmin oxygen.
- Keep source-specific sample summaries separate from device daily metrics;
  apply the existing device source exclusion/priority policy. NULL sample sources
  remain excluded. Missing data is not a normal clinical finding.
- Return explicit partial/no-data status, date coverage, and provenance. Neither
  daily rows nor sample counts prove a sleep interval or continuous monitoring;
  do not derive ODI or diagnose apnea. Existing sleep and safety rules remain.
- Carry oxygen fields and limitations through the verified completion projection
into the Web stream and persisted response, with no health-data writes.

## Independent review follow-up

The first fixed-commit review returned NO-GO: a sleep-only restriction could
retain oxygen authority, and provider prose could claim whole-night monitoring
or an apnea conclusion. The follow-up uses expanded domains in restriction checks.
A second review found that phrase-based answer checks still missed equivalent
clinical claims and incorrectly exempted unrelated uncertainty. Oxygen bundles
now publish only the verified deterministic fact summary plus fixed conservative
guidance; free-form provider prose is not published, regardless of its wording.
The read still completes with source/date coverage and partial/no-data limitations.
This intentionally limits oxygen interpretation until a separately governed
aligned-night/clinical-evidence adapter exists; no such capability is claimed.
Regression tests cover stream/persistence, available/no-data, arbitrary provider
text, and single-/multi-model surfaces. Earlier candidates are not approved for
release; a new fixed-commit review is required.

A third review confirmed deterministic projection but found equivalent
sleep-only wording (`仅分析` / `只分析`) lost during scaffolding. These operators
now enter the same restriction grammar; unrecognized `只` / `仅` restrictions
fail closed before scaffolding. Individual, flat/nested batch, and streamed
execution regressions require no oxygen dispatch for the narrower request.

Integration review found that upstream also authorizes a standalone oxygen
read. The generic single-dimension shortcut skipped controlled synthesis and
could publish unsupported ODI/continuous-monitoring claims. A single `spo2`
scope now also receives verified provider inputs and deterministic answer
projection. Regression coverage includes individual/batch dispatch, single/
multi-model responses, no-data/available data, stream and persistence.

## Improvement-question regression

The complete follow-up request “分析最近一周的睡眠血氧情况，给出你的建议，我有哪些需要提升的点？”
was rejected as `longitudinal_read_scope_unresolved`: the final domain-free
answer goal was misclassified as a read filter. The shared analysis-goal grammar
now consumes complete improvement questions (points/areas to improve), without
granting read authority by itself. Attached unknown filters still fail closed;
owner, date, dimension, cancellation and mutation checks remain on the original
turn. Tests cover the exact full request through individual/batch authorization,
owned date-window execution, streamed answer and persisted completion, with
both available oxygen and no-data results. Publication and production acceptance
must be verified separately for this follow-up revision.

## Evidence and release gates

### Web card/narrative disappearance

The reported 2026-09-23 23:40 (Asia/Shanghai) turn succeeded on the server:
sanitized read-only inspection found two verified query goals and a persisted
1,032-character response. The final supported sleep card triggered a Web-only
early return that hid the response, its inline table and completion panel.
Unknown metadata card types were correctly filtered; multi-card grouping was
not the cause. No health payload or identity is included in this evidence.

`ChatView` now renders cards as supplements to the same message's markdown and
completion status. The registry/action allowlists are unchanged. Test-first
regressions reproduce the disappearing table and history narrative, then verify
stream-to-done and history restoration through the real page and renderers.
Card-only, unknown-card, multi-card and copy behavior remain covered. This is a
Web rendering repair; no read scope, clinical interpretation, database or native
client behavior changes. Browser acceptance and exact-revision deployment remain
separate gates; existing persisted answers need no backfill or re-execution.

Original scope regressions failed before the repair; the missing date-bound
reader and completion support were each separately reproduced before changes.
Targeted policy/calendar tests passed. Synthetic PostgreSQL tests verify range,
owner, source exclusion, source provenance, and explicit failures. Web streaming
tests cover both available oxygen and no qualifying oxygen.

Release still requires the current fixed-commit independent safety review,
CI-mode regressions, exact-revision hosted CI, canonical deployment, and live
read-path acceptance. Local evidence does not claim deployment completion.

## September 24 screenshot follow-up

The full week/improvement request now passes the existing binder. Two remaining
failures reproduced separately: `昨晚血氧` hit a sleep-only night restriction;
the self-owned device monitoring narrative was rejected as a foreign owner.

- Night oxygen carries a server-bound `period=sleep_night` through policy,
  normalization, execution, completion and owned continuation. The wake date is
  frozen in the turn timezone. It is not an all-day or latest-night query.
- Only epoch-stamped samples within one coherent recorded sleep-clock interval
  corroborated by absolute sleep interval bounds for the same owner/source/date
  are summarized, separately by source. Bare clocks alone are not evidence of
  their timezone. The current adapter supports the
  ingestion clock timezone (Asia/Shanghai). Missing/conflicting clock sources,
  unsupported timezone, equal clocks or an interval over 20 hours produce an
  explicit unavailable interval, not unfiltered daily metrics. Clock-derived
  intervals do not attest actual sleep, continuous coverage or sleep stages.
- The complete self-owned monitoring/sync question authorizes only the existing
  owned job-status reader, not a sync job or implicit health-history read. Extra
  owners, dates, commands and unsupported clauses remain blocked. Its answer is
  projected from verified status; arbitrary provider diagnosis/repair claims
  are excluded from both streaming and persisted responses.
- Existing Garmin oxygen exclusion is unchanged and now explained: unavailable
  analysis is not proof of upload failure. Sample ingestion and device hardware
  were not verified by this repair. No production data were inspected or changed.
- Mobile blocked/refused states no longer use the generic interrupted-turn
  fallback. Real transport failures, write reconciliation and retry gates remain.

Test-first evidence: scope/status RED 4 failures; UI RED 2 failures; continuation
RED 1 failure; unsupported provider claims RED 2 failures. Mobile chat suite
64 passed and TypeScript passed. Final PostgreSQL, independent safety review and
release evidence must be recorded separately; this note does not claim release.

The first independent review of `65e685937` was NO-GO: Apple imports can retain
source-local clocks after dropping their UTC offset. Request timezone alone did
not attest those clocks. Four additional RED regressions cover missing absolute
intervals, foreign timezone, foreign owner and foreign source. Night selection
now also requires matching absolute `SleepLevelInterval` bounds; no matching
provenance means unavailable, even when daily oxygen values exist. This does not
establish stage-level correlation or continuous sleep. The rejected candidate
must not be published; the revised fixed diff requires a new independent review.
