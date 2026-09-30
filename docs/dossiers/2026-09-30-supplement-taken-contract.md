# Supplement taken contract incident

| 字段 | 值 |
| --- | --- |
| 状态 | G4 GO (v3); uncommitted — commit/push/deploy/backfill not yet authorized |
| 当前阶段 | awaiting owner authorization (commit → CI → deploy → backfill) |
| Controller | health-harness-orchestrator (incident) |
| Overlay | safety-gate |
| Run ledger | `docs/_generated/harness-runs/ca71a07382d4.jsonl` (local, not committed) |

## G1 — Scope and evidence

裁决: PASS

Symptom: in September 2026, 16 of user 3's 21 `supplement_records` rows were
stored `taken=false` although their notes annotate an intake. Twin "taking"
segmentation, adherence stats and DSI reasoning count only `taken=true`, so
those doses were treated as not taken.

Read-only production evidence (2026-09-30, `default_transaction_read_only=on`;
raw rows stayed in the session scratchpad, none are recorded here):

- `taken_count` is an unmapped legacy column from the January SQLite→PostgreSQL
  migration (`DEFAULT 1`). All 917 rows hold 1, including every `taken=true`
  row, so it carries no intake signal. The proposed backfill predicate
  `taken_count >= 1 AND taken = false` matches all 59 `taken=false` rows,
  43 of which (March–June) have no intake evidence; one April row is a
  deliberate correction that must stay not-taken.
- The 16 September rows share one shape: notes present, `taken_time` and
  `actual_dosage` absent, three back-dated, written in sub-second bursts as
  separate transactions. They are the only notes-bearing rows written since
  mid-April. Every note annotates an intake: 9 state it with an explicit
  intake verb, 7 are context/purpose tags only, and none negates, cancels or
  plans an intake (independently re-read by both G4 reviewers).
- No `agent_tool_operations` row owns any of them. For 8 of the 16 there was
  no in-app agent run within ±3 minutes; where chat overlapped, the concurrent
  in-app turns were unrelated (the one inspected was an analysis query that did
  not execute). Pre-April notes-bearing writes from the old chat path were
  `taken=true`.
- Caller identity is not recoverable: the health vhost runs `access_log off`,
  backend journald retention is ~1.5 days, and no local agent transcript
  contains the notes before the 2026-09-29 analyses.
- In-repo writers were ruled out by code: NFC, `/records/intake-batch`,
  write-intent confirmation and protocol completion always set `taken=true`;
  the in-app agent's supplement branch routes only to those; web, mobile, Mac
  and mini-program toggles send explicit boolean `taken` to `/records/batch`.

Root cause: `SupplementRecordCreate` declared `taken: bool = False` (optional
in OpenAPI) while requiring a `user_id` the server ignores, and silently
dropped unknown fields. A client sending the OpenAPI-required fields plus notes
received 200 and stored the dose as not taken.

Adjacent defects on the same candidate paths: the POST upsert overwrote unsent
`taken_time`/`notes` with `None` and ignored `actual_dosage`; `/records/batch`
items were untyped (missing `taken` → false, `"false"` → 500, unknown keys
dropped, per-item commits); quick-record replied "已打卡" without changing an
existing same-day `taken=false` row, and parsed negated/planned phrasing
("没吃…", "准备吃…") as intakes.

## Decision

- `POST /supplements/records`: `taken` is a required `StrictBool`; no default
  in either direction (`true` inflates adherence, which feeds DDI/PGx/Safety
  reasoning; `false` loses intakes). Unknown fields → 422; `user_id` optional
  and ignored in favour of the authenticated user.
- Same-day upsert applies only fields the caller sent (explicit `null` still
  clears); explicit `taken=false` remains a valid un-check.
- `/records/batch`: typed items (`supplement_id: StrictInt`,
  `taken: StrictBool`, extra fields forbidden → 422); ownership and duplicate
  ids (→ 400) are checked before any write; one commit.
- Quick-record never flips an existing same-day `taken=false` row: 409 naming
  the supplement, no write (already-taken rows stay idempotent). Supplement
  free text matching negation / missed / other-day / plan / advice / question
  markers is rejected with 400 before any write. This is a tightening-only
  filter, not full intent recognition (e.g. "睡前吃X", "我妈吃了X" still parse
  as intakes on a fresh day, as before); the shared classifier follow-up owns
  the complete fix.
- `backend/skills/health-record/SKILL.md` is unchanged: skill text is an LLM
  prompt surface that requires a live-LLM regression gate; its contract note
  and wrong step-1 endpoint moved to a follow-up.
- Twin collector unchanged: `taken == True` is the correct semantics.
- Backfill: `backend/scripts/repair_supplement_taken.py` (dry run by default)
  re-verifies the frozen 16 ids against the evidence predicate under
  SERIALIZABLE + `lock_timeout` + table lock, refuses to join an open
  transaction, fails closed on any drift, enforces the exact rowcount, and
  prints the affected ids and prior state for this dossier. Not executed.

