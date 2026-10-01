# Biomarker alias mis-mapping and exam sync gap incident

| Field | Value |
| --- | --- |
| 状态 | shipped |
| 当前阶段 | G6 PASS: deployed 2026-10-01 (main 644b6a2de), production reconcile applied for user 3 and verified |
| Controller | health-harness-orchestrator |
| Overlay | safety-gate |

## G1 / G2

裁决: PASS (incident, bounded repair of the lab-data pipeline; no new product
surface, no schema change).

Read-only production evidence for the anchor user (values deliberately not
recorded here) shows three defects:

1. Substring alias matching: `低密度脂蛋白` is contained in `极低密度脂蛋白`,
   `LDL` in `VLDL`/`sdLDL`, `肌酐` in `尿肌酐`, and ASCII aliases such as `Cr`,
   `TG`, `TC`, `Hb` match inside `EPI-cr`/`CRP`, `TgAb`, `QTc`, `HBsAg`.
   VLDL-C is stored as `lipid_ldl`; eGFR and urine creatinine as `CREA`.
2. Exam ingestion gap: only `MedicalExamImportService` calls `ingest_exam`.
   `POST /medical-exams/` (mobile confirm-import), `/import/pdf`,
   `/import/image` and item edits never reach `biomarker_observations`; the
   on-demand indicator sync only runs from two endpoints.
3. Duplicates: `indicator_sync` looks up its target per indicator with
   `autoflush=False`, so same-day indicators create extra rows and later runs
   overwrite the first candidate (last writer wins); the exam path dedups only
   by `source_exam_item_id`; neither path deletes rows whose mapping changed.

Write-time poisoning compounds (1): `exam_packages.normalize_item_name`
(bidirectional substring) rewrites item names/codes in the PDF parser, the
image-report path and `create_indicator_from_item`.

Downstream consumers affected: Safety Guardian `ldl_high` (first flagged item
containing `LDL`/`低密度脂蛋白` wins and suppresses the `twin.labs.ldl`
fallback), `uric_acid_high`, `kidney_function_decline` citation,
`uncategorized_abnormal_summary` (VLDL/urine creatinine silently "covered"),
Twin `fetch_latest_labs` (ILIKE prefilter, newest row wins), and
`tasks.metrics._fetch_lab_item` (dead: imports a non-existent model and
swallows the ImportError).

## G3

Run `82b4ae09f234`. Worktree based on `origin/main` `e13cd67e9`.

- RED: 112 failing tests on the unmodified code (alias boundaries incl. every
  production mis-mapping, unit gate, sync dedup/stale rows, exam ingestion on
  confirm/PDF/image/item-edit, Safety `ldl_high`/`uric_acid_high`/kidney
  citation/uncategorized, Twin collector, text parser, metrics fetcher), plus
  one later RED for converging duplicates left by an older backfill.
- SQLite: touched suites 477 passed / 1 PostgreSQL-only skip; follow-up runs
  49, 315 and 12 passed, exit 0.
- PostgreSQL 16 (isolated disposable DB, `Asia/Shanghai`): 476 passed, 2 failed.
  Both failures are pre-existing SQLite-only fixtures (a fake exam item id
  violates the `source_exam_item_id` foreign key; reproduced on unmodified
  main). Fixed to use real exam items: 12/12 pass on PostgreSQL. The reconcile
  script's dry-run/apply test runs on PostgreSQL only and passed. Final
  PostgreSQL run of all touched suites on the current code: 499 passed, zero
  failed, zero skipped, exit 0.
- Production-shaped simulation: read-only export of the anchor user's lab rows
  (no identity columns) loaded into a disposable local PostgreSQL DB. Dry-run
  persisted nothing. Apply: 91 deletes (84 duplicate or stale `indicator_sync`
  rows, 5 duplicates from a report imported twice, VLDL-C stored as LDL, a
  BUN/creatinine ratio stored as BUN), 36 inserts (14 for the exam that was
  never ingested), zero same-value duplicates, zero VLDL-as-LDL, zero
  non-concentration creatinine rows. Six same-day groups where a manual entry
  and a PDF import disagree are kept for human review.
- Every distinct lab name in production (275) run through the old and new
  resolvers: the only changed mappings are the intended fixes, plus vitamin D
  D2/D3 fractions no longer relabelled as total vitamin D at write time.
