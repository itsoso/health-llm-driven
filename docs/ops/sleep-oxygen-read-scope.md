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

Original scope regressions failed before the repair; the missing date-bound
reader and completion support were each separately reproduced before changes.
Targeted policy/calendar tests passed. Synthetic PostgreSQL tests verify range,
owner, source exclusion, source provenance, and explicit failures. Web streaming
tests cover both available oxygen and no qualifying oxygen.

Release still requires the current fixed-commit independent safety review,
CI-mode regressions, exact-revision hosted CI, canonical deployment, and live
read-path acceptance. Local evidence does not claim deployment completion.