## G2 / G3 — Implementation and verification

All runs used a CI-equivalent venv (`requirements.lock` with hashes +
`requirements-dev.txt`); the developer's older venv drifted from the lock and
produced false reds on unmodified `main`, so it is not used as evidence.

- RED on baseline code: contract v1 7 failed / 1 passed (explicit un-check
  guard); v3 additions 14 failed / 24 passed; repair tests failed at import.
- GREEN: contract + repair + supplements + quick-record + intake classifier +
  slot completion + adherence idempotency: 192 passed.
- PostgreSQL 16.13 (production is 14.20; no relevant feature differs): the
  first run caught a real defect (SERIALIZABLE after a prior query) that SQLite
  hid; fixed by the explicit own-transaction precondition. v3 changed-endpoint
  files: 101 passed, zero skips. Replay on a table with the exact production
  DDL (v2 and v3) reproduced the incident (`taken=false`, `taken_count=1` on
  inserts that omit `taken`), then dry run 16 → apply 16 → controls untouched
  → second apply fails closed.
- CI-faithful A/B (one pytest process per file, CI flags, Pi kernel, 143
  files touching supplements/quick-record/skills/dossiers) v3 vs baseline:
  15,240 tests, 0 failures, vs 15,202 on baseline; zero new failures. Baseline
  shows 4 governance tooling tests timing out under local load (nested
  pytest); they pass when the machine is less loaded.
- API clients regenerated from OpenAPI; both clients receive identical
  changes; `generate-api-types.sh --check`, mobile and frontend `tsc --noEmit`
  pass; no client code references the changed schemas.
- System Map regenerated (service count +1 for the repair module);
  `system-map-check.sh` and `check_doc_drift.py` pass. Blocking ruff
  (F821/F822/E9) passes. LLM change gate: zero-cost pass for every changed
  path once the SKILL.md edit was dropped.

## G4 — Safety review

- v2 (patch sha256 `55e155a5…9d9639`): NO-GO. Blocker: the quick-record flip
  turned every gap in the phrasing guard (53/64 probed non-affirmative texts,
  whitespace bypass) into an overwrite of a row the user had un-checked.
  Should-fix: untyped batch items; repair audit output and lock timeout;
  explicit owner approval of the 16 rows. Nits: lax bool coercion, synthetic
  test controls, stale dossier.
- v3 (patch sha256 `33f6af68…a2aa7a`), fresh reviewer: GO. Blocker and
  should-fix items closed; baseline-vs-v3 parse comparison over 523,993
  generated texts shows the filter only ever rejects more; HTTP probes found no
  write v3 makes that baseline did not. Conditions: deploy the fix before the
  backfill; owner approves the exact 16 ids (naming the 7 context-tag rows
  1092, 1093, 1102–1106); this dossier's production-derived date/timing
  generalized (done, doc-only; code unchanged since review). Remaining nits
  are listed under follow-ups.

## Backfill runbook (requires explicit owner approval of the 16 ids)

1. Deploy the contract fix first so no new rows are produced this way.
2. Dry run on production: `cd /opt/health-app/backend && venv/bin/python
   scripts/repair_supplement_taken.py` → expect `rows: 16` and the frozen ids.
3. Owner approves exactly those 16 ids; then run with `--apply` and paste the
   JSON output here together with the UTC run time (`date -u`).
4. Verify read-only that the 16 ids are `taken=true` and nothing else changed;
   Twin cache is invalidated by the script (5-minute TTL otherwise).
5. Rollback: the SQL in `backend/app/services/supplement_taken_repair.py`.

## Follow-ups (not in this change)

- Mobile supplement notification action posts to a non-existent
  `/supplements/me/checkin` and swallows the error.
- Shared intake classifier misses past negation / planned intake / questions
  (mirrored by a mobile guard); then retire the local quick-record filter.
- Drop the legacy `taken_count` column after the backfill decision.
- SKILL.md: document the contract; fix step 1 endpoint and the single-quoted
  `$(date …)` examples (live-LLM gate).
- Pre-existing quick-record issues: always records today even for "昨天…";
  ambiguous `ilike … first()` definition match; Mac form "补剂<name> <dose>"
  creates duplicate definitions; 500 handler returns `str(e)`.
- `watch_summary` advertises `POST /supplements/records` without a payload
  contract (unused by the watch today); the agent's `record_map["supplement"]`
  entry is dead code (would now fail loudly with 422 if ever reached).
- Review nits kept out of the reviewed code: `SupplementRecordCreate.supplement_id`
  → `StrictInt`; timestamp in the repair's audit JSON; distinct 400 message for
  filtered supplement text; success reply should name the resolved definition;
  `checkins` length limit; `supplements.py` grew 5 lines past the file budget.
- Filter gap classes for the classifier follow-up: stop/skip/pause, zero dose,
  purchase/inventory, third party, advice ("推荐"), future timing without a
  marker (睡前/今晚/马上), English negation.