- Related suites (124 other test files that touch the changed modules, CI-mode
  SQLite, one process): branch and unmodified main fail the identical
  pre-existing environmental set (agent/Pi runtime tests); zero failures unique
  to the branch.
- Twin probe on the simulation: the pre-fix collector returned a uric-acid
  value from a mislabelled image-OCR row (ng/mL); the fixed collector returns
  the serum value. VLDL-C is not flagged abnormal in the current data, so no
  LDL alert was actually suppressed; the unit tests reproduce the suppression.
- LLM change gate: passed, live model eval not required (no prompt/provider
  change). System Map wrapper and doc-drift: passed, no count changes.
- Rebase onto main after b480c36d4 (Safety lab-input completeness): tracked
  analytes (LDL / eGFR / creatinine / uric acid / HbA1c) keep the canonical
  reader, which gives the same latest-date, worst-value, order-independent
  guarantee as `lab_pick.pick_worst` plus name and unit checks; liver enzymes
  and the WBC pattern use `pick_worst`. eGFR keeps main's
  `min(flagged, twin.labs.egfr)` fallback. `latest_reading` now merges undated
  rows into the newest group like `pick_worst` (new regression test, red on
  the old logic). Unused `_find_item` and `lab_pick.is_standard_hba1c` removed.
  `test_safety_lab_input_completeness.py` (incl. the subset property test),
  Safety, biomarker, Twin and metrics suites: 558 passed.

## G4 / G5 / G6

Independent review round 1 (snapshot of the uncommitted diff): **NO-GO**, four
blocking items, all reproduced and fixed with regression tests:

1. Under-alarm: an unrecognised name or unit spelling (`eGFRcr`, unit `-`,
   OCR unit variants, `%(NGSP)`) became "no value" in Safety/Twin, e.g. an
   eGFR 25 alert dropped from HIGH to the LOW catch-all. Fix: units are
   tri-state (convertible / recognised-incompatible / unrecognised);
   unrecognised spellings read as canonical (old contract), only recognised
   incompatible units (`ml/min` or `mg/g` for creatinine, `pg` for Hb) or
   implausible values reject a row. Safety/Twin/metrics readers accept a row
   whose name resolves, or whose name is unknown but carries the rule's old
   keyword without a positive conflict (coverage only tightens). Added the
   eGFRcr/cys/2021, UricAcid/SUA, CRE, FPG, TCH, GPT/SGPT, GOT/SGOT aliases.
2. Silent loss: exam items with abbreviated/English names, same-day readings
   with different values, exam-linked indicators without an exam item, and
   text-parser matches could disappear. Fix: exam ingest falls back to a
   non-conflicting `item_code`; sync dedups by (code, day, value) and keeps
   exam-linked indicators; the parser skips only on a positive conflict with
   a bounded name span; the reconcile dry-run labels every delete and
   `--apply` refuses unexplained drops.
3. Revived micronutrient fetchers fed wrong analytes into N-of-1 baselines.
   Fix: only LDL/HbA1c/fasting glucose are read (canonical validation);
   Hcy/vitamin D/B12/ferritin stay `None`.
4. Production values and attributions in code and tests. Fix: all replaced by
   synthetic values and dates; no exam ids.

Also addressed from the non-blocking list: highest-risk same-day value is
evaluated, IFCC HbA1c converted in the rule, display precision of the LDL
citation, UA/creatinine mmol/L, eGFR mL/s and µkat/L conversions, unitless
g/dL haemoglobin, same-day re-ingest after an item correction, ratio names
such as `尿素氮肌酐比(BUN/Cr)`, and write-time labels for `SCr`/`CRE`.

Round 2 evidence: the new tests fail 40 times (plus one collection error) on
the reviewed snapshot and pass on the fix; SQLite 501 passed / 2
PostgreSQL-only skips. Simulation on the production-shaped copy: every one of
89 deletes is explained (75 superseded by an identical measurement, 14
rejected mapping, 1 remapped to eGFR), zero DROPPED, 36 inserts. It also
removes haemoglobin rows derived from MCH/MCHC and triglyceride rows derived
from TgAb titers.

