# Sleep oxygen read scope repair (maintenance note)

## Scope and admission

Maintenance of the existing HealthTwin read/answer loop, not a new diagnosis,
write, sync, notification, or native-client capability. Reproduce the request
“分析最近一周的睡眠血氧情况，给出你的建议” with synthetic users only.
Baseline: `7e6313f85c06028d64f626a3c3e9e10286d47b89`.

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

## Evidence and release gates

Original scope regressions failed before the repair; the missing date-bound
reader and completion support were each separately reproduced before changes.
Targeted policy/calendar tests passed. Synthetic PostgreSQL tests verify range,
owner, source exclusion, source provenance, and explicit failures. Web streaming
tests cover both available oxygen and no qualifying oxygen.

Release still requires the current fixed-commit independent safety review,
CI-mode regressions, exact-revision hosted CI, canonical deployment, and live
read-path acceptance. Local evidence does not claim deployment completion.