Round 2 NO-GO (fresh reviewer): timed/urine/CSF glucose entered the Twin as
fasting glucose; unitless IFCC HbA1c and mg/dL creatinine were rejected; an
unreadable newest row let an older value stand in as current. Fixed with
tighter glucose exclusions, unitless inference (HbA1c 20–130 as IFCC,
creatinine <20 as mg/dL) and a newest-date-or-nothing selector; an unreadable
tracked analyte escalates the catch-all to MEDIUM "needs checking".
Round 3 NO-GO: an unreadable HbA1c was counted as covered and vanished. Fixed.
Round 4 NO-GO: space-stripped exclusion matching glued English words
("Plasma Creatinine" contains "acr"). Fixed by stripping spaces only for CJK
exclusions. Round 5: **GO**; remaining notes behave the same as main and are
filed as a follow-up.

Final evidence: SQLite 702 passed / 3 skipped; PostgreSQL 16 729 passed with
one wall-clock timing flake (`test_build_time_under_2s_empty`, run took over an
hour under host load) that passes on rerun on both PostgreSQL and SQLite;
related suites show zero failures unique to the branch; every distinct
production lab name changes mapping only where intended.

The read-only export and the local simulation databases were destroyed after
use. Production writes (commit, deploy, backfill / cleanup) require explicit
user approval.

## Follow-up: prothrombin time and neutrophil count (branch claude/biomarker-pt-neutrophil)

- User decision (2026-09-30): add PT and neutrophils to the registry; leave
  folate out (a mildly high folate is acceptable to the user).
- NEUT (absolute count, 10^9/L, 1.8-6.3, low = risk) and PT (seconds,
  generic 10-14 s, prolonged = risk). Lab PT ranges vary (10.0-13.5 and
  12.0-14.0 seen), so a reading the lab flags as low can be normal here; a
  short PT is not a risk direction.
- Safety review round 1 NO-GO: an unitless bare-name neutrophil fraction
  (0.58) read as a confident low count. Fixed: without a recognised count
  unit, NEUT needs a count qualifier in the name and PT rejects values
  above 60 (activity %); more excludes. Round 2 GO.
- Production name corpus (373 names): exactly 3 mapping changes; all
  production bare-name neutrophil rows carry a unit. Related suites: 699
  passed, 3 PostgreSQL-only skipped.
- Not done (non-blocking): OCR unit spellings like `x10 9/L` / `10~9/L` are
  unrecognised, so such bare-name rows are dropped rather than read.

## G5 / G6 production evidence (2026-10-01)

裁决: PASS.

- Merged to main: #261 (dependency CVEs), #259 (this fix), #262, #264 (PT/NEUT),
  #266 (analyte-guard cases folded into the canonical layer). Deployed with
  `./deploy.sh -b` from a clean release clone at main 644b6a2de (17:59 CST):
  health score 60/60, skills 22 = 22, runtime-state transaction finalized,
  managed migration `20261001_150000_remote_health_oauth` applied, remote-health
  routes absent from OpenAPI (default-off), PyJWT 2.15.0 / urllib3 2.8.0 /
  pydantic 2.12.5 live, no backend/celery error logs after restart. Three
  earlier launches were stopped by deploy.sh guards before any production
  change (local `.env` missing 13 prod keys; missing `refs/reva-production` in
  the fresh clone; origin/main moved). Frontend not redeployed (user decision;
  the Next.js advisory concerns `next/og`, which the frontend does not use).
  iOS OTA left to a separate session (no new production update group yet).
- `scripts/reconcile_biomarkers.py --user 3`: dry run 158 → 110 rows, 89
  deletes (75 superseded, 13 mapping invalid, 1 remapped to egfr, 0 DROPPED),
  41 inserts (the 5 beyond the pre-merge simulation are the new PT/NEUT
  rows). Applied with user approval; `--all` dry run showed inserts only for
  users 1 (5) and 23 (2), which the user chose not to apply.
- Read-only verification after apply: 0 LDL rows sourced from VLDL-C items,
  0 creatinine rows with ml/min or mg/g units, 16 observations for exam 50,
  latest observation 2026-08-24, PT 2 / NEUT 3 / eGFR 5 present, 0 duplicate
  (code, day, value) measurements, 110 rows.
- Not done by user decision: renaming the 23 PDF-rewritten source item names;
  the supplement `taken` repair (dry run OK, 16 rows); users 1/23 reconcile.
