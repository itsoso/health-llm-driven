# Health Day Phase 1a Read-Only Shadow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a dormant, internal Health Day shadow library that composes one deterministic user-local day from an immutable PostgreSQL snapshot and produces a redacted per-surface legacy diff, with mechanical proof that the shadow path performs no writes, notifications, cache/provider calls, API changes, or client changes.

**Architecture:** A PostgreSQL-only loader turns explicitly ordered source rows into one digest-bound frozen bundle inside one `REPEATABLE READ, READ ONLY` transaction. A DB-free composer calculates an explicitly bounded Daily Plan shadow subset and fixed occurrences without calling existing builders/registries. It does not claim to be the extracted full `build_daily_operating_plan` calculation half:unsupported Twin/training-gate/AdviceGuard branches remain named degraded evidence until a later pure-seam Gate. Versioned canonical surface projectors and legacy adapters normalize both sides into symmetric scopes before deterministic diff. Each writeful legacy surface runs in its own PostgreSQL schema cloned from the same committed semantic baseline;the measured shadow uses a separate untouched schema. No production runner is wired in Phase 1a.

**Tech Stack:** Python 3.12, FastAPI/SQLAlchemy models already in the repo, PostgreSQL, frozen dataclasses, `cryptography` HKDF + stdlib HMAC and a test-locked restricted RFC 8785/JCS JSON subset, pytest, existing Dossier/system-map/doc-drift tooling. No new runtime dependency.

---

## Authority and stop conditions

- Parent spec:`docs/specs/active/2026-08-15-quiet-proactive-health-day.md` §7、§8.1、§14–§18。
- Child Dossier:`docs/dossiers/2026-08-15-health-day-read-only-shadow.md`。
- Parent Dossier remains `blocked_at_g2`. Finishing this plan does **not** authorize Phase 2–4, a client plan version, mutation, or proactive notification.
- Stop immediately if implementation requires an API/router, mobile/mac/watch change, DB migration/table, persisted shadow row, scheduler/Celery/startup hook, PushService/outbox call or production key wiring. Shadow modules may not import/call any legacy assembled wrapper, including `build_twin`, `build_daily_operating_plan`, `agenda_service.today`, `smart_today`, `runtime_range_view`, `build_day_schedule`, `build_daily_artifact`, `build_today_dynamic_view`, `build_today_spine`, `med_supplement_items`, workout-chain materialization or timeline event materialization.
- Do not add even a manual CLI in Phase 1a. Any runtime/manual runner is a separate child Gate because it creates owner-selection, telemetry, rate-limit and rollback obligations.
- PostgreSQL semantic modules and any schema-copy fixture must run with an exported isolated `TEST_DATABASE_URL`,the feature-specific destructive opt-in,and a preinstalled database-internal safety marker. A name containing `test` is only a secondary heuristic and never authority to create/drop schemas. Pure contract/projector focused tests explicitly unset that target and use no DB behavior (an in-memory SQLite URL only prevents ambient app config leakage);they may not request the shared `db` fixture. Never let a PostgreSQL proof silently skip/fall back to SQLite.
- Existing unrelated dirty files stay untouched. Stage explicit paths only.

## Fixed Phase 1a contracts

### Supported inputs

The read-only loader may query only existing rows, with explicit owner filters and stable `ORDER BY ... id`:

- explicit frozen facts needed by the bounded in-memory Daily Plan shadow subset;the already materialized `DailyOperatingPlan` is loaded only as a legacy/projection diagnostic and never becomes canonical truth;
- active `HealthProgram` inventory (reported as `unsupported_current_composer`, never silently omitted);
- active `HealthProtocol` rows and all terminal/snooze/event-trigger facts from the relevant cadence period start through the loader-derived user-local day;
- active `HealthProblem` follow-up facts;
- active `Medication` rows, including all reminder slots;
- `UserProfile` timezone/work/sleep preferences;
- cached `CalendarSource` / `CalendarEvent` rows and sync status;
- existing execution/terminal facts needed to avoid resurfacing handled items;
- active intervention cycle summary only after eager/plain-data conversion.

The loader must not refresh a connector, rebuild a Twin, record AdviceLedger, create/update a DailyOperatingPlan, call SafetyGuardian's global registry, materialize a workout chain/HealthEvent, or infer missing safety/calendar data as clear.

Every frozen source DTO receives a keyed `source_payload_digest`;the manifest embeds that digest in addition to any source revision. `HealthDayShadowBundle` constructs payload + manifest together and recomputes every digest,so a caller cannot pair changed DTO bytes with an old revision/manifest.

`DailyPlanSubsetFactsDTO` is a closed schema of source facts,not an injectable bag of `planner_flags` or a serialized Twin. The calculator derives only the rules listed below;every other current DOP branch is explicit unsupported/degraded. No title/free prose enters identity or signing. A controlled `training_like` may be derived inside the loader by the exact versioned classifier declared below and is covered,with its classifier version/policy digest,by the source-payload HMAC;raw title never crosses that boundary and an unclassified value stays unknown. Personal prediction enrichment,AdviceGuard/AdviceLedger,complete personal-evidence-matrix flags and the composite training gate are never treated as empty,green or allowed.

The implementation must encode this field-to-source matrix in contract tests;adding a field or derivation requires a schema-version and golden-vector update:

| DTO group | Exact existing source columns | Pure derivation allowed in Phase 1a | Availability/degraded rule |
|---|---|---|---|
| `BodyWeightSubsetDTO` | transient loader input `weight_records(user_id,id,record_date,weight,source)` with `record_date <= local_day`,ordered `record_date DESC,id DESC LIMIT 2` | only when row 2 is absent or older:use row 1's finite decimal weight;for legacy characterization only,`protein_target_g = round(float(weight_decimal or "70") * 1.6)`;using the default adds a controlled reason. Raw `source` is reduced inside the loader to controlled `unique_latest | same_source_duplicate | multi_source_competition` and never crosses the DTO boundary | any second row on the latest date is `daily_plan_weight_source_policy_unsupported`;never silently choose by repaired id or invent a source-priority algorithm |
| `LabAnchorSubsetDTO` | none in the minimal authoring subset;the loader may record source availability only | none | both `lab_anchor_missing` and `lab_anchor_stale` remain `unknown + daily_plan_lab_flag_policy_unsupported`. Current behavior spans abnormal-only `medical_indicators`,name/code matching,other lab sources and a known all-normal-exam edge;an empty tuple must not mean no flag |
| `RecoverySubsetDTO` | transient loader inputs:`garmin_data(user_id,id,record_date,data_source,sleep_score,training_readiness_score)`;`illness_episodes(user_id,id,status,name,start_date,severity)` for `active|improving`;`symptom_entries(user_id,id,occurred_at,body_part,description,severity)` within injected `as_of - 72h`. DTO output retains no raw name/description,only controlled booleans + classifier versions | run two bounded queries:non-null sleep and non-null official readiness,each owner + `record_date <= local_day`,ordered `record_date DESC,id DESC LIMIT 2`;readiness deliberately has no 7-day lower cutoff to characterize current SQL. Use row 1 only when row 2 is absent/older. Derive poor recovery from sleep `<65` or readiness `<50`;derive acute rest from active illness/cold/fever | for either query,row 2 sharing row 1's date means same-source duplicate or multisource competition and yields `daily_plan_recovery_multisource_policy_unsupported`;missing/stale facts retain explicit availability/freshness and never mean green. Computed readiness,TRIMP/ACWR,device agreement and final gate remain unsupported |
| `InterventionSubsetDTO` | transient loader input adds `action_cards.title` to `action_cards(user_id,id,status,is_visible,user_decision,priority,expires_at,created_at,metric_key,target_value,evidence_level,check_back_date)`,ordered `priority DESC,created_at DESC,id DESC` | preserve legacy candidate shape:take SQL top 20 first,then expire against injected `as_of` without mutating rows,do not backfill row 21,and keep first 3. `action_key=intervention.card.<id>`. Inside the loader only,reduce title to controlled `training_like + classifier_version + classifier_policy_digest`;raw title does not cross the DTO boundary | unknown/unclassified intervention under acute rest is retained degraded/non-actionable. The HMAC binds only the derived classifier facts/version/policy digest,not raw title |
| `TerminalActionSubsetDTO` | `intervention_events(user_id,id,plan_date,action_key,feedback_status)` for the controlled terminal statuses,ordered `action_key ASC,id ASC` | drop only that local-day action key;preserve completed-vs-other-terminal provenance | malformed/unknown status is fail-visible,not terminal by guess |
| `ActiveCycleSubsetDTO` | `intervention_cycles(user_id,id,status,cycle_type,start_date,planned_end_date)` plus `outcome_metrics(id,cycle_id,metric_code,status)`,ordered by stable ids | bind controlled IDs/codes/date offsets only | global biomarker display registry/clinician gating and free labels are `daily_plan_cycle_label_policy_unsupported` |
| unsupported current DOP seams | no single same-snapshot persisted field | none | full Twin/personal matrix,computed training gate,AdviceGuard/AdviceLedger,personal predictions and their action filtering/order are `intentionally_unscoped` with the specific reasons above |

For source text that current code parses (`SymptomEntry.description`,ActionCard title),the loader may inspect it only inside the isolated transaction to produce a controlled derived enum/boolean. Raw text does not enter DTOs,digests,logs,telemetry or identity. Tests lock positive/negative characterization and prove that an unclassified value degrades rather than authorizes.

The ActionCard classifier lives in `health_day_shadow_loader.py` (no extra service import) and is exactly:

```text
classifier_version = daily-plan-training-like.v1
terms_in_order = 跑步,训练,力量,HIIT,间歇,冲刺,配速,长跑,马拉松,举铁,重量,健身,workout,gym,run,jog,strength
ASCII term rule = term.lower() in title.lower()
non-ASCII term rule = literal code-point substring in raw title
Unicode normalization = none
```

`classifier_policy_digest` uses the existing `source-payload` signing purpose over a restricted-canonical descriptor containing all semantics,not only the terms:`classifier_version`, `policy_kind`, ordered `terms`, `ascii_match="term.lower() in title.lower()"`, `non_ascii_match="literal_codepoint_substring"`, `unicode_normalization="none"`, `null_input="unavailable"`, and `output_grammar="classification_status:classified|input_unavailable|policy_mismatch;training_like:true|false|null"`. `InterventionSubsetDTO` contains that status,version,digest and derived tri-state;its own source payload digest therefore changes if the result or policy changes. Tests cover every literal term,ASCII case behavior,current substring semantics,Unicode non-normalization,near-miss negatives,null/unknown input and a forged algorithm/version/digest/result.

The acute classifier is independently versioned `daily-plan-acute.v1`. Before classification,the loader selects active/improving illnesses ordered `start_date DESC,id DESC LIMIT 5` and symptoms with `occurred_at >= as_of_utc - 72h` ordered `occurred_at DESC,id DESC LIMIT 10`;the `id` tie is a deterministic repair and tied legacy cases carry `legacy_nondeterministic_tie`. It then applies exactly:

```text
cold_terms = 感冒,发烧,发热,低烧,高烧,咳嗽,咽痛,嗓子疼,喉咙痛,鼻塞,流鼻涕,流涕,打喷嚏,头痛,头疼,畏寒,寒战,乏力,肌肉酸痛,全身酸痛,新冠,流感,上呼吸道
fever_terms = 发烧,发热,低烧,高烧,体温,38,39,40
respiratory_body_parts = general,head,respiratory
looks_like_cold = any(term.lower() in text.lower())
symptom_texts = selected descriptions whose body_part is allowlisted or description looks cold
combined = " ".join(nonempty selected illness names + symptom_texts)
suspected_cold = bool(combined) and looks_like_cold(combined)
fever_reported = any(term in combined for fever_terms)
should_rest = has_selected_active_illness or suspected_cold or fever_reported
guardrail precedence = fever > cold > active illness
Unicode normalization = none
```

`acute_classifier_policy_digest` uses `source-payload` over a descriptor that contains every ordered term/body-part/status list,limits,cutoff inclusivity/order/tie repair,matching/join/normalization rules,guardrail precedence and output grammar. `RecoverySubsetDTO` contains `acute_classifier_version`,policy digest,`has_active_illness/suspected_cold/fever_reported/should_rest/guardrail_code`,availability and no raw text. Tests cover every term/body-part path,near misses,boundary at 72h,the sixth illness and eleventh symptom exclusions,tied-row divergence,guardrail precedence and forged descriptor/result.

Medication-vs-supplement domain reduction is independently frozen as `medication-domain.v1`,characterizing the current `timing_adapter._domain` behavior without importing that service:

```text
supplement_terms = supplement,补剂,保健品,膳食补充剂
input = "" when category is null,otherwise the exact string
trim = input.strip()
ASCII special case = trim.lower() == "supplement"
non-ASCII match = exact trimmed code-point equality against supplement_terms
Unicode normalization = none
domain = supplement on either match,otherwise medication
classification_provenance = exact_supplement | legacy_default_medication | input_unavailable | policy_mismatch
```

`MEDICATION_DOMAIN_CLASSIFIER_V1` and its descriptor include the ordered term set,strip/lower/equality/default/null/Unicode rules and output grammar. The descriptor receives a `source-payload` policy digest. The loader maps raw `medications.category` only transiently to `MedicationSourceDTO.domain + domain_classification_provenance + domain_classifier_version + domain_classifier_policy_digest`;raw category does not cross the boundary. Those derived fields are covered by that source DTO's HMAC. AST characterization locks the descriptor against `_SUPPLEMENT_CATEGORIES` and `_domain`;tests cover every literal,ASCII case and surrounding whitespace,Unicode near misses,null/empty/unknown default behavior,and forged version/digest/result. A policy mismatch is degraded/non-authorizing rather than silently changing identity.

### Unsupported inputs are first-class results

Use controlled reason codes, at minimum:

```text
unsupported_current_composer
safety_snapshot_unavailable
calendar_tombstone_unsupported
calendar_sync_stale
calendar_sync_failed
calendar_timezone_provenance_unknown
calendar_all_day_timezone_provenance_unsupported
calendar_interval_invalid
calendar_event_cap_exceeded
legacy_calendar_busy_precision_unsupported
legacy_flexible_schedule_timing_unsupported
timezone_candidate_invalid
timezone_manifest_profile_mismatch
daily_plan_snapshot_missing
daily_plan_inputs_incomplete
daily_plan_weight_source_policy_unsupported
daily_plan_lab_flag_policy_unsupported
daily_plan_recovery_multisource_policy_unsupported
daily_plan_composite_training_gate_unsupported
daily_plan_advice_guard_unsupported
daily_plan_post_guard_selection_uncomparable
daily_plan_prediction_enrichment_unsupported
daily_plan_intervention_domain_unknown
daily_plan_cycle_label_policy_unsupported
daily_plan_weight_default_used
daily_plan_training_classifier_policy_mismatch
daily_plan_acute_classifier_policy_mismatch
medication_domain_classifier_policy_mismatch
legacy_nondeterministic_tie
source_revision_missing
source_payload_digest_mismatch
legacy_lossy_identity
unsupported_timing_precision
slot_identity_ambiguous
invalid_local_slot
nonexistent_local_time
ambiguous_local_time_without_fold
unsupported_lifecycle_state
protocol_per_meal_occurrence_unsupported
medication_source_occurrence_count_mismatch
medication_daily_marker_multidose_unsupported
medication_off_slot_execution_unsupported
medication_normalized_log_collision
legacy_oracle_baseline_mismatch
ambiguous_comparable_identity
daily_artifact_top_source_unsupported
runtime_future_projection_unscoped
legacy_training_decision_unsupported
legacy_day_schedule_workout_unsupported
legacy_data_quality_unsupported
legacy_wearable_router_unsupported
legacy_protocol_correction_unsupported
legacy_outcome_correction_unsupported
legacy_review_schedule_unsupported
legacy_baseline_deviation_unsupported
legacy_runtime_guidance_unsupported
legacy_timeline_observation_unscoped
legacy_timeline_outcome_unscoped
legacy_timeline_work_unscoped
legacy_timeline_rhythm_unscoped
legacy_schedule_meal_default_unsupported
legacy_schedule_sleep_default_unsupported
legacy_schedule_workout_default_unsupported
standalone_supplement_non_schedule_surface_unscoped
legacy_surface_source_role_unknown
```

Calendar state is exactly `trusted_current | provenance_unknown | stale_unknown | failed_unknown | tombstone_unsupported`. Only a provenance-aware future source could reach `trusted_current` and prove a free window or authorize flexible retiming. Current `calendar_events` rows cannot:the ingestion/schema does not retain whether a timed VEVENT was aware vs floating and converts all-day DATE values through a Beijing instant. The measured loader therefore emits `provenance_unknown` (with `calendar_timezone_provenance_unknown` or `calendar_all_day_timezone_provenance_unsupported`) even when sync freshness is good. Stale/failed/provenance-unknown states may preserve a coarse diagnostic conflict candidate,but empty busy never means free. Fixed source times stay visible with conflict/safety unknown;adaptive/opportunity timing is not calculated or moved.

An unsupported/unavailable safety or calendar source makes the artifact `degraded`;it never makes an item safer or a window free. Phase 1a's assembled integration has no authoritative SafetySnapshotDTO,so safety rows are intentionally unscoped and medication/adaptive occurrences remain non-authorizing with `unknown/degraded` safety.

### Comparable identity

Normalize slots on both sides to user-local integer minute `0..1439`,then match by this order only:

1. `storage_namespace + complete_ref.object_type + object_id + slot_local_minute + dose_ordinal + local_day`;
2. `storage_namespace + source.object_type + object_id + slot_local_minute + dose_ordinal + local_day + projection_role`;
3. explicitly parsed,versioned Schedule IDs such as `med:{id}` plus the context-proven `medication_row` namespace and normalized slot/ordinal;
4. Daily Plan `action_key + local_day`.

Never use title/subtitle/free text as identity. Domain is not a storage namespace:`medication_row(category=supplement,id=1)` and `supplement_definition(id=1)` remain different sources. `agenda_service._smart_id`, DynamicView card IDs, timeline `event_id`, or hashes built from visible health text are not stable occurrence identities.

`8:00` and `08:00` are the same minute. Duplicate normalized slots or invalid local times fail visible as degraded/non-actionable rather than being collapsed. A pure `HH:MM` source defines one wall-clock identity (`local_day + local_minute + dose_ordinal`),not an inferred UTC instant. On a spring-forward day,a nonexistent minute remains one diagnostic row with `nonexistent_local_time + unsupported_precision + actionable=false`. On a fall-back day,an ambiguous minute without explicit offset/fold remains one wall-clock row with `ambiguous_local_time_without_fold + unsupported_precision + actionable=false`;do not choose a fold or duplicate it.

A persisted CalendarEvent `timestamptz` preserves a database instant,but current ingestion may have fabricated that instant from a floating datetime or all-day DATE in Beijing and the schema retains no provenance. For diagnostic conversion only,normalize a non-null interval instant to UTC,then derive user-local wall time,UTC offset,PEP 495 fold and cross-midnight membership with `astimezone(ZoneInfo(effective_timezone))`;never upgrade it to trusted calendar timing. All-day rows are separately unsupported because their original date timezone is lost. The canonical source projection may retain these degraded derived facts;legacy `today_busy_blocks` has already hardcoded Beijing day and collapsed intervals to `HH:MM`,so its adapter must not claim the same precision. Timeline work stays unscoped;Schedule timing is comparable only for an exact source reminder slot proven unchanged by the solver. Flexible/meal/anytime/calendar-influenced legacy timing is `unsupported_precision + legacy_flexible_schedule_timing_unsupported` (and calendar evidence adds `legacy_calendar_busy_precision_unsupported`),never a timing diff. `snoozed`, `adjusted` and `auto_observed` remain distinct canonical lifecycle states;unknown raw states map only to controlled `unknown + unsupported_lifecycle_state` and are not comparable.

Because assembled Schedule rows no longer contain the solver input's `fixed_time`/source-slot consistency and Timeline single-dose rows omit a slot while multi-dose rows do not retain count/duplicate provenance,both adapters receive an additional immutable `LegacyOccurrenceContext` derived only from the untouched,digest-bound candidate bundle—not from an oracle-mutated database or oracle delta. Its key is `(storage_namespace,source_id)`,where namespace is exactly `medication_row | supplement_definition`;domain remains a separate controlled fact,so equal numeric IDs in the two tables cannot collide. Legacy Schedule `med:<id>` and Timeline `complete_ref.object_type=supplement` refer only to `medication_row` rows,including Medication rows classified as supplements;standalone `supplement_definition` rows are never silently matched to those legacy identities. The context maps each source to normalized slots/dose ordinals,count-consistency/versioned domain classification,`exact_reminder | flexible` origin,and conservative calendar state `busy_input_present_and_eligible | no_busy_input | unknown`;it contains no title/free text and grants no authorization. “Calendar participated” is not inferable and must not be claimed. The context is schema/version checked against the manifest and recomputed from HMAC-verified DTOs before Schedule or Timeline projection. If a single-occurrence legacy row moves away from its exact source minute,identity remains bound to that source occurrence but precision is unsupported;for a multi-occurrence or invalid source that cannot be uniquely rebound,the source group on **both** sides becomes `ambiguous_identity`,so it cannot create false missing/extra. Fixed-vs-flexible rows that share `anchor=anytime`,rejected rows without a slot,and Timeline rows with missing/duplicate/count-inconsistent source evidence are classified from this context,never from the assembled payload alone.

### Diff perspective

The canonical shadow is the reference. `missing` means absent from a legacy surface; `extra` means present only on that surface. `rank_changed` compares relative order/top/now within one surface. `timing_changed` requires comparable precision. `safety_changed` covers actionability, lifecycle, blocked/degraded disposition, or controlled safety reason only when that policy declares safety comparable. Every canonical and legacy row must be classified `comparable`, `intentionally_unscoped`, `lossy_identity`, `ambiguous_identity`, or `unsupported_precision`;projectors/adapters may not silently drop rows.

## Task 0: Preflight and isolated PostgreSQL proof target

**Files:** No source changes.

**Step 1: Recheck upstream and overlap**

Run:

```bash
git fetch --prune
git rev-list --left-right --count HEAD...@{upstream}
gh pr list --state open --limit 30 --json number,title,headRefName,baseRefName,url
git status --short --branch
```

Expected:

- explicitly review any new Daily Plan/Agenda/Today/backend PR;
- do not depend on PR #225 or another branch's unmerged code;
- identify the pre-existing unrelated dirty files and preserve them.

**Step 2: Prove the test target is safe**

The schema-copy fixture is destructive test infrastructure. It may run only when all three independent authorities agree:

1. `HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN` is exactly `drop-generated-health-day-shadow-schemas-v1`;
2. the parsed URL is PostgreSQL and its database name matches `(?:^|_)test(?:_|$)`;
3. after connecting,`current_database()` exactly equals the parsed URL database and `health_day_shadow_test_control.safety_marker` contains exactly `('health-day-shadow-v1','schema-ddl-authorized-v1')`.

The marker is created by the ephemeral CI database setup,or manually by a developer only after independently confirming the database is disposable. The Phase 1a fixture never creates or repairs its own authority marker. A database such as `contest`,`latest_prod` or an unmarked `health_test_prod` must fail.

Run:

```bash
export HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1
backend/venv/bin/python - <<'PY'
import os
import re
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

raw = os.environ.get("TEST_DATABASE_URL", "")
if not raw:
    raise SystemExit("TEST_DATABASE_URL is required")
if os.environ.get("HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN") != "drop-generated-health-day-shadow-schemas-v1":
    raise SystemExit("feature-specific schema DDL opt-in is required")
url = make_url(raw)
database = url.database or ""
if url.get_backend_name() != "postgresql" or not re.search(r"(?:^|_)test(?:_|$)", database):
    raise SystemExit("TEST_DATABASE_URL must pass the PostgreSQL test-name heuristic")
engine = create_engine(url, pool_pre_ping=True)
try:
    with engine.connect() as conn:
        actual = conn.execute(text("SELECT current_database()" )).scalar_one()
        marker = conn.execute(text(
            "SELECT marker_value FROM health_day_shadow_test_control.safety_marker "
            "WHERE marker_key = 'health-day-shadow-v1'"
        )).scalar_one_or_none()
        if actual != database or marker != "schema-ddl-authorized-v1":
            raise SystemExit("connected database or Health Day schema-DDL marker mismatch")
finally:
    engine.dispose()
print("postgres-test-target-ok")
PY
```

Expected:`postgres-test-target-ok`. If not, stop;never substitute SQLite,auto-create the marker,or weaken the guard. The same helper and a fresh marker read run immediately before **every** generated-schema `CREATE`/`DROP`,including finalizers;URL validation done once at process start is insufficient.

## Task 1: Lock immutable manifest and item contracts

**Files:**

- Create:`backend/app/services/health_day_shadow_contracts.py`
- Create:`backend/app/services/health_day_composer.py`
- Create:`backend/health_day_shadow_tests/conftest.py`
- Create:`backend/health_day_shadow_tests/test_health_day_composer.py`

**Step 1: Write failing contract tests**

Add tests named:

```python
def test_manifest_requires_explicit_owner_local_day_timezone_and_as_of(): ...
def test_source_results_have_stable_controlled_order(): ...
def test_shadow_item_identity_requires_storage_namespace_source_day_slot_and_ordinal(): ...
def test_shadow_item_identity_schema_has_no_title_subtitle_or_free_text_field(): ...
def test_equal_numeric_ids_in_two_storage_namespaces_are_distinct_contract_values(): ...
def test_snoozed_adjusted_and_auto_observed_remain_distinct(): ...
def test_unknown_lifecycle_fails_visible_instead_of_guessing(): ...
def test_contract_dtos_are_frozen_slots_and_reject_mutable_payloads(): ...
def test_legacy_occurrence_context_schema_requires_manifest_and_payload_digest_binding_fields(): ...
def test_shared_surface_projection_and_diff_types_live_only_in_contracts_leaf(): ...
def test_unsealed_and_sealed_projection_types_have_disjoint_identity_fields(): ...
def test_phase1_subtree_does_not_load_parent_autouse_redis_fixtures(): ...
```

Task 1 tests only immutable schema/invariant behavior implemented in this task. Slot parsing,domain classification,calendar/DST conversion,context derivation and composition behavior are deliberately tested in Tasks 3–5 where their implementations are introduced;Task 1 must not require later behavior to become GREEN.

**Step 2: Run the focused test and confirm RED**

```bash
set -euo pipefail
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_composer.py -q --no-cov
```

Expected:collection/import failure because `health_day_composer` does not exist.

**Step 3: Establish the isolated test subtree and implement a behavior-free contracts leaf**

`backend/health_day_shadow_tests/` is a sibling of `backend/tests/`,not a child. Its local `conftest.py` is the only Phase 1a pytest plugin and must never import or register `backend/tests/conftest.py`. It fails loud if the parent plugin or its `_isolate_twin_cache` / `_noop_twin_cache` autouse fixtures are loaded,defines no shared `db` fixture,and installs a default deny for real Redis,network/provider and ambient global-engine access before each test. Task 7 may replace that deny only through an explicit schema/variant-scoped in-memory fake fixture created in this local conftest;no test may scan/delete a developer Redis key before or after the test. The contract test inspects the active plugin/fixture registry rather than trusting directory naming.

Define every enum/frozen dataclass in `health_day_shadow_contracts.py` using `@dataclass(frozen=True, slots=True)` and controlled enums/literals. This module imports stdlib only and performs no signing,composition,DB access,clock/logging or service call. It defines at minimum:

```python
HealthDaySourceResult
HealthDayShadowManifest
HealthDayShadowBundle
DailyPlanSubsetFactsDTO
CalendarKnowledgeDTO
SafetySeamDTO
LegacyOccurrenceContext
ShadowItemIdentity
ShadowTiming
ShadowSafety
ShadowOrderingFacts
HealthDayShadowItem
HealthDayShadowArtifact
SurfaceRank
SurfaceProjectionPolicy
UnsealedSurfaceProjectedRow
UnsealedCanonicalSurfaceProjection
UnsealedLegacySurfaceProjection
SealedSurfaceProjectedRow
SealedCanonicalSurfaceProjection
SealedLegacySurfaceProjection
ShadowSurfaceDiffRow
```

Rules:

- timestamps are timezone-aware and normalized before construction;
- `local_day` and IANA timezone are explicit; no `date.today()` or China-day helper;
- source results are immutable tuples sorted by one declared source-order constant;
- payload + manifest cannot be constructed independently;the bundle owns both and Task 2 binds every composition-relevant DTO field;
- `LegacyOccurrenceContext` schema contains required manifest schema/digest and source-payload digest bindings plus controlled occurrence facts;Task 4's only public factory derives it from the original `HealthDayShadowBundle` object after calling Task 2 verification with the injected key provider. A `VerifiedBundle`/wrapper type is forbidden:the same bundle object from the same snapshot continues through composition/context derivation. It cannot contain oracle output or claim that a calendar block actually participated;
- ORM instances, mutable dicts/lists, `Session`, provider clients and wall-clock calls are rejected at the boundary;
- `shadow_item_key` remains empty until Task 2 signing; it is not called `occurrence_id`. The contracts leaf exposes no public raw-token binder:its only construction seam is the private `_SIGNED_SHADOW_ITEM_KEY_BINDER`,which accepts an exact unsigned item plus only `[A-Za-z0-9_-]{1,32}\.[0-9a-f]{64}`. Task 2 is the sole allowed importer and exposes the public `health_day_shadow.bind_signed_shadow_item_key(...)` that computes the HMAC before delegating to that private seam;Task 8 locks this import edge.
- shared surface/policy/rank/unsealed/sealed/diff dataclasses are behavior-free schemas only. Unsealed comparable rows carry typed `ShadowItemIdentity` and no opaque key;sealed rows carry only `opaque_item_key` plus controlled projection facts and no raw identity;`ShadowSurfaceDiffRow` carries only the Task 6 allowlist. Projectors,signing and diff import these types from contracts and never define/import one another's shared types.

`health_day_composer.py` initially imports contracts from this leaf and exposes no DB/signing implementation yet. The fixed dependency direction is:

```text
contracts <- signing/summary
contracts + signing <- composer
SQLAlchemy-only source table mapping <- loader
contracts + signing + source table mapping <- loader
contracts <- canonical/legacy surface projectors + diff
```

Add an import-graph test later in Task 8;no reverse edge into contracts is permitted.

**Step 4: Run and confirm GREEN**

Use the command from Step 2.

Expected:all Task 1 contract-only tests pass;no later classifier/loader/composer behavior is asserted yet.

**Step 5: Commit**

```bash
git add backend/app/services/health_day_shadow_contracts.py \
  backend/app/services/health_day_composer.py \
  backend/health_day_shadow_tests/conftest.py \
  backend/health_day_shadow_tests/test_health_day_composer.py
git commit -m "test(health-day): lock shadow composition contracts"
```

## Task 2: Add domain-separated non-authorizing digest

**Files:**

- Create:`backend/app/services/health_day_shadow.py`
- Modify:`backend/health_day_shadow_tests/test_health_day_composer.py`

**Step 1: Write failing digest tests**

Add:

```python
def test_same_manifest_and_key_produce_same_digest(): ...
def test_any_composition_field_change_changes_source_and_manifest_digest(): ...
def test_any_source_or_nested_tuple_order_change_changes_digest(): ...
def test_forged_same_manifest_with_changed_payload_is_rejected(): ...
def test_source_and_manifest_signing_inputs_are_frozen_slots_with_exact_fields(): ...
def test_source_signing_input_has_no_caller_supplied_payload_digest(): ...
def test_bundle_builder_reads_key_provider_exactly_once(): ...
def test_verify_digest_bound_bundle_rejects_each_forged_source_and_manifest_field(): ...
def test_external_revision_binds_revision_acquired_at_cutoff_and_payload(): ...
def test_digest_uses_separate_health_day_shadow_domain(): ...
def test_manifest_source_and_item_use_independent_hkdf_purposes(): ...
def test_item_key_is_slot_sensitive_and_title_independent(): ...
def test_item_key_is_storage_namespace_sensitive_for_equal_numeric_ids(): ...
def test_sign_shadow_item_identity_rejects_missing_or_unknown_storage_namespace(): ...
def test_missing_unknown_or_short_key_fails_closed(): ...
def test_jcs_subset_matches_rfc_8785_string_and_literal_golden_vector(): ...
def test_jcs_subset_rejects_float_datetime_non_ascii_keys_and_lone_surrogates(): ...
def test_jcs_subset_rejects_integer_outside_ijson_safe_range(): ...
def test_jcs_subset_preserves_unicode_without_normalization(): ...
def test_complete_signing_protocol_matches_golden_canonical_frame_key_and_mac(): ...
def test_absent_null_unknown_field_and_scalar_subclass_fail_closed(): ...
def test_safe_repr_scope_hides_signing_value_and_sanitizes_errors_without_a_bundle_repr_contract(): ...
def test_bind_signed_shadow_item_key_accepts_only_task2_token_and_preserves_other_fields(): ...
def test_digest_is_stable_across_fresh_python_processes(): ...
```

The test key provider exposes only `key_id` and at least 32 random bytes. Do not read production settings in these tests.

**Step 2: Run and confirm RED**

Use Task 1's focused pytest command.

Expected:imports or assertions fail because digest support is absent.

**Step 3: Implement and prove the restricted JCS framing**

Define these signing-local input types in `health_day_shadow.py`;they do not move into the Task 1 contracts leaf:

```python
@dataclass(frozen=True, slots=True)
class SourceSigningInput:
    source_kind: HealthDaySourceKind
    source_role: HealthDaySourceRole
    revision: str | None
    acquired_at: datetime | None
    cutoff: datetime | None
    freshness: SourceFreshness
    availability: SourceAvailability
    error_code: ShadowReasonCode | None
    tombstone_state: TombstoneState
    value: SourcePayloadValue = field(repr=False)

@dataclass(frozen=True, slots=True)
class ManifestSigningInput:
    schema_version: str
    owner_id: str
    local_day: date
    timezone: str
    as_of: datetime
    transaction: HealthDayTransaction
    sources: tuple[SourceSigningInput, ...]
```

These are exact closed schemas:unknown/missing fields fail closed,`SourceSigningInput` has no `payload_digest`,and callers cannot supply any digest through a side metadata object. `value` is `repr=False` (an equally strict explicit non-sensitive descriptor is acceptable),and validation exceptions expose only controlled field paths/reason codes—never raw values,key material or tokens. This `safe_repr` obligation applies to these signing inputs and their exception messages only;it does not redefine or require a redacted public `repr(HealthDayShadowBundle)`. Bundles still must never be logged.

Implement an injected `ShadowKeyProvider` protocol and:

```python
canonical_shadow_jcs_subset_bytes(value) -> bytes
build_digest_bound_shadow_bundle(manifest_input, key_provider) -> HealthDayShadowBundle
verify_digest_bound_shadow_bundle(bundle, key_provider) -> None
sign_shadow_source_payload(source_input, key_provider) -> str
sign_shadow_manifest(manifest, key_provider) -> str
sign_shadow_item_identity(manifest_identity, item_identity, key_provider) -> str
bind_signed_shadow_item_key(unsigned_item, *, manifest_identity, key_provider) -> HealthDayShadowItem
```

`health_day_shadow.py` imports stdlib,`cryptography` and the contracts leaf only. The contracts leaf never imports signing;this keeps Task 4's `composer -> signing -> contracts` graph acyclic.

Contract:

- recursively allow only controlled-ASCII built-in dict keys and exact `None | bool | int | str | tuple/list | dict` types;reject subclasses and custom Mapping implementations;
- serialize dataclasses with explicit schema functions,never generic `asdict`;manifest fields are exactly `schema_version,owner_id,local_day,timezone,as_of,transaction,sources`,and envelope fields exactly `key_id,payload,purpose,schema_version`;
- encode owner/source IDs and composition-relevant decimal measurements as validated ASCII strings;normalize every timestamp to UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ` before canonicalization;all optional schema fields are present with explicit `null`;
- reject every float, integers outside `[-(2**53 - 1), 2**53 - 1]`, lone Unicode surrogates, bytes, datetime, arbitrary objects and implicit `default=str`;
- serialize with exactly `json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8", "strict")` after validation;
- ASCII-only keys make Python code-point sorting equal JCS UTF-16 sorting for this domain;excluding floats removes the ECMAScript number-format seam;safe integers, strings, escapes, arrays, literals and objects must match RFC 8785 bytes;
- preserve Unicode strings exactly;never normalize NFC/NFD;
- check in RFC 8785 §3.2 string/literal vectors and test both in-process and in a fresh Python process;
- canonical envelope contains controlled `purpose`, `key_id`, `schema_version`, and payload. Frame exactly two parent-authorized segments:`u32be(len(domain)) || domain || u32be(len(canonical_envelope)) || canonical_envelope`,where domain is `b"health-day-shadow-v1"`;
- key ID grammar is `[A-Za-z0-9_-]{1,32}`. Root key is at least 32 bytes. HKDF is SHA-256, length 32, salt `b"health-day-shadow-v1\x00hkdf-salt-v1"`, info `b"health-day-shadow-v1\x00" + purpose_ascii`;
- purposes are exactly `source-payload`, `manifest-digest`, `item-key`. `build_digest_bound_shadow_bundle` accepts only one `ManifestSigningInput` plus the provider and reads that provider exactly once. For each exact `SourceSigningInput`,it recomputes the `source-payload` HMAC over `source_kind,source_role,revision,acquired_at,cutoff,freshness,availability,error_code,tombstone_state,value`,creates the corresponding `HealthDaySourceResult` with that internal digest,constructs the bundle-owned payload/manifest graph,and only then signs the manifest for the returned `HealthDayShadowBundle`. No public builder argument or signing input accepts `payload_digest`;
- every tuple/list order is composition-relevant and is signed byte-for-byte. The signer never sorts source rows or nested DTO tuples:Task 3's explicit `ORDER BY`/pure normalization owns canonical source order before constructing `ManifestSigningInput`. Reordering interventions,existing DOP actions,normalized medication slots,source rows or any nested tuple must change the source and manifest digests. Top-level sources must already follow `HEALTH_DAY_SOURCE_ORDER_V1`;the builder validates and rejects out-of-order/duplicate kinds instead of silently reordering them;
- `verify_digest_bound_shadow_bundle` pairs each owned payload with its manifest source,rehydrates the exact signing input,recomputes every source HMAC and then the manifest HMAC,and uses `hmac.compare_digest` for every comparison. A changed payload or any forged composition-relevant source/manifest field fails closed even when a stale revision/digest/token is reused. Verification errors expose only controlled reason codes/field locations;they never echo the source value,key material,expected token or received token;
- item-key payload contains exactly schema,owner,local day,`storage_namespace`,source kind/id,normalized local minute,dose ordinal and projection role;title/free text is forbidden. `STORAGE_NAMESPACE_V1` is exactly `medication_row | supplement_definition | health_protocol | health_problem | daily_plan_action`;only comparable rows receive one,while unscoped/lossy diagnostics carry no identity. Namespace cannot be inferred from domain;equal source kind/id values in `medication_row` and `supplement_definition` must yield different MACs. The enum is part of policy/golden vectors. The token is non-authorizing,not durable across test-key rotation and never substitutes for a future occurrence identity;
- ordinary direct construction of `HealthDayShadowItem` with a non-empty `shadow_item_key` remains fail closed. `bind_signed_shadow_item_key` is the sole narrow factory:it obtains only the non-authorizing token produced by Task 2's `sign_shadow_item_identity`,does not accept an arbitrary caller-supplied token string,and returns an item with every field other than `shadow_item_key` preserved exactly. Do not loosen the Task 1 constructor invariant;
- HMAC-SHA-256 output is lowercase 64-character hex;opaque token grammar is `key_id + "." + mac_hex`. Never log either field in Phase 1a;
- one complete fixed-root golden vector covers all manifest/source fields, nested arrays/objects, integer bounds, control characters and decomposed Unicode, and asserts canonical envelope bytes, framed bytes, all three derived keys and final MAC;
- no production key/env fallback. Missing provider is an error, not a raw SHA fallback.

Do not call this a general JCS implementation. A full RFC implementation would need ECMAScript number serialization and UTF-16 ordering for arbitrary keys. Do not add the current `rfc8785` package:stdlib is sufficient for this deliberately restricted domain, and the package does not meet this repository's “updated in the last six months” new-dependency rule.

Normative/provenance links:the [RFC 8785 specification](https://www.rfc-editor.org/rfc/rfc8785.html) is the byte-contract authority;the rejected package's release history remains visible on [PyPI](https://pypi.org/project/rfc8785/). Copy only the minimum expected-byte fixtures needed by the tests and cite their RFC section in comments.

**Step 4: Run and confirm GREEN**

Run the focused composer tests again.

**Step 5: Commit**

```bash
git add backend/app/services/health_day_shadow.py \
  backend/health_day_shadow_tests/test_health_day_composer.py
git commit -m "feat(health-day): add keyed shadow manifest digest"
```

## Task 3: Build the single-session PostgreSQL source loader

**Files:**

- Create:`backend/app/services/health_day_shadow_source_tables.py`
- Create:`backend/app/services/health_day_shadow_loader.py`
- Modify:`backend/health_day_shadow_tests/conftest.py`
- Create:`backend/health_day_shadow_tests/test_health_day_shadow_postgres.py`

**Step 1: Write PostgreSQL-only failing tests**

Seed an explicit owner ID scalar plus its timezone/profile, BID medication, active protocol + event, due HealthProblem, active HealthProgram, calendar source/event, execution fact and an existing DailyOperatingPlan. The Task 3 private Core schema deliberately has no `users` table or cross-table foreign keys. Owner-bearing tables are filtered by their owner column;an owner-less child table (currently `outcome_metrics`) may be read only through IDs selected from its already owner-scoped parent cycle. Do not add an owner column merely for the fixture. Then add:

```python
def test_loader_requires_postgresql_repeatable_read_and_read_only(): ...
def test_loader_keeps_one_mvcc_snapshot_while_second_connection_commits(): ...
def test_loader_derives_effective_timezone_and_local_day_inside_snapshot(): ...
def test_timezone_precedence_manual_detected_legacy_then_fallback(): ...
def test_invalid_timezone_candidate_fails_visible_instead_of_falling_through(): ...
def test_forged_manifest_timezone_or_local_day_mismatch_is_rejected(): ...
def test_weight_latest_day_duplicate_or_multi_source_is_unsupported_not_silently_selected(): ...
def test_sleep_latest_row_is_unique_or_same_day_competition_is_unsupported(): ...
def test_readiness_latest_row_is_unique_or_same_day_competition_is_unsupported(): ...
def test_loader_preserves_all_medication_slots(): ...
def test_medication_execution_binds_only_exact_unique_normalized_slot(): ...
def test_single_occurrence_null_daily_marker_has_explicit_status_semantics(): ...
def test_multidose_null_off_slot_or_normalized_collision_does_not_complete_any_dose(): ...
def test_medication_taken_skipped_delayed_and_unknown_status_map_without_guessing(): ...
def test_loader_reads_weekly_monthly_quarterly_and_annual_events_from_exact_period_start(): ...
def test_loader_binds_every_composition_relevant_source_field(): ...
def test_medication_domain_classifier_matches_every_legacy_literal_and_default_case(): ...
def test_medication_domain_classifier_policy_mismatch_is_degraded(): ...
def test_medication_domain_classifier_matches_legacy_ast_without_importing_service(): ...
def test_action_card_classifier_locks_terms_algorithm_tristate_and_policy_digest(): ...
def test_acute_classifier_locks_terms_filters_limits_precedence_and_policy_digest(): ...
def test_acute_classifier_excludes_sixth_illness_and_eleventh_symptom_before_matching(): ...
def test_classifier_forged_algorithm_version_digest_or_result_fails_closed(): ...
def test_loader_marks_program_composition_and_calendar_tombstones_unsupported(): ...
def test_calendar_sync_failure_is_unknown_not_free(): ...
def test_loader_derives_calendar_local_offsets_fold_and_cross_midnight_from_instants(): ...
def test_loader_marks_original_calendar_offset_fold_provenance_unsupported(): ...
def test_loader_marks_all_day_and_timed_cache_timezone_provenance_unknown(): ...
def test_loader_calendar_overlap_is_half_open_and_dst_day_length_safe(): ...
def test_loader_calendar_null_zero_reversed_or_over_cap_is_fail_visible(): ...
def test_source_table_mapping_matches_all_required_postgres_columns_and_types(): ...
def test_source_table_query_registry_matches_schema_and_dto_matrix_bidirectionally(): ...
def test_unknown_table_column_json_key_owner_filter_or_unbounded_query_fails_closed(): ...
def test_fresh_process_import_never_loads_app_models_database_config_or_fernet(): ...
def test_loader_never_calls_sessionlocal_twin_cache_provider_or_push(): ...
def test_loader_has_no_new_dirty_or_deleted_orm_objects(): ...
def test_database_read_only_cases_each_fail_with_sqlstate_25006_in_fresh_transaction(): ...
def test_clause_allowlist_rejects_cte_do_truncate_temp_call_copy_lock_and_session_effects(): ...
def test_clause_allowlist_rejects_function_set_config_pg_notify_and_volatile_udf_selects(): ...
def test_clause_allowlist_accepts_declared_asc_nulls_first_execution_order(): ...
def test_clause_allowlist_rejects_unknown_or_nested_unary_order_expressions(): ...
def test_clause_allowlist_accepts_grouped_boolean_null_true_false_source_filters(): ...
def test_clause_allowlist_rejects_unknown_constants_or_grouped_non_boolean_expressions(): ...
def test_before_cursor_rejects_exec_driver_sql_without_one_shot_clause_approval(): ...
def test_loader_ast_forbids_exec_driver_sql_raw_connection_driver_connection_and_cursor(): ...
def test_phase1_modules_helpers_and_local_conftest_never_request_shared_db_fixture_or_touch_public_metadata(): ...
def test_loader_explicit_owner_filter_never_reads_second_owner(): ...
def test_shadow_leaves_rows_sequence_temp_guc_notify_and_locks_unchanged(): ...
```

Do not skip when `TEST_DATABASE_URL` is missing:Task 0 already makes the execution stop. Assert dialect exactly `postgresql` inside the fixture. This module must not request the repository's shared `db` fixture or call `Base.metadata.create_all/drop_all`:that fixture mutates `public` under a weaker database-name check and is outside this child Gate.

**Step 2: Create the dedicated generated-schema fixture and transaction helper in the local conftest**

Task 3 adds the schema guard/engine fixture to `backend/health_day_shadow_tests/conftest.py`;it does not import or extend a helper from `backend/tests`. It uses a private loader schema named only `health_day_shadow_loader_[a-f0-9]{32}`. Before its `CREATE SCHEMA`,before `health_day_shadow_source_tables.metadata.create_all`,and again immediately before final `DROP SCHEMA`,the fixture must call the Task 0 authority helper against a fresh connection and revalidate the exact opt-in,current database,test-name heuristic and marker value. It builds only the private source-table metadata inside that exclusive schema through a `NullPool` engine with `schema_translate_map={None: schema}` and `search_path=<schema>`;checkout asserts `current_schema()==schema` and `current_schemas(false)==[schema]`. It never creates,drops,reads or seeds `public`,never imports repo `Base`,and its finalizer refuses any name outside that exact regex. Task 7 may reuse this test-only guard/engine helper,but no production Phase 1a module may import schema-DDL code. Task 3's source-contract test pre-freezes one future-only allowlist slot named `_create_guarded_oracle_schema_v1`:before Task 7 it must be absent;after Task 7 only the exact guarded private-schema `Base.metadata.create_all` shape described there may occupy it. This avoids weakening or rewriting the prior test when the assembled fixture arrives.

Use a dedicated `NullPool` engine and a new connection/session after seed commit:

```python
connection = engine.connect().execution_options(
    isolation_level="REPEATABLE READ",
    postgresql_readonly=True,
)
transaction = connection.begin()
session = Session(
    bind=connection,
    autoflush=False,
    expire_on_commit=False,
    join_transaction_mode="rollback_only",
)
session.execute(text("SET LOCAL statement_timeout = '5s'"))
session.execute(text("SET LOCAL idle_in_transaction_session_timeout = '5s'"))
session.execute(
    text("SELECT set_config('app.user_id', :owner, true)"),
    {"owner": str(owner_id)},
)
assert session.execute(text("SHOW transaction_isolation")).scalar_one() == "repeatable read"
assert session.execute(text("SHOW transaction_read_only")).scalar_one() == "on"
snapshot_id = session.execute(text("SELECT pg_current_snapshot()::text")).scalar_one()
```

Always `transaction.rollback()` and close Session/connection in `finally`;the snapshot ID is assertion-only and never enters the shadow summary.

Attach test guards:

- `before_flush`:fail if `new/dirty/deleted` is non-empty;
- `before_commit`:always fail during the measured shadow phase;
- `before_execute`:walk the whole ClauseElement with default deny. A data query must be one simple single-allowlisted-table `Select`;the only permitted child node families are that table's allowlisted columns,primitive `BindParameter`,exact `Null/True_/False_` constants,controlled boolean `AND/OR`,binary `= != < <= > >= IN IS IS NOT`,an inert `Grouping` only around an already-approved boolean tree,and an allowlisted column ordered by `ASC/DESC` optionally wrapped exactly once by `NULLS FIRST/NULLS LAST`. These nodes explicitly admit declared owner/active/null/date-overlap filters and the `taken_time ASC NULLS FIRST,id ASC` execution-fact query. A Grouping around a value/arithmetic/text/function expression,unknown constant,unknown unary operator,nested null modifier or modifier over a non-column expression is rejected. Also reject joins/subqueries/unions,arithmetic/string expressions,every `FunctionElement`,locking option,prefix/suffix,textual/literal SQL fragment,non-allowlisted FROM,data-changing CTE,Insert/Update/Delete and any unrecognized node. The exact setup/proof TextClause byte strings shown above are the only exception,so `pg_current_snapshot()` and `set_config(app.user_id)` cannot be smuggled through a constructed `Select`. Every approved execution records one connection-local,one-shot approval containing the exact clause category,compiled statement identity and parameter-shape digest;
- `before_cursor_execute`:default-deny unless it can atomically consume the immediately preceding matching one-shot approval. `context.compiled is None`,missing/mismatched/reused approval,or a direct driver statement is rejected before the cursor runs;this makes `Connection.exec_driver_sql()` unable to bypass `before_execute`. After approval matching,the second layer still rejects DML/DDL/DO/TRUNCATE/CALL/COPY/LISTEN/NOTIFY/LOCK, `FOR UPDATE|NO KEY UPDATE|SHARE|KEY SHARE`, `nextval/setval`, advisory locks and transaction-mode/GUC changes,with one deliberately narrow exception:the exact approved TextClause byte strings and parameter shapes for `SET LOCAL statement_timeout = '5s'`,`SET LOCAL idle_in_transaction_session_timeout = '5s'`,and `SELECT set_config('app.user_id', :owner, true)` may execute once as measured-transaction setup. No other `SET`/`set_config`/transaction-mode change is allowed. Exact setup/proof TextClause statements are not independently trusted here:they too must first pass `before_execute`,carry their exact parameter shape,and consume the immediately preceding one-shot approval;
- static AST over every shadow module rejects `exec_driver_sql`, `raw_connection`, `driver_connection`, DBAPI `.connection`/`.cursor` traversal and any call that can obtain a raw cursor. The loader must use only injected SQLAlchemy `Session.execute` against the approved Core statements. Negative tests call `session.connection().exec_driver_sql("SELECT fixture_volatile_udf()")` and representative raw-connection/cursor spellings;the former must be stopped by the cursor gate and the latter must be absent from the feature graph;
- install fail-loud sentinels for `app.database.SessionLocal`,Redis get/set,environment-provider entry points,PushService/outbox and notification producers **without importing those modules**;the fresh-process import hook and local conftest must catch any attempted resolution.

Guard tests and database-authority tests are separate. Each database case disables the custom guard,opens a brand-new read-only transaction and accepts only SQLSTATE `25006`;never accept generic exception or `25P02`. Guard-only cases assert the controlled guard error,including `select(func.set_config('search_path',...))`,`select(func.pg_notify(...))`,a fixture volatile UDF,temp-object operations PostgreSQL may otherwise allow and `exec_driver_sql` with an unlisted volatile/external-effect `SELECT`. Also prove an approval is single-use and cannot authorize the next cursor execution. Compare relevant rows,sequence `last_value`,GUC values,notification listener observations,advisory/relation-lock state and temp objects outside the failed transaction.

**Step 3: Run and confirm RED**

```bash
HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1 \
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
POSTGRES_HOST="" POSTGRES_PASSWORD="" \
REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
SECRET_KEY="test-secret-key-32-chars-minimum!!" \
  GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  -q --no-cov --timeout=120 --timeout-method=signal
```

Expected:import failure because the loader does not exist.

**Step 4: Implement direct, owner-scoped DTO loading**

The loader accepts only the supplied `Session`,authenticated owner ID,an explicit timezone-aware `as_of`,a required valid IANA `fallback_timezone`,and injected external revision fixtures. It does **not** accept an authoritative caller-supplied manifest timezone or local day. Inside the same snapshot it validates every non-null profile timezone candidate and the fallback with `ZoneInfo`,chooses `effective_timezone` by `manual_timezone -> detected_timezone -> legacy timezone -> fallback_timezone`,derives `local_day = as_of.astimezone(ZoneInfo(effective_timezone)).date()`,and only then constructs/signs the manifest. A present invalid higher-precedence candidate is `timezone_candidate_invalid`,not permission to fall through. Bundle verification recomputes this precedence from `ProfileScheduleDTO` and rejects `timezone_manifest_profile_mismatch` or a forged local day. There is no ambient OS/China/default timezone fallback.

It must:

- use `health_day_shadow_source_tables.py` for **all** measured source queries. It owns a private `MetaData`,imports only SQLAlchemy,and defines the exact minimal Core tables/columns listed below. The loader must never import any `app.models.*`, `app.database` or `app.config`;all existing ORM models transitively import the global Base/config/engine,while `app.models.calendar_sync` additionally constructs Fernet from settings at import time;

```text
SOURCE_TABLE_SCHEMA_V1
user_profiles: id,user_id,timezone,detected_timezone,manual_timezone,usual_sleep_time,usual_wake_time,work_start_time,work_end_time,workout_pref_window,workout_target_minutes
weight_records: id,user_id,record_date,weight,source
garmin_data: id,user_id,record_date,data_source,sleep_score,training_readiness_score
illness_episodes: id,user_id,name,start_date,status,severity
symptom_entries: id,user_id,occurred_at,body_part,description,severity
action_cards: id,user_id,title,status,is_visible,user_decision,priority,expires_at,created_at,metric_key,target_value,evidence_level,check_back_date
intervention_events: id,user_id,plan_date,action_key,feedback_status
intervention_cycles: id,user_id,cycle_type,status,start_date,planned_end_date
outcome_metrics: id,cycle_id,metric_code,status
daily_operating_plans: id,user_id,plan_date,status,actions
health_programs: id,user_id,program_type,status,problem_id,started_on,target_end_on
health_protocols: id,user_id,domain,mechanism,implied_quantity,cadence,time_window,completion_mode,can_default_complete,manual_track_allowed,status,program_id,source_model,source_id
health_protocol_events: id,user_id,protocol_id,event_date,status,track,value
health_problems: id,user_id,risk_level,status,follow_up
medications: id,user_id,times_per_day,reminder_times,category,timing_relation,meal_anchor,start_date,end_date,is_active
medication_logs: id,user_id,medication_id,taken_date,taken_time,status
supplement_definitions: id,user_id,timing,is_active,sort_order
supplement_records: id,supplement_id,user_id,record_date,taken,taken_time
calendar_sources: id,user_id,provider,sync_enabled,last_sync_at,last_error
calendar_events: id,user_id,source_id,start_time,end_time,all_day,status,last_synced_at
```

The module declares explicit SQLAlchemy types/nullability for this inventory and nothing else;it never reflects at runtime. Before the measured transaction,a PostgreSQL-only test compares this hand-reviewed inventory against `information_schema.columns` filtered to the exact generated loader `table_schema` for name,type family and nullability,then uses the private mappings in a real typed query;rows from `public` or another schema cannot satisfy parity. Adding/removing/changing a composition column requires an explicit mapping/schema-version/golden update. `title`,illness `name` and symptom `description` are marked transient-classifier-only;`daily_operating_plans.actions`,protocol/follow-up JSON and other raw JSON are reduced through closed field allowlists before any DTO/signature. Calendar encrypted credentials/title/location/description/attendees,medication/supplement names/dosages and all other PII/free prose are not mapped at all.

The loader query/DTO matrix is equally closed:

| Source tables | Owner/filter/horizon | Stable order/limit | Frozen DTO or controlled reduction |
|---|---|---|---|
| `user_profiles` | `user_id == owner`;exactly zero or one row | `id ASC`;duplicate is fail-visible | `ProfileScheduleDTO(timezone,detected_timezone,manual_timezone,sleep/wake/work/workout preferences)`;validate every present IANA value,then precedence is manual→detected→legacy→caller fallback. The derived effective value/local day are the only values signed into the manifest |
| `weight_records` | owner and `record_date <= local_day`;`source` is transient policy evidence only | `record_date DESC,id DESC LIMIT 2` | if row 2 shares row 1's latest date,return `BodyWeightSubsetDTO(weight=null,availability=unsupported,competition=same_source_duplicate|multi_source_competition)`;otherwise return row 1 date/weight with `competition=unique_latest`. Raw source never crosses or enters telemetry |
| `garmin_data` | two separate owner + `record_date <= local_day` queries:one requires non-null sleep score,one non-null readiness;readiness has no lower cutoff | each `record_date DESC,id DESC LIMIT 2`;row 2 on row 1's date is duplicate/multisource competition | unique row 1 becomes the corresponding `RecoveryWearableFactDTO`;same-day row 2 produces no selected value and `daily_plan_recovery_multisource_policy_unsupported`. Tests cover unique,same-source duplicate and two-source competition independently for sleep/readiness |
| `illness_episodes`,`symptom_entries` | owner;active/improving illness and inclusive `as_of-72h` symptom cutoff | illness `start_date DESC,id DESC LIMIT 5`;symptom `occurred_at DESC,id DESC LIMIT 10` | transient text enters only `AcuteSubsetDTO` classifier described above;DTO contains controlled booleans/guardrail/version/digest/severity max |
| `action_cards` | owner,active,visible,decision accepted/adjusted | `priority DESC,created_at DESC,id DESC LIMIT 20`,then expire/no-backfill/first 3 | `InterventionSubsetDTO(action_key,priority,created/expires,metric/target/evidence/check_back,training classification/version/digest)`;no title |
| `intervention_events` | owner and `plan_date == local_day`,controlled terminal statuses only | `action_key ASC,id ASC` | `TerminalActionSubsetDTO(action_key,status,completion_provenance)` |
| `intervention_cycles`,`outcome_metrics` | owner active cycles;outcomes only where `cycle_id IN` the already owner-scoped selected cycle ids | cycle `start_date DESC,id DESC LIMIT 1`;outcome `id ASC` | `ActiveCycleSubsetDTO(id,type,date offsets,primary metric code)`;display/registry/clinician readout excluded |
| `daily_operating_plans` | owner and `plan_date == local_day` | `id ASC`;duplicate violates model contract and fails | `ExistingDOPDiagnosticDTO(id,status,controlled action_key/domain/when fields)`;raw action title/why/evidence text is discarded and row is never canonical input |
| `health_programs` | owner and `status == active` | `started_on ASC,id ASC` | `ProgramInventoryDTO(id,type,problem_id,start/end,availability=unsupported_current_composer)` |
| `health_protocols` | owner and `status == active` | `domain ASC,id ASC` | `ProtocolDTO(id,domain,mechanism,cadence,time_window,completion_mode,default/manual flags,program/source refs,trigger_date)`;from `implied_quantity` only `trigger_date` crosses this slice |
| `health_protocol_events` | owner,selected protocol ids,and cadence-period-start `<= event_date <= local_day` | `protocol_id ASC,event_date ASC,id ASC` | `ProtocolEventDTO(id,protocol_id,event_date,status,track,snoozed_until)`;from `value` only parsed `snoozed_until` crosses |
| `health_problems` | owner and status active/monitoring | `risk_level ASC,id ASC` | `ProblemFollowUpDTO(id,risk,status,last_checkup,cadence,next_due)`;from `follow_up` only those controlled keys cross |
| `medications`,`medication_logs` | active owner medication overlapping local day;logs owner+selected medication ids+local day | medication `id ASC`;logs `medication_id ASC,taken_time ASC NULLS FIRST,id ASC` | raw `category` is transient classifier input only. `MedicationSourceDTO(storage_namespace=medication_row,id,times,normalized unique slots,domain,domain classification provenance/version/policy digest,timing_relation,meal_anchor,date bounds,occurrence_availability)` + `MedicationExecutionDTO(record_id,medication_id,date,raw-slot-presence,normalized slot,status,match disposition)`. Exact binding rules below;names/dosage/raw category/regimen excluded |
| `supplement_definitions`,`supplement_records` | active owner supplement;records owner+selected ids+local day | supplement `sort_order ASC,id ASC`;records `supplement_id ASC,taken_time ASC NULLS FIRST,id ASC` | raw timing is reduced to exact `morning|noon|evening|bedtime|unknown` plus precision status;it never becomes a minute. `SupplementSourceDTO(storage_namespace=supplement_definition,id,timing_label,timing_precision_status,sort_order)` + `SupplementExecutionDTO(record_id,supplement_definition_id,date,normalized time,taken)`;record PK and definition FK are never conflated,names/dosage/category excluded |
| `calendar_sources`,`calendar_events` | enabled owner sources;selected-source events satisfying `start IS NULL OR end IS NULL OR (start < day_end_utc AND end > day_start_utc)`,where the two UTC bounds come from separately constructed effective-timezone local midnights | source `id ASC`;events `start_time ASC NULLS FIRST,end_time ASC NULLS FIRST,id ASC LIMIT 501`;501 means `calendar_event_cap_exceeded` | validate endpoints after load:null/zero/reversed is `calendar_interval_invalid`. `CalendarKnowledgeDTO` carries source sync/error facts,canonical UTC instants and degraded derived user-local interval/offset/fold/cross-midnight only for valid rows;all current rows have original timezone provenance unsupported,all-day gets `calendar_all_day_timezone_provenance_unsupported`,timed cache gets `calendar_timezone_provenance_unknown`,and source state cannot become `trusted_current`. Raw error/UID/encrypted PII excluded |

Every query must match one row of this matrix exactly and use a supplied `Session`;unknown table/column,extra JSON key,missing owner predicate,unbounded horizon,order/limit drift or DTO field not covered by source-payload HMAC fails closed. Architecture tests compare the AST-declared table/column/query registry to `SOURCE_TABLE_SCHEMA_V1` bidirectionally,so unused mapped columns and secretly queried columns both fail.

- assert PostgreSQL + repeatable read + read only via `SHOW`;
- assert the caller supplied exactly one Session bound to the measured connection;never open a nested engine/session;
- query the supported models directly and eagerly convert every result to plain frozen DTOs;
- include stable secondary `id` ordering for every tie;
- load the existing DailyOperatingPlan row only as projection diagnostic without calling its builder;
- load protocol terminal/snooze/event-trigger facts from cadence period start through local day and derive status using explicit `as_of`, not `datetime.now()`;mark current per-meal protocol event uniqueness as `protocol_per_meal_occurrence_unsupported`;
- calculate cadence starts without importing the legacy service:weekly = the local-day Monday;monthly = day 1 of the local month;quarterly = day 1 of month `1 + 3 * ((month - 1) // 3)`;annual = January 1 of the local year. The event window is inclusive `[period_start,local_day]`. Parameterized tests cover all four cadences,Sunday→Monday,month end→day 1,each quarter boundary,a mid-quarter completion,December→January and an annual completion on January 1;
- normalize source reminder slots to unique local minutes,sort by minute and assign zero-based dose ordinal. Duplicate-normalized slots or `times_per_day` inconsistent with a multi-slot source make the medication occurrence set `medication_source_occurrence_count_mismatch/slot_identity_ambiguous`;no execution log may terminate an invented occurrence. A one-dose source with zero/one valid slot has exactly one occurrence;two or more doses require the same number of unique explicit slots in Phase 1a;
- reduce `medications.category` with exactly `MEDICATION_DOMAIN_CLASSIFIER_V1` above before DTO construction. Bind derived domain/provenance/version/policy digest into the source payload HMAC,discard raw category,and fail degraded on policy mismatch. The AST parity test must fail if the legacy `_SUPPLEMENT_CATEGORIES` literal or `_domain` strip/lower/default algorithm changes;
- assign source namespace before identity:every Medication row is `medication_row` even when its derived domain is `supplement`;every standalone definition is `supplement_definition`. `SupplementExecutionDTO.record_id` is the record PK and `supplement_definition_id` is the FK. Tests seed the same numeric id in both tables and prove both canonical facts survive while legacy Schedule/Timeline supplement rows bind only to the Medication-table source;
- bind a MedicationLog only by exact normalized minute to exactly one source occurrence. Never nearest-match. For a true single occurrence only,a `taken_time=NULL` daily marker binds to that one occurrence but has unsupported timing precision;for BID/TID it is `medication_daily_marker_multidose_unsupported + lossy_identity` and terminates none. An off-slot time is `medication_off_slot_execution_unsupported + lossy_identity`. Two raw logs such as `8:00` and `08:00` that normalize to one occurrence are `medication_normalized_log_collision + ambiguous_identity` and terminate none,regardless of equal statuses;
- map a uniquely bound controlled status exactly:`taken -> completed,terminal`;`skipped -> skipped,terminal`;`delayed -> adjusted,nonterminal,degraded/non-authorizing`. Null/other status is `unsupported_lifecycle_state` and does not terminate. Keep log id only inside the frozen source DTO/order evidence;it never becomes occurrence identity or telemetry. A SupplementRecord remains a separate once-per-day definition fact:only `taken=true` completes its single daily occurrence;`taken=false` is nonterminal and its optional `taken_time` is observation precision,not a second occurrence;
- derive follow-up due/overdue from the loader-derived manifest `local_day`,not `get_user_today`;
- build calendar bounds from `effective_timezone` local midnight and the following local date's midnight,then convert to UTC;use the exact half-open overlap above. Convert valid CalendarEvent `timestamptz` values to canonical UTC instants without decrypting or copying title/location/attendees,then call `astimezone(ZoneInfo(effective_timezone))` only for degraded diagnostic wall time/offset/fold/cross-midnight facts. Never use the psycopg-returned `.fold` directly,never claim PostgreSQL retained the external producer's original timezone notation,and never let current all-day/floating-ambiguous cache authorize free/busy or retiming;
- include source `last_sync_at/last_error`, timezone and tombstone capability state;
- encode numeric DB values needed for composition as lossless canonical decimal strings,never binary float in signed primitives:`Decimal(str(value))`,finite-only,fixed-point/no exponent,strip insignificant trailing zeros,and normalize negative zero to `0`. This is storage/composition precision,not the user-display rounding helper. Construct every source's exact primitive DTO schema so Task 2 can recompute its keyed payload digest;
- after every ordered DTO is loaded,construct the exact `ManifestSigningInput` and call `build_digest_bound_shadow_bundle(manifest_input, key_provider)` before leaving the same snapshot;the loader never calculates or passes a `payload_digest` and returns that bundle,not separable manifest/payload objects;
- return explicit unavailable/unsupported source results instead of empty-success;
- fail loud on an actual DB query error because PostgreSQL aborts the read-only transaction; do not rollback and continue with a fabricated partial snapshot.

For the MVCC test use scalar SQL,not an ORM identity-map hit. Barrier order is:shadow reads A -> writer commits B -> a fresh reader confirms B -> shadow issues another scalar SELECT and still reads A. Assert `pg_current_snapshot()`,isolation and read-only values stay unchanged across both reads. Snapshot/owner tests prove explicit filtering and transaction consistency only;do not claim RLS coverage because the CI PostgreSQL role may bypass RLS.

Do not import or call any service/model/database module. Loader imports are allowlisted to stdlib,SQLAlchemy,the SQLAlchemy-only source mapping,and this feature's frozen DTO/signing modules only;all `app.models.*`, `app.database`, `app.config`,settings/secret/Fernet,`SessionLocal`,Twin,Daily Plan/Agenda/Schedule/Artifact/DynamicView/Timeline builders,SafetyGuardian registry,Redis/provider/push paths are forbidden. A fresh-process import test installs fail-loud import hooks for `app.config`, `app.database`, `app.models`, `app.models.calendar_sync` and `cryptography.fernet` before importing the mapping/loader,so a conftest-cached module cannot hide the dependency.

**Step 5: Run and confirm GREEN**

Run Step 3's command.

**Step 6: Commit**

```bash
git add backend/app/services/health_day_shadow_source_tables.py \
  backend/app/services/health_day_shadow_loader.py \
  backend/health_day_shadow_tests/conftest.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py
git commit -m "feat(health-day): load a read-only shadow snapshot"
```

## Task 4: Compose canonical items without a DB handle

**Files:**

- Modify:`backend/app/services/health_day_composer.py`
- Modify:`backend/health_day_shadow_tests/test_health_day_composer.py`
- Modify:`backend/health_day_shadow_tests/test_health_day_shadow_postgres.py`

**Step 1: Write failing composition tests**

Add:

```python
def test_compose_same_complete_manifest_is_byte_deterministic(): ...
def test_compose_does_not_mutate_frozen_input(): ...
def test_missing_dop_does_not_block_bounded_subset_or_materialize_a_plan(): ...
def test_supported_daily_plan_subset_produces_characterized_candidates_without_claiming_legacy_parity(): ...
def test_daily_plan_candidates_carry_pre_guard_non_authorizing_metadata(): ...
def test_absent_composite_training_gate_is_unknown_not_green(): ...
def test_action_card_title_is_reduced_to_versioned_training_like_without_crossing_boundary(): ...
def test_unknown_intervention_domain_under_acute_rest_is_degraded_not_authorized(): ...
def test_expired_intervention_is_filtered_without_mutating_source(): ...
def test_intervention_top20_then_expiry_does_not_backfill_row21_and_keeps_first3(): ...
def test_fixed_medication_and_due_followup_survive_lower_rank(): ...
def test_schedule_rejected_item_remains_visible_and_not_actionable(): ...
def test_canonical_deferred_state_remains_visible_and_not_actionable(): ...
def test_terminal_execution_fact_does_not_resurface_item(): ...
def test_repeated_slots_produce_distinct_shadow_items(): ...
def test_slot_8_00_and_08_00_normalize_to_the_same_local_minute(): ...
def test_duplicate_or_invalid_normalized_slot_is_degraded_and_not_actionable(): ...
def test_bid_tid_slots_and_per_slot_safety_do_not_collapse(): ...
def test_standalone_supplement_definition_composes_once_daily_without_clock_inference(): ...
def test_same_numeric_medication_and_definition_ids_remain_distinct_sources(): ...
def test_weekly_completed_earlier_monthly_and_snooze_as_of_do_not_resurface(): ...
def test_event_triggered_protocol_and_per_meal_unsupported_are_fail_visible(): ...
def test_health_program_is_explicitly_unsupported_not_silently_consumed(): ...
def test_stale_empty_or_nonempty_calendar_never_proves_free_or_retimes(): ...
def test_current_schema_calendar_provenance_unknown_never_proves_free_or_retimes(): ...
def test_fixed_source_time_stays_visible_with_unknown_conflict(): ...
def test_canonical_flexible_or_calendar_eligible_timing_is_unsupported_precision(): ...
def test_occurrence_context_same_anytime_anchor_fixed_vs_flexible_uses_signed_source_facts(): ...
def test_calendar_busy_present_is_conservative_context_not_participation_claim(): ...
def test_legacy_occurrence_context_factory_requires_key_provider_and_verifies_first(): ...
def test_legacy_occurrence_context_factory_rejects_forged_or_different_bundle_digest(): ...
def test_composed_artifact_and_occurrence_context_share_exact_manifest_and_payload_digests(): ...
def test_title_never_participates_in_item_identity(): ...
def test_unsupported_safety_or_calendar_source_degrades_artifact(): ...
def test_new_york_spring_forward_0230_is_nonexistent_and_not_actionable(): ...
def test_new_york_fall_back_0130_without_fold_is_ambiguous_once_not_twice(): ...
def test_calendar_instants_derive_user_local_offset_fold_and_cross_midnight(): ...
def test_calendar_original_source_offset_and_fold_provenance_is_unsupported(): ...
def test_calendar_all_day_beijing_ingest_cannot_claim_new_york_local_date(): ...
def test_calendar_floating_timed_ingest_cannot_authorize_busy_free_or_retime(): ...
def test_calendar_half_open_day_bounds_handle_exact_edges_crossing_and_23h_25h_days(): ...
def test_calendar_null_zero_or_reversed_interval_is_fail_visible(): ...
def test_nonexistent_wall_clock_slot_stays_visible_degraded_and_not_actionable(): ...
def test_ambiguous_wall_clock_without_fold_is_one_non_actionable_occurrence(): ...
def test_cross_midnight_calendar_instant_is_degraded_diagnostic_not_trusted_conflict(): ...
def test_missing_safety_seam_is_unknown_degraded_never_allowed(): ...
def test_composer_never_calls_wall_clock_registry_logging_or_existing_schedule_builder(): ...
```

The pure test calls `compose_health_day(input_bundle, key_provider)` without importing SQLAlchemy.

Task 4 asserts only canonical artifact/context behavior implemented here. It does not call a legacy adapter,sealer or diff. Post-guard legacy scope,cross-surface missing/extra/rank,and two-sided precision reconciliation are Task 5/6 assertions and cannot be prerequisites for this Task's GREEN checkpoint.

**Step 2: Run and confirm RED**

Run both composer and shadow PostgreSQL test files.

**Step 3: Implement the smallest canonical composer**

Inputs and behavior:

- call `verify_digest_bound_shadow_bundle(input_bundle, key_provider)` before any composition rule runs;it recomputes and `compare_digest`-verifies every source payload digest and the manifest digest,so changed payload + reused manifest fails closed without exposing raw values or tokens;
- implement `calculate_shadow_daily_plan_candidates(DailyPlanSubsetFactsDTO, as_of)` and expose that exact name. It derives only the matrix-listed baseline/action-key,weight,single-source recovery,structured acute/intervention,terminal and active-cycle facts in memory;filters expired interventions without changing ORM state;and never sees a Session/AdviceLedger/materializer. The exact sequence is `base diagnostic candidates -> supported acute/official-readiness branch -> accepted interventions -> versioned training_like suppression -> terminal removal -> STOP before AdviceGuard/top-5 -> cycle core bind`. Every returned Daily Plan candidate is pre-AdviceGuard,non-authorizing and carries `actionable=false/degraded + daily_plan_advice_guard_unsupported` plus a controlled `daily_plan_post_guard_selection_uncomparable` scope hint. Task 4 does not inspect or classify a legacy action;Task 5 consumes that hint and symmetrically classifies canonical candidates plus legacy post-guard/top-5 actions on Daily Plan and exact smart-agenda downstream surfaces. Regular Agenda `today` and Timeline `build_today_spine` do not consume that DOP branch and must not invent an exclusion row. The function emits controlled unsupported reasons for lab flags,composite training gate,predictions,unknown intervention domain and registry labels. Existing DOP rows are legacy diagnostics,not canonical input. Do not call this the extracted full DOP calculation half or rewire the live builder in Phase 1a;the parent DOP calculation/materialization split remains blocked until those seams have their own pure contract and G2/G3/G4 evidence;
- normalize protocol cadence-window facts/follow-ups and their explicit lifecycle state;the pure function accepts `local_day/as_of` and never calls user/China/global date helpers;
- implement a new occurrence-level medication/supplement projector over one DTO per normalized slot,explicit `CalendarKnowledgeDTO`,and explicit per-slot `SafetySeamDTO`;do **not** call `schedule_from_medications`,`compute_seam`,SafetyGuardian registry or any existing Day Schedule wrapper. Current-schema calendar state is always non-authorizing provenance/stale/failure/tombstone unknown:it may be surfaced as diagnostic conflict uncertainty but cannot place or move an occurrence;
- parse each source slot into local minute before identity/dedupe,then assign stable dose ordinal. Duplicate-normalized/invalid slots remain degraded/non-actionable diagnostic facts. Validate the resulting wall time against the explicit IANA timezone/local day:nonexistent times get `nonexistent_local_time`;ambiguous times without source offset/fold get `ambiguous_local_time_without_fold`. Both remain a single non-actionable diagnostic occurrence and are never converted to an arbitrary instant;
- preserve canonical schedule `rejected/deferred` with `actionable=False` and controlled disposition. The characterized legacy medication/supplement solver emits only `scheduled/rejected`;a legacy med/supp `deferred` row is an unknown producer/disposition and must not be promoted into the closed comparable set;
- implement the pure `derive_legacy_occurrence_context_from_bundle(bundle, key_provider)` factory. Its first operation is `verify_digest_bound_shadow_bundle(bundle, key_provider)`;only after that succeeds may it schema-check and emit storage namespace,source id,derived domain policy,normalized slots/ordinals,count consistency,fixed/flexible origin and conservative `busy_input_present_and_eligible | no_busy_input | unknown`. It receives and preserves the original bundle object from the measured snapshot—no `VerifiedBundle` wrapper,second load or reconstructed bundle—and never accepts an assembled legacy row,oracle payload/delta or oracle-mutated state. It never infers calendar participation and never performs canonical-vs-legacy comparison or symmetric downgrade;those projector rules begin in Task 5;
- classify prescription medication and due follow-up as fixed;classify pure DOP behavioral actions as adaptive;use `unknown` when the source cannot prove a class. Without immutable safety seam,disposition is `unknown/degraded`,never `allowed`;
- never create an action from a HealthProgram in Phase 1a;mark source unsupported/degraded;
- only `trusted_current` calendar may prove a free window or place/move flexible items. Current-schema provenance-unknown plus stale/failed/tombstone-unsupported states preserve only degraded conflict diagnostics and never infer free;fixed source times remain visible with conflict unknown;
- meal/sleep/workout defaults have no supported immutable source in Phase 1a and are emitted only as diagnostic/intentionally-unscoped coverage,never canonical actions;
- emit each active `supplement_definition` as one canonical daily occurrence with identity `(supplement_definition,id,local_day,dose_ordinal=0,slot=null)` and lifecycle derived only from its exact owner/day `SupplementRecord`. Its raw `timing` never becomes an inferred minute:only exact `morning|noon|evening|bedtime` is retained as a controlled diagnostic label;null/other becomes `unknown + unsupported_precision`. The identity/lifecycle row is comparable on Schedule and Timeline,so absence from current legacy builders is an expected `missing`,not an intentional exclusion;it can never match a Medication-table supplement with the same numeric id;
- merge in declared source order, dedupe only by structured identity, then sort with a total stable key ending in `shadow_item_key`;
- exclude `shadow_run_id` from deterministic artifact comparison;all canonical items/digest remain identical for identical manifest + key.

The pure module import allowlist is stdlib + this feature's DTO/signing module only. Static tests forbid SQLAlchemy,all `app.services`/SafetyGuardian imports,wall-clock helpers,logging,registry access,dynamic import/eval and mutable global caches.

**Step 4: Run and confirm GREEN**

```bash
HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1 \
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  -q --no-cov
```

**Step 5: Commit**

```bash
git add backend/app/services/health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py
git commit -m "feat(health-day): compose canonical shadow items"
```

## Task 5: Project both canonical and legacy surfaces with explicit scope

**Files:**

- Modify:`backend/app/services/health_day_shadow_contracts.py`
- Create:`backend/app/services/health_day_surface_projection.py`
- Create:`backend/app/services/health_day_legacy_projection.py`
- Create:`backend/health_day_shadow_tests/test_health_day_projection_contract.py`
- Create:`backend/health_day_shadow_tests/fixtures/health_day_projection.py`

**Step 1: Write failing adapter tests**

Reuse or translate fixture shapes from:

- `backend/tests/test_daily_artifact.py`;
- `backend/tests/test_today_dynamic_view.py`;
- `backend/tests/test_agenda_range_complete.py`;
- `backend/tests/test_today_timeline.py`;
- `backend/tests/test_agenda_bid_multidose.py`;
- `backend/tests/test_day_schedule_service.py`.

Add:

```python
def test_every_canonical_row_is_classified_for_every_surface_policy(): ...
def test_surface_policies_declare_horizon_cardinality_dedupe_order_top_and_now(): ...
def test_daily_artifact_canonical_projection_is_exactly_top_one(): ...
def test_runtime_future_and_timeline_past_rhythm_outcome_work_are_unscoped(): ...
def test_same_item_can_have_different_dop_agenda_timeline_surface_rank(): ...
def test_daily_plan_adapter_uses_action_key_not_title(): ...
def test_daily_plan_pre_and_post_guard_rows_are_intentionally_unscoped_before_diff(): ...
def test_runtime_artifact_dynamic_dop_roles_inherit_advice_guard_unscoped_classification(): ...
def test_regular_agenda_today_has_no_daily_plan_action_branch(): ...
def test_agenda_adapter_prefers_source_and_keeps_status_canonical(): ...
def test_legacy_source_role_matrix_is_closed_versioned_and_title_free(): ...
def test_every_legacy_source_role_policy_branch_has_a_fixture_obligation(): ...
def test_legacy_producer_site_inventory_matches_scoped_builder_ast(): ...
def test_producer_inventory_required_variant_ids_are_closed_metadata(): ...
def test_each_allowed_multivalue_discriminator_member_has_a_case(): ...
def test_health_protocol_correction_is_not_misclassified_as_due_protocol(): ...
def test_every_protocol_domain_type_v1_is_explicitly_comparable(): ...
def test_null_or_unknown_protocol_domain_fails_to_unknown_source_role_exclusion(): ...
def test_protocol_domain_policy_v1_matches_model_literal_via_ast_without_model_import(): ...
def test_unknown_source_type_status_or_role_fails_to_controlled_exclusion(): ...
def test_source_role_exclusion_propagates_through_runtime_artifact_dynamic_and_timeline(): ...
def test_schedule_adapter_keeps_scheduled_and_rejected_only(): ...
def test_schedule_adapter_treats_med_or_supp_deferred_as_unknown_disposition(): ...
def test_schedule_and_timeline_adapters_require_digest_bound_legacy_occurrence_context(): ...
def test_occurrence_context_keeps_same_numeric_id_across_two_storage_namespaces_distinct(): ...
def test_standalone_supplement_is_canonical_comparable_and_has_no_legacy_cross_namespace_match(): ...
def test_standalone_supplement_is_unscoped_on_non_schedule_non_timeline_surfaces(): ...
def test_schedule_precision_reconciliation_downgrades_moved_source_groups_before_diff(): ...
def test_single_fixed_source_moved_by_interval_keeps_identity_with_unsupported_precision(): ...
def test_multidose_unmatched_legacy_minute_downgrades_both_source_groups_to_ambiguous(): ...
def test_legacy_order_tie_is_fail_visible_instead_of_claiming_parity(): ...
def test_timeline_missing_or_invalid_source_slot_evidence_is_lossy_or_ambiguous(): ...
def test_schedule_default_meal_sleep_and_workout_branches_are_explicitly_unscoped(): ...
def test_schedule_medication_source_requires_exact_med_integer_id_and_domain(): ...
def test_artifact_adapter_compares_only_top_action_semantics(): ...
def test_artifact_dop_top_is_unscoped_but_supported_protocol_problem_top_is_comparable(): ...
def test_artifact_unknown_top_source_fails_to_controlled_exclusion(): ...
def test_dynamic_view_adapter_excludes_cache_and_render_metadata(): ...
def test_dynamic_view_intentional_dedupe_runs_before_diff(): ...
def test_active_high_critical_dynamic_safety_is_explicitly_unscoped_and_degraded(): ...
def test_timeline_adapter_uses_complete_ref_slot_and_excludes_event_id(): ...
def test_timeline_medication_status_ref_action_kind_and_driver_are_closed(): ...
def test_timeline_medication_null_bogus_or_mismatched_discriminators_fail_closed(): ...
def test_timeline_past_is_explicitly_unscoped(): ...
def test_slot_format_and_lifecycle_are_normalized_symmetrically_on_both_sides(): ...
def test_policy_dedupe_runs_before_uniqueness_and_keeps_one_declared_group(): ...
def test_canonical_duplicate_comparable_key_becomes_ambiguous_not_last_wins(): ...
def test_legacy_duplicate_comparable_key_becomes_ambiguous_not_arbitrary_match(): ...
def test_every_canonical_and_legacy_row_has_a_coverage_classification(): ...
def test_no_adapter_uses_title_subtitle_or_free_text_as_identity(): ...
def test_unsealed_comparable_rows_carry_typed_identity_material_not_an_output_key(): ...
```

**Step 2: Run and confirm RED**

```bash
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py -q --no-cov
```

**Step 3: Implement symmetric surface projections**

Use the behavior-free shared `SurfaceProjectionPolicy`, `UnsealedCanonicalSurfaceProjection`, `UnsealedLegacySurfaceProjection`, `UnsealedSurfaceProjectedRow` and `SurfaceRank` dataclasses already defined in the Task 1 contracts leaf;Task 5 must not redefine them in either projector. Add the exact `STORAGE_NAMESPACE_V1`,`PROTOCOL_DOMAIN_TYPES_V1`,`SURFACE_PROJECTION_POLICIES_V1` and `LEGACY_SOURCE_ROLE_MATRIX_V1` as immutable data-only constants to that same leaf—no matching/composition/signing behavior and no reverse imports. Both projectors import the same constants from contracts,never duplicate policy literals. A comparable unsealed row carries a typed `ShadowItemIdentity` as in-memory identity material and no opaque output key;non-comparable rows carry no match identity unless their controlled exclusion policy explicitly needs one. One versioned policy constant per surface declares local-day/horizon,include/exclude roles,cardinality/top-N,dedupe groups,ordering/top/now semantics and whether safety is comparable. Schedule and Timeline policies additionally require a `LegacyOccurrenceContext` produced by `derive_legacy_occurrence_context_from_bundle(the_same_bundle, key_provider)`;calls without it,with a different manifest/schema version,or with context reconstructed from oracle output fail closed.

`project_canonical_surface(artifact, policy, occurrence_context=None)` must classify every canonical item before selecting comparable rows. Global items carry only neutral ordering facts;surface ordinal/top/now is calculated here. Provide one legacy function per surface over already assembled plain dicts. Schedule and Timeline use exactly `(assembled_plain_dict, occurrence_context_from_same_bundle, policy)`;other surfaces use plain payload + policy. That context comes only from `derive_legacy_occurrence_context_from_bundle(the_same_bundle, key_provider)`,whose first operation verifies the unwrapped measured candidate bundle. It may be created after isolated oracle capture,but oracle payload/delta is never an input and the measured bundle is not reloaded or reconstructed in a second snapshot. It supplies only source identity/precision provenance destroyed by the assembled output. Neither side may call a service,DB,endpoint or provider;an unclassified row is an error.

Task 5 owns the two-sided occurrence precision rules. Compare legacy Schedule timing only when `LegacyOccurrenceContext` proves an exact source reminder and the row preserves that normalized minute. Do not infer fixed/flexible from `anchor`,because both can be `anytime`,and never claim a calendar block participated. Flexible rows or `busy_input_present_and_eligible` carry unsupported precision and the controlled reasons above. A moved single occurrence stays source-identity matched but cannot emit timing drift;an unbindable multi-occurrence/invalid source is downgraded on **both** canonical and legacy projections to `ambiguous_identity` before sealing,so later diff emits no false missing/extra. Timeline uses the same context to reject missing/duplicate/count-inconsistent source evidence and to keep `supplement_definition` separate from Medication-table supplement refs.

The legacy side must use one reviewed,versioned `LEGACY_SOURCE_ROLE_MATRIX_V1`;it may inspect only the structured tuple `(surface, source.object_type, complete_ref.object_type, type/action_kind/kind/domain, status/list_disposition, driver, horizon_role, section_role, structured_id_family)`. Normalize these to named fields such as `source_object_type` and `complete_ref_object_type` before policy matching;do not let an arbitrary nested dict reach the matcher. It must never inspect title,subtitle,detail or another free-text field to decide scope. `structured_id_family` is allowed only through an exact versioned parser for governed IDs:Schedule medication/supplement must be exactly `med:<base10 integer>` plus `domain in {medication,supplement}`;other accepted families are `meal:{breakfast|lunch|dinner}`, `sleep:{winddown|caffeine_cutoff}` and `workout:today`. Missing IDs,negative/non-integer suffixes,arbitrary prefixes or free text fail closed.

`PROTOCOL_DOMAIN_TYPES_V1` is the reviewed literal set `hydration,diet,sleep,training,medication,supplement,measurement,mood,activity,exercise,checkup,respiratory`. It is part of the `SurfaceProjectionPolicy` descriptor/version and policy-coverage golden. Tests compare it to the model's `PROTOCOL_DOMAINS` literal through AST without importing `app.models` and exercise every allowed value plus null/bogus values. A new model domain does not become comparable until this policy version and its obligations/golden are explicitly updated.

The closed Agenda-origin families and their downstream disposition are:

| Structured legacy discriminator | Agenda today | runtime today | Artifact/Dynamic hero | Timeline agenda row | Controlled reason when excluded |
|---|---|---|---|---|---|
| `health_protocol`, `type in PROTOCOL_DOMAIN_TYPES_V1`, status in `pending/due/overdue/completed/skipped/snoozed/adjusted/auto_observed`, role=`today_protocol` | comparable | comparable when selected | comparable when selected | comparable | — |
| `health_problem`, `type=checkup`, status in `due/overdue`, role=`today_followup` | comparable | comparable when selected | comparable when selected | comparable | — |
| `daily_plan_action`, status=`pending`, role=`adaptive_action` | — | intentionally_unscoped | intentionally_unscoped | — | `daily_plan_post_guard_selection_uncomparable` |
| `review_schedule`, `type=checkup`, status in `due/overdue` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_review_schedule_unsupported` |
| `training_decision`, `type=training`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_training_decision_unsupported` |
| `day_schedule_workout`, `type=movement`, status in `pending/info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_day_schedule_workout_unsupported` |
| `data_quality`, `type=data_quality`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_data_quality_unsupported` |
| `wearable_router`, `type=data_quality`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_wearable_router_unsupported` |
| `health_protocol`, `type=correction`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_protocol_correction_unsupported` |
| `outcome_correction`, `type=correction`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_outcome_correction_unsupported` |
| `baseline_deviation`, `type=baseline_deviation`, status=`info` | intentionally_unscoped | intentionally_unscoped when propagated | intentionally_unscoped when selected | intentionally_unscoped | `legacy_baseline_deviation_unsupported` |

The same matrix also closes the non-Agenda roles:

| Surface role | Structured legacy discriminator | Disposition | Controlled reason |
|---|---|---|---|
| runtime future protocol/checkup | `horizon_role=future` with `health_protocol` or `health_problem` | intentionally_unscoped diagnostic | `runtime_future_projection_unscoped` |
| runtime synthetic anchor | `source.object_type=runtime_guidance`, `type in {movement,sleep}`, status=`info`, `horizon_role=future` | intentionally_unscoped | `legacy_runtime_guidance_unsupported` |
| Schedule occurrence | exact `med:<base10 integer>`,context-proven `storage_namespace=medication_row`,matching `domain in {medication,supplement}`, disposition in `scheduled/rejected` | identity and exact source reminder minute comparable only when `LegacyOccurrenceContext` proves a valid source occurrence and legacy preserves that minute;flexible/meal/anytime/calendar-eligible timing is unsupported precision;actionability/safety only when the surface policy says comparable. `deferred` is not a reachable medication/supplement disposition and goes to the unknown catch-all | `legacy_flexible_schedule_timing_unsupported` / `legacy_calendar_busy_precision_unsupported` when applicable |
| Canonical standalone supplement on Schedule | `storage_namespace=supplement_definition`,one occurrence per active definition/local day,slot null,dose ordinal 0 | identity + lifecycle comparable;timing precision unsupported unless a later Gate freezes a true clock-time mapping. No current Schedule legacy tuple may match it,so absence is an expected `missing` | no legacy exclusion;unknown raw timing only disables timing diff |
| Schedule generated meal default | `list_disposition=scheduled`, `domain=diet`, `structured_id_family=meal` | intentionally_unscoped | `legacy_schedule_meal_default_unsupported` |
| Schedule generated sleep default | `list_disposition=scheduled`, `domain=sleep`, `structured_id_family=sleep` | intentionally_unscoped | `legacy_schedule_sleep_default_unsupported` |
| Schedule generated workout/default recovery | `list_disposition in {scheduled,rejected}`, `domain=movement`, `structured_id_family=workout_today` | intentionally_unscoped | `legacy_schedule_workout_default_unsupported` |
| Timeline medication/supplement action | `kind=action`, `driver=plan_driven`, `action_kind == complete_ref.object_type in {medication,supplement}`, status in `pending/completed/skipped/overdue`,valid object id and normalized optional slot | comparable | — |
| Canonical standalone supplement on Timeline | `storage_namespace=supplement_definition`,one occurrence per active definition/local day | identity + lifecycle comparable;current Timeline has no matching producer,so absence is an expected `missing` | no legacy exclusion;never bind to `complete_ref.object_type=supplement` because that ref resolves a Medication row |
| Canonical standalone supplement on Daily Plan/Agenda/runtime/Artifact/Dynamic | `storage_namespace=supplement_definition` | intentionally_unscoped;these policies do not define this occurrence in Phase 1a | `standalone_supplement_non_schedule_surface_unscoped` |
| Timeline past observation/insight | `section_role=past` or `kind=observation` | intentionally_unscoped | `legacy_timeline_observation_unscoped` |
| Timeline outcome | `kind=outcome` | intentionally_unscoped | `legacy_timeline_outcome_unscoped` |
| Timeline calendar work | `kind=work` | intentionally_unscoped | `legacy_timeline_work_unscoped` |
| Timeline rhythm card | `kind=advisory`, `driver=time_driven`, `action_kind=day_rhythm` | intentionally_unscoped | `legacy_timeline_rhythm_unscoped` |
| DynamicView safety section | `section_role=safety` | intentionally_unscoped + degraded | `safety_snapshot_unavailable` |

`health_protocol/type=correction` is therefore never treated as a due protocol merely because its `source.object_type` matches;null/bogus/new protocol domains also cannot pass through an open `type != correction` rule. Likewise meal/sleep/workout rows generated unconditionally or from profile preferences by the legacy Schedule are known exclusions,not generic unknowns and not supported medication occurrences. Timeline medication/supplement rows require the exact driver/status/action-kind/complete-ref relation above;null,bogus or mismatched values cannot become comparable. A tuple not covered above,an allowed family with an unknown type/status/disposition/driver/role/id family,or a row missing a required discriminator is classified `intentionally_unscoped + legacy_surface_source_role_unknown`;it cannot become comparable. This catch-all is itself a policy branch and causes the reviewed assembled coverage matrix to fail until a policy-version bump explicitly classifies the new producer.

Policy branch coverage is necessary but not sufficient. Maintain a separate hand-reviewed `LEGACY_PRODUCER_SITE_INVENTORY_V1` with exact `file + enclosing symbol + emitter shape/family + propagated surfaces + required_variant_ids`. Its minimum rows are:

| Producer site(s) | Normalized family emitted | Propagated surfaces |
|---|---|---|
| `daily_operating_plan.py::build_daily_operating_plan(actions)`;`agenda_service.py::_daily_plan_action_items` | post-guard Daily Plan action / `daily_plan_action` | Daily Plan;runtime/Artifact/Dynamic |
| `agenda_service.py::today(protocol loop)` | `health_protocol` × every `PROTOCOL_DOMAIN_TYPES_V1` member and allowed lifecycle | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::today(follow-up loop)` | `health_problem/checkup` | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::_project_course_reviews` | `review_schedule/checkup` | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::_training_item`、`_day_schedule_workout_item` | `training_decision`、`day_schedule_workout` | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::_data_quality_item`、`_wearable_router_quality_items` | `data_quality`、`wearable_router` | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::_self_correction_items`;`baseline_deviation_sentinel.py::_to_advisory` | protocol correction、outcome correction、baseline deviation | Agenda/runtime/Artifact/Dynamic/Timeline |
| `agenda_service.py::_future_protocol_items`、`runtime_range_view(future follow-up)`、`_runtime_anchor_items` | future protocol/checkup、runtime guidance | runtime only |
| `timing_adapter.py::medication_to_item`;`timing_solver.py::solve_day_schedule` | exact `med:<int>` Medication-table medication/supplement × reachable `scheduled/rejected`;checkup-only `deferred` is not claimed for this family | Schedule |
| `schedule_diet_sleep.py::meal_items`、`sleep_items`;`day_schedule_service.py::_maybe_workout_item` | meal、sleep、workout ID families and current dispositions | Schedule |
| `today_spine_meds.py::_single_item`、`_multidose_items` | Timeline medication/supplement action × every allowed lifecycle | Timeline |
| `today_timeline_service.py::_map_observation`、`_past_projection_items`、`_outcome_items`、`_work_items`、`_day_rhythm_items` | past/observation/insight、outcome、work、day rhythm | Timeline |
| `today_dynamic_view_service.py::_safety_alert_card`、`_safety_unavailable_card` | safety section | DynamicView |
| `agenda_service.py::smart_today/runtime_range_view`;`daily_artifact_service.py::build_daily_artifact`;`today_dynamic_view_service.py::_compose_sections`;`today_timeline_service.py::build_today_spine` | propagation/cardinality sites,not new source families | runtime/Artifact/Dynamic/Timeline as declared |

An AST characterization test scans only these scoped builder files/symbols and extracts `_agenda_item`/`Item` calls,structured `source.object_type`/`complete_ref`,Schedule ID-family constructors,list-disposition emitters and Timeline `kind/driver/action_kind` dicts. Literal and explicitly inventoried dynamic expressions are allowed;an unknown emitter/expression/site or an inventory row no longer present fails. Dynamic protocol domain is bound to the separately AST-checked `PROTOCOL_DOMAINS`;dynamic medication domain is bound to `{medication,supplement}`. This is a source-site contract,not an architecture count in prose.

Each inventory row lists real top-level-builder fixture variants that activate the site by seeding data or patching only its upstream provider seam,never by fabricating the assembled adapter output. The integration runner records executed variant IDs and asserts exact set equality with the inventory union;no required or extra variant is allowed. A separate member-case table expands every multi-value discriminator member (all protocol domains/lifecycles,Schedule domains/dispositions,Timeline medication domains/statuses,ID families) and is also set-equal to executed parameterized cases. Thus a dormant/new producer,member or propagation path cannot hide behind an existing catch-all or a default seed.

Exclude at minimum:

- DB/user/event/card IDs that are not source identity;
- generated/updated/expires timestamps;
- `view_id/context_hash/trigger/client_context`;
- render dedupe keys, routes/endpoints, confirmation copy;
- title/subtitle/icon/color/why/evidence/free text;
- raw health readings, medication/diagnosis strings and raw provenance row IDs;
- recomputable counts and static disclaimers.

Preserve normalized-minute + dose-ordinal identity,domain/type,canonical lifecycle/actionability,timing precision,surface-relative ordinal/top/now,schedule disposition,controlled degraded state and projection coverage. Preserve `snoozed/adjusted/auto_observed`;unknown values become non-comparable controlled `unsupported_lifecycle_state`.

DynamicView safety rows are `intentionally_unscoped` in Phase 1a because no immutable SafetySnapshotDTO exists. An active HIGH/CRITICAL fixture must remain explicitly represented and make source availability degraded,but it must not become `extra` or participate in `safety_changed`. Independently,all `daily_plan_shadow_candidate` / legacy `daily_plan_action` rows are intentionally unscoped on Daily Plan and on the exact runtime/Artifact/DynamicView paths that consume `smart_today`,because the two sides straddle AdviceGuard + top-5. The regular Agenda oracle is explicitly `agenda_service.today(...)`,not `smart_today`,and therefore has no DOP branch or DOP exclusion obligation. Runtime-derived DOP rows remain in exact exclusion coverage and cannot produce missing/extra/rank/safety diffs. Timeline's exact builder consumes regular `today`,so it likewise does not claim a DOP row unless its source changes and the producer inventory/policy is bumped. Daily Artifact must branch on structured `top_action.source.object_type`:only `daily_plan_action` inherits that exclusion;supported protocol/problem/checkup sources remain comparable;unknown sources become `intentionally_unscoped + daily_artifact_top_source_unsupported`,never a blanket Artifact exclusion.

After a policy's one declared intentional-dedupe pass,comparable match keys must be unique independently on canonical and legacy sides. Remaining duplicate groups become `ambiguous_identity + ambiguous_comparable_identity`;never build a last-wins dict or pick one row. Task 6 rejects any comparable duplicate that escaped projection.

**Step 4: Run and confirm GREEN**

Run Step 2's command.

**Step 5: Commit**

```bash
git add backend/app/services/health_day_surface_projection.py \
  backend/app/services/health_day_shadow_contracts.py \
  backend/app/services/health_day_legacy_projection.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py \
  backend/health_day_shadow_tests/fixtures/health_day_projection.py
git commit -m "feat(health-day): project canonical and legacy surfaces"
```

## Task 6: Implement deterministic per-surface diff

**Files:**

- Modify:`backend/app/services/health_day_shadow.py`
- Create:`backend/app/services/health_day_shadow_diff.py`
- Modify:`backend/health_day_shadow_tests/test_health_day_projection_contract.py`

**Step 1: Write failing diff tests**

Add:

```python
def test_diff_direction_is_canonical_missing_and_legacy_extra(): ...
def test_diff_detects_relative_rank_top_and_now_changes(): ...
def test_diff_detects_actionability_lifecycle_and_safety_changes(): ...
def test_diff_consumes_symmetric_surface_projections_not_global_artifact(): ...
def test_intentionally_unscoped_safety_and_future_rows_never_become_missing_or_extra(): ...
def test_pre_post_guard_dop_rows_never_become_missing_extra_rank_or_safety_diff(): ...
def test_moved_or_ambiguous_schedule_groups_never_become_false_missing_extra_or_timing_diff(): ...
def test_standalone_supplement_definition_absence_is_exactly_one_expected_missing(): ...
def test_exact_vs_window_is_unsupported_precision_not_false_timing_change(): ...
def test_exact_timing_change_is_detected(): ...
def test_lossy_identity_is_reported_without_title_fallback(): ...
def test_diff_rejects_any_comparable_duplicate_key_that_escaped_projection(): ...
def test_diff_output_has_total_stable_sort_order(): ...
def test_identical_inputs_produce_byte_identical_diff(): ...
def test_outer_sealer_gives_same_hmac_key_to_same_canonical_and_legacy_identity(): ...
def test_legacy_only_extra_receives_item_key_hmac_without_leaking_source_id(): ...
def test_item_key_changes_with_owner_or_test_key_and_ignores_legacy_owner_field(): ...
def test_outer_sealer_requires_storage_namespace_and_equal_ids_cross_namespace_do_not_collide(): ...
def test_sealed_projection_rejects_identity_without_storage_namespace(): ...
def test_diff_rejects_unsealed_forged_or_partially_keyed_projection(): ...
def test_lossy_or_unscoped_row_cannot_smuggle_raw_identity_into_diff(): ...
```

**Step 2: Run and confirm RED**

Run the projection contract test file.

**Step 3: Implement the five-kind diff**

Add `seal_surface_projection(unsealed, *, trusted_owner_id, trusted_local_day, key_provider)` to `health_day_shadow.py`,the existing signing/summary module. It imports the shared sealed/unsealed dataclasses from the contracts leaf;neither signing nor diff defines a duplicate projection type. It:

- accepts only one of the two typed unsealed projection variants and verifies policy/schema/local-day consistency;
- ignores any owner/date fields in legacy payloads and builds the item-key payload from trusted manifest owner/local day plus the row's normalized typed identity material,including the required controlled `storage_namespace`;
- calls the one Task 2 `sign_shadow_item_identity(..., purpose="item-key")` implementation for every comparable row on both sides,including a legacy-only extra;
- returns immutable `SealedCanonicalSurfaceProjection` / `SealedLegacySurfaceProjection` rows containing `opaque_item_key` but no raw source kind/id,identity material,owner/date,title or payload fragment;
- requires every comparable row to have exactly one valid opaque key;missing/unknown namespace,key collisions across distinct typed identities,or a domain-derived namespace fail closed. Lossy/intentionally-unscoped rows have `opaque_item_key=None`. Unknown coverage,key failure,duplicate pre-seal identity or partial sealing fails closed.

This outer decoration keeps the import graph acyclic:canonical/legacy projectors still import only contracts;signing imports contracts;the caller performs `project -> seal -> diff`. No projector duplicates HMAC code or receives key material.

Return immutable rows with only controlled fields:

```python
surface
diff_kind  # missing|extra|rank_changed|timing_changed|safety_changed
opaque_item_key
diagnostic_row_ordinal
reason_code
canonical_coverage
legacy_coverage
```

The function accepts only `SealedCanonicalSurfaceProjection + SealedLegacySurfaceProjection`,never an unsealed projection,global artifact/list or key provider. Both policies/versions must match;unclassified,mismatched-policy,missing/invalid key or any raw identity field fails.

Do not include titles, source IDs, raw times/doses, raw payload fragments or exception text. Comparable rows use opaque item key. A lossy row must not invent identity:`opaque_item_key=None` and a non-sensitive surface-local `diagnostic_row_ordinal` is used only for deterministic diagnostics. Stable-sort by `(surface, diff_kind, opaque_item_key or "", diagnostic_row_ordinal, reason_code)`.

**Step 4: Run and confirm GREEN**

Run the projection contract test file again.

**Step 5: Commit**

```bash
git add backend/app/services/health_day_shadow.py \
  backend/app/services/health_day_shadow_diff.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py
git commit -m "feat(health-day): diff canonical and legacy projections"
```

## Task 7: Prove a real assembled oracle against the measured shadow

**Files:**

- Modify:`backend/health_day_shadow_tests/conftest.py`
- Create:`backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py`
- Modify:`backend/health_day_shadow_tests/fixtures/health_day_projection.py`

**Step 1: Write the isolated-baseline integration test**

The oracle surface registry is exact and versioned;fixtures cannot choose a nearby wrapper/mode/default:

| Surface | Exact builder call after frozen clock/local-day injection |
|---|---|
| Daily Plan | `daily_operating_plan.build_daily_operating_plan(db,user_id,plan_date=local_day)` |
| Agenda today | `agenda_service.today(db,user_id,followup_within_days=14)` (regular mode;never `smart_today`) |
| runtime | `agenda_service.runtime_range_view(db,user_id,days=1,max_items_per_day=4)` |
| Schedule | `day_schedule_service.build_day_schedule(db,user_id,forbidden_reasons=None,ctx_overrides=None)` |
| Daily Artifact | `daily_artifact_service.build_daily_artifact(db,user_id,artifact_date=local_day,followup_within_days=7,top_action_id=None)` |
| DynamicView | `today_dynamic_view_service.build_today_dynamic_view(db,user_id,trigger="open",client_context=None)` |
| `/timeline/today` | `today_timeline_service.build_today_spine(db,user_id)` |

`LEGACY_ORACLE_SURFACE_REGISTRY_V1` stores these symbols and arguments;an AST/signature test plus expected payload `mode` where present prevents default/parameter drift. The regular Agenda registry has no Daily Plan producer obligation. Runtime/Artifact/Dynamic may carry smart-agenda DOP exclusions;Timeline currently consumes regular Agenda and has none.

Add integration tests named:

```python
def test_oracle_surface_registry_uses_exact_symbols_arguments_and_modes_v1(): ...
def test_inventory_required_cases_equal_collected_real_builder_cases_v1(): ...
def test_schema_ddl_authority_rejects_missing_opt_in_marker_database_mismatch_and_bad_name(): ...
def test_every_create_and_drop_revalidates_authority_and_never_touches_public(): ...
def test_assembled_case_manifest_equals_inventory_policy_and_golden_obligations_v1(): ...
def test_assembled_parametrization_uses_each_case_id_exactly_once_v1(): ...
def test_assembled_projection_matches_reviewed_golden_case_v1(case): ...
def test_oracle_order_is_stable_for_bounded_target_surface_case_v1(order_case): ...
```

Baseline preparation:

1. define immutable `ASSEMBLED_CASE_MANIFEST_V1` rows as controlled `case_id,variant_id,surface_id,producer_obligations,golden_id`;it contains only required inventory/policy cases,not a blind Cartesian product. Case/variant/golden IDs use `[a-z0-9_-]+` and contain no owner/source ID,health text or time. Exactly one `pytest.mark.parametrize(..., ids=case_id)` binds `test_assembled_projection_matches_reviewed_golden_case_v1` to this manifest. That single node performs the baseline-equality,same-bundle context,applicable two-storage and expected projection/diff assertions together;do not create four separately parametrized DDL tests for the same case. Collection/source tests prove every case ID is unique,each required producer/policy/golden obligation maps to exactly one case,and no test/fixture/helper in that node loops over the full manifest,all variants or all surfaces. A separate bounded `ORDER_CASE_MANIFEST_V1` has exactly one controlled base-variant target case for every surface in `LEGACY_ORACLE_SURFACE_REGISTRY_V1`,with a reviewed predecessor/order label;set equality between its target surfaces and the registry is mandatory. It detects cache/module-state bleed without multiplying across every producer variant;
2. for **one collected case node only**,require the already validated PostgreSQL test database and feature-specific opt-in. Immediately before every DDL operation,re-read and validate the Task 0 database marker/current database. Generate only target names matching `health_day_shadow_(candidate|oracle|poison)_[a-f0-9]{32}`. A golden case creates exactly one untouched candidate schema,one fresh oracle schema for its declared surface,and one minimal poison schema. An order case creates only the two fresh oracle captures plus the minimal poison schema needed for its target comparison;no node creates all seven surfaces or runs another variant internally;
3. build a separate `NullPool` engine per schema with both `schema_translate_map={None: schema}` and exclusive connection `search_path=<schema>` (implicit `pg_catalog` only;no `public` fallback). Every checkout asserts `current_schema() == schema` and `current_schemas(false) == [schema]`,and records schema/backend PID. Candidate measured checkout uses the same assertion;
4. create the same model schema through the single local `_create_guarded_oracle_schema_v1` helper and deterministic seed in every full copy:owner/profile/timezone,BID medication,supplement,protocol/cadence events,due follow-up,program,calendar source/event,execution facts and supported raw Daily Plan source rows. That helper alone imports repo `Base`/models inside the function and calls `Base.metadata.create_all(bind=guarded_schema_engine)` only after the fresh authority + exact exclusive-schema checks;it never touches the original engine or `public`,and no `Base.metadata.drop_all` is allowed. The poison schema contains only its sentinel objects. Do not clone from a schema after any builder ran;
5. never write `public`. Production-shaped oracle/candidate engines keep the exclusive one-schema search path and assert the poison schema is absent;one deliberately misconfigured negative engine (`target,poison`) proves the checkout assertion fails before any query. Final before/after checks prove the poison rows remain unchanged. Attach a fail-loud checkout listener to the app's original/global engine while oracle/measured phases run;
6. compute an ordered semantic baseline fingerprint over the same explicit composition DTO schemas and Task 2 keyed source digests in every full copy;never use/log a raw low-entropy hash. Exclude schema name and generated DB metadata. Assert the case's pre-oracle fingerprint equals its untouched candidate fingerprint before continuing;
7. freeze clocks/network/provider fixtures globally. Each case capture gets a brand-new empty fake Redis/cache namespace keyed by schema,then destroys it after capture;reset every discovered module-local cache. Assert each first Twin lookup is a miss and no get/set crosses a schema namespace.

Legacy oracle capture:

1. patch every statically inventoried `SessionLocal` alias in the target builder's transitive graph to that surface's sessionmaker;all fresh/nested sessions must appear in its checkout log and pass the exact-schema assertion. Any original/global-engine checkout fails;
2. call only that surface's real top-level builder and capture its assembled plain payload;
3. validate DynamicView with `validate_dynamic_view` and Timeline with `TodaySpineResponse.model_validate`;
4. record the builder's ordered DB delta against its pre-oracle fingerprint,close every connection/destroy that cache namespace,and never copy those rows/digests into the candidate schema;
5. finish that one case and return. The separately parametrized order case compares its target surface under the two reviewed fresh capture orders,using fresh schema/cache state for every capture,and asserts normalized payloads are identical;the helper rejects schema reuse. Neither test loops over surfaces or variants internally.

Measured candidate:

1. confirm its semantic fingerprint still equals the original baseline,then open the one `REPEATABLE READ, READ ONLY` Session with all guards;
2. load one digest-bound `bundle` and keep that exact unwrapped object from the untouched candidate snapshot;call `derive_legacy_occurrence_context_from_bundle(bundle, key_provider)` (which first calls `verify_digest_bound_shadow_bundle(bundle, key_provider)`),then compose canonical items,project canonical and legacy sides through matching surface policies,and compute diffs. Oracle capture may have happened earlier in its isolated schemas,but no oracle payload/delta enters verification or context derivation. Assert the same bundle object/manifest digest is used throughout and prohibit a `VerifiedBundle` wrapper,second loader call or cross-snapshot reconstruction;
3. run the same bundle/composition twice and assert byte-identical canonical projections/diffs;
4. assert normalized BID slots remain distinct,fixed/rejected facts remain visible,calendar/safety unknown remains degraded,active HIGH/CRITICAL safety is explicitly unscoped,and every row on both sides has coverage;
5. assert candidate rows/sequences/temp objects remain unchanged and no forbidden call fired.

The fixture contains hand-reviewed `LEGACY_PRODUCER_SITE_INVENTORY_V1`,`POLICY_COVERAGE_OBLIGATIONS_V1`,`ASSEMBLED_CASE_MANIFEST_V1` and `EXPECTED_ASSEMBLED_MATRIX_V1`,none generated/updated from runtime under test. Producer AST parity and exact required-vs-collected-case set equality run first. The obligations table then has exactly one stable branch id for every row/disposition/reason in `LEGACY_SOURCE_ROLE_MATRIX_V1`,including canonical-only scope branches and the unknown legacy catch-all;set equality among policy branch ids,obligation ids and case-manifest obligations is mandatory. Parameterized plain-payload tests activate every obligation and every allowed multi-value member. Independently seeded real-builder cases collectively activate every inventoried producer site on each propagated surface,so a dormant branch cannot hide behind the default seed. Daily Artifact has at least two such cases:`dop_top` (exact DOP exclusion expected) and `supported_non_dop_top` (protocol/problem/checkup top must be comparable);the producer cases additionally cover training decision,day-schedule workout,both data-quality sources,both correction families,review schedule,baseline deviation,runtime guidance,the generated Schedule meal/sleep/workout rows,calendar/DST flexible timing and each Timeline-native role. A two-storage-same-id case seeds `medication_row(id=1,domain=supplement)` plus `supplement_definition(id=1)` and requires both canonical identities on Schedule/Timeline,only the Medication-table row matched,and exactly one standalone-definition `missing` per applicable surface;the same definition is exactly one controlled unscoped row on every other surface. Each collected case gets fresh oracle/candidate state and cannot reuse a builder-mutated schema. `EXPECTED_ASSEMBLED_MATRIX_V1` is keyed by the same unique `case_id`;for that one variant/surface it lists:

- exact canonical comparable semantic identities and count;
- exact legacy comparable semantic identities and count;
- exact `(coverage, reason_code) -> count` for every intentional/lossy/ambiguous/precision exclusion;
- exact expected diff rows/kinds for the seeded BID slots,known Schedule precision/loss and safety-unscoped case.

`test_legacy_producer_site_inventory_matches_ast_v1` and `test_assembled_case_manifest_equals_inventory_policy_and_golden_obligations_v1` prove source-site/case coverage;`test_policy_coverage_obligations_match_every_source_role_branch_v1` proves policy/fixture set equality;the parametrized `test_assembled_projection_matches_reviewed_golden_case_v1` compares one bounded reviewed case per node. A new producer/member/exclusion,uncovered source-role branch,coverage shrink or diff change fails;intentional contract changes require inventory/policy/case-manifest version bumps plus reviewed obligation and golden updates. There is no snapshot auto-update flag. Zero diff is not required,but exact expected coverage/diff is.

No Phase 1a code path may create/drop schemas;that logic lives only in the PostgreSQL test fixture. Immediately before **each** create/drop and every finalizer cleanup,the fixture revalidates the exact opt-in,current database,test-name heuristic and authoritative marker through a fresh connection. Cleanup may drop only names matching `health_day_shadow_(candidate|oracle|poison)_[a-f0-9]{32}`;it never touches `public` or the control-marker schema. This test never uses TestClient in the measured candidate or the repository shared `db` fixture. Oracle commits are evidence of legacy impurity,never permission for shadow writes.

**Step 2: Run the isolated RED, then the cumulative GREEN**

```bash
HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1 \
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
POSTGRES_HOST="" POSTGRES_PASSWORD="" \
REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
SECRET_KEY="test-secret-key-32-chars-minimum!!" \
  GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  -q --no-cov --timeout=120 --timeout-method=signal
```

Expected RED:first missing isolated-schema/oracle/fixture/golden wiring. Task 7 is fixture-and-evidence-only:do not modify a production projector,adapter,signer,diff or no-write guard here. If RED exposes a production behavior defect,return to the owning Task 4,5 or 6,add the focused RED case there,make that task GREEN and commit it,then restart Task 7 from fresh schemas.

After fixture implementation,do **not** reuse the RED-only command as the GREEN checkpoint. Rerun every module that already exists under the changed local plugin:

```bash
HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1 \
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
POSTGRES_HOST="" POSTGRES_PASSWORD="" \
REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
SECRET_KEY="test-secret-key-32-chars-minimum!!" \
GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  -q --no-cov --timeout=120 --timeout-method=signal --durations=20
```

Expected GREEN:the real assembled comparison produces deterministic,classified evidence under PostgreSQL,the Task 1/3/4/5 contracts still pass under the modified `conftest.py`,and the result is **not** required to have zero diffs. Record the fresh elapsed summary and 20 slowest nodes:every node must be `<90s` and this four-module suite `<1500s`,leaving headroom under the later 120s/30m hard limits. If either target fails,split the case manifest into a smaller stable unit and rerun;do not raise a timeout in Task 7. Any proposed larger budget returns to child G2 with measured evidence.

**Step 3: Commit**

```bash
git add backend/health_day_shadow_tests/conftest.py \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  backend/health_day_shadow_tests/fixtures/health_day_projection.py
git commit -m "test(health-day): prove assembled read-only shadow"
```

## Task 8: Lock architecture, telemetry privacy, and no-skip evidence

**Files:**

- Create:`backend/health_day_shadow_tests/test_health_day_shadow_architecture.py`
- Create:`backend/scripts/assert_pytest_no_skips.py`
- Modify:`backend/app/services/health_day_shadow.py`
- Modify:`backend/health_day_shadow_tests/test_health_day_shadow_postgres.py`

**Step 1: Write failing architecture/privacy tests**

Add static AST/import and behavior tests:

```python
def test_each_shadow_module_matches_its_exact_import_allowlist(): ...
def test_shadow_feature_import_graph_is_acyclic_and_contracts_is_a_leaf(): ...
def test_shadow_modules_have_no_dynamic_import_eval_registry_clock_or_logging(): ...
def test_shadow_has_no_router_task_scheduler_or_startup_registration(): ...
def test_shadow_has_no_sessionlocal_cache_provider_push_or_notification_call(): ...
def test_shadow_has_no_driver_sql_raw_connection_driver_connection_or_cursor_escape(): ...
def test_phase1_test_tree_contains_no_skip_skipif_or_importorskip(): ...
def test_phase1_test_tree_never_requests_shared_db_or_uses_unguarded_base_metadata(): ...
def test_only_local_guarded_oracle_schema_factory_may_call_base_create_all(): ...
def test_phase1_test_tree_never_imports_parent_conftest_or_parent_fixtures(): ...
def test_phase1_local_conftest_blocks_real_redis_provider_network_and_global_engine(): ...
def test_assembled_cases_use_exact_collection_manifest_without_inner_variant_or_surface_loop(): ...
def test_junit_no_skip_gate_fails_on_any_skipped_case(): ...
def test_junit_no_skip_gate_rejects_missing_or_empty_report(): ...
def test_junit_no_skip_gate_fails_when_any_required_module_has_no_executed_case(): ...
def test_junit_no_skip_gate_accepts_executed_cases(): ...
def test_junit_timing_gate_rejects_missing_invalid_slow_case_or_slow_suite_time(): ...
def test_junit_timing_gate_accepts_bounded_case_and_suite_times(): ...
def test_shadow_summary_is_aggregate_allowlist_only(): ...
def test_shadow_summary_contains_no_owner_date_digest_key_item_or_health_text(): ...
def test_shadow_module_logging_cannot_receive_raw_manifest_payload_or_diff_rows(): ...
```

Use per-file module allowlists,not only a symbol denylist:

- contracts:`stdlib` only;no behavior or reverse feature imports;
- source table mapping:`SQLAlchemy` only with private metadata/the closed minimal column inventory;no `app.*`,config,crypto or reverse feature imports;
- signing/summary:`stdlib + cryptography + contracts` only;
- composer:`stdlib + contracts + signing` only;
- canonical surface projector/legacy projector/diff:`stdlib + contracts` only;
- loader:`stdlib + SQLAlchemy + source table mapping + contracts + signing` only;all `app.models.*`, `app.database` and `app.config` are explicitly forbidden;
- no shadow module may import an `app.services` module outside this eight-file feature set,dynamically import/eval,read wall clock,call logging/registry,or keep a mutable global cache.

The test-tree source contract recursively scans every `*.py` under `backend/health_day_shadow_tests/`,including `conftest.py`,all five modules and `fixtures/health_day_projection.py`. It rejects requests for or indirect fixture dependencies on `db`,imports/plugin registration of `backend/tests/conftest.py` or `backend/tests/fixtures`,public-schema DDL,real Redis scan/delete/client construction,ambient provider/network access and a production global engine. The only `Base.metadata` exception is one statically named local helper,`conftest.py::_create_guarded_oracle_schema_v1`:inside that function only,a normal function-local import may load repo `Base`/models,then `Base.metadata.create_all(bind=guarded_schema_engine)` may run after the fresh Task 0 authority check and exact exclusive-schema checkout assertion. No test module/helper may call it directly;only the Task 7 generated-schema fixture may. `Base.metadata.drop_all` is forbidden everywhere;cleanup uses the guarded exact-name `DROP SCHEMA` path. The AST contract rejects any second call site,different bind,missing guard predecessor,public/default engine or import of Base/models outside this helper. It also requires the assembled test's collection-time `parametrize` to reference the exact immutable case manifests and rejects a loop/recursive expansion over variants,surfaces or case manifests anywhere in that parametrized test's fixture/helper call graph,so one JUnit testcase remains one bounded DDL unit. This is one closed boundary for all five modules;putting a dependency in another helper does not evade it. The runtime fixture-registry assertion additionally proves `_isolate_twin_cache` and `_noop_twin_cache` are absent before any Phase 1a test body runs.

Defense-in-depth forbidden symbols/imports include at least:

```text
SessionLocal
build_twin
build_daily_operating_plan
guard_and_record_advice
agenda_service.today
smart_today
runtime_range_view
build_day_schedule
schedule_from_medications
compute_seam
evaluate_rules_with_status
build_daily_artifact
build_today_dynamic_view
build_today_spine
med_supplement_items
maybe_materialize_workout_chain
materialize_agenda_event
exec_driver_sql
raw_connection
driver_connection
cursor
PushService
NotificationLog
Celery/task decorators
FastAPI/APIRouter
```

**Step 2: Run and confirm RED**

```bash
set -euo pipefail
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py -q --no-cov
HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1 \
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  -q --no-cov --timeout=120 --timeout-method=signal
```

**Step 3: Implement allowlisted summary and mechanical no-skip gate**

`summarize_shadow_run(...)` returns only:

```text
schema_version
overall_status
source_status_counts
diff_counts_by_surface_and_kind
degraded_reason_codes
duration_bucket
```

It does not itself log or persist. Reject unknown fields. Never include owner/date/timezone/digest/key_id/source IDs/item keys/times/titles/free text/raw manifest/raw diff/exception messages or any medication/supplement/diagnosis/lab value.

`assert_pytest_no_skips.py REPORT --require-module NAME ... --max-case-seconds 90 --max-suite-seconds 1500` parses JUnit XML and validates module names against `[a-z0-9_]+`. It fails on any `<skipped>`,missing/malformed/empty report,any required module without at least one executed testcase (derive module from normalized JUnit `file`/`classname`,not substring-only matching),or a missing/non-finite/negative testcase/suite time. It requires every testcase duration `< max-case-seconds` and the report's authoritative suite duration `< max-suite-seconds`;boundary equality fails to preserve headroom under pytest's 120-second hard timeout and the job's 1800-second timeout. Nested/multiple suites are summed once without double-counting testcase times. It prints only aggregate executed/skipped/required-module counts and duration buckets/maximum value;never node IDs or health fixture text. This is the G3 mechanical backstop because pytest's normal exit code treats skips as success and a timeout setting alone does not prove the parametrization fits its budget.

**Step 4: Run and confirm GREEN**

Run Step 2's command.

**Step 5: Commit**

```bash
git add backend/app/services/health_day_shadow.py \
  backend/scripts/assert_pytest_no_skips.py \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py
git commit -m "security(health-day): lock no-side-effect shadow boundary"
```

## Task 9: Run focused regressions and update generated system-map facts

Before touching CI/generated files,run `git fetch --prune` and re-read open PRs. PR #252 was open at planning time and overlaps `.github/workflows/ci.yml` plus generated system-map facts. If it has merged,rebase/reconcile this task against the new `main` and update the release-contract assertions to the new job graph;while it remains open,do not implement Task 9 against an assumed stale CI layout. This concurrency check does not relax any dedicated-job/aggregate/no-skip requirement below.

**Files:**

- Modify:`.github/workflows/ci.yml`
- Modify:`scripts/test_release_ci_contract.py`
- Modify if generated:`docs/_generated/system-map.json`
- Modify if generated:`docs/_generated/system-map-agent-context.md`
- Modify:`docs/dossiers/2026-08-15-health-day-read-only-shadow.md`
- Modify:`docs/dossiers/2026-08-15-quiet-proactive-health-day.md`

**Step 1: Run the complete new Phase 1a suite**

```bash
set -euo pipefail
PHASE1A_TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/health-day-phase1a.XXXXXX")"
PHASE1A_JUNIT="$PHASE1A_TMP_DIR/report.xml"
trap 'rm -f "$PHASE1A_JUNIT"; rmdir "$PHASE1A_TMP_DIR"' EXIT
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py -q --no-cov
export HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1
DATABASE_URL="$TEST_DATABASE_URL" TEST_DATABASE_URL="$TEST_DATABASE_URL" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-phase1a.sock" \
  SECRET_KEY="test-secret-key-32-chars-minimum!!" \
  GARMIN_ENCRYPTION_KEY="mI4nYXirjGlbHD7sFogYlqPQJzirU04mUsS5LyDS0SU=" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py \
  -q --no-cov --timeout=120 --timeout-method=signal \
  --junitxml="$PHASE1A_JUNIT"
backend/venv/bin/python backend/scripts/assert_pytest_no_skips.py \
  "$PHASE1A_JUNIT" \
  --require-module test_health_day_composer \
  --require-module test_health_day_projection_contract \
  --require-module test_health_day_shadow_postgres \
  --require-module test_health_day_shadow_assembled_postgres \
  --require-module test_health_day_shadow_architecture \
  --max-case-seconds 90 \
  --max-suite-seconds 1500
```

Expected:all pass;zero skip for PostgreSQL semantics.

**Step 2: Run existing projection/safety regressions**

```bash
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  POSTGRES_HOST="" POSTGRES_PASSWORD="" \
  REDIS_URL="unix:///nonexistent/health-day-shadow-regression.sock" \
  TZ=Asia/Shanghai backend/venv/bin/python -m pytest \
  backend/tests/test_daily_operating_plan_arbitration.py \
  backend/tests/test_planner_personal_evidence_matrix.py \
  backend/tests/test_day_schedule_service.py \
  backend/tests/test_schedule_diet_sleep.py \
  backend/tests/test_workout_prescription.py \
  backend/tests/test_agenda_contract.py \
  backend/tests/test_agenda_range_complete.py \
  backend/tests/test_agenda_bid_multidose.py \
  backend/tests/test_daily_artifact.py \
  backend/tests/test_today_dynamic_view.py \
  backend/tests/test_today_timeline.py \
  backend/tests/test_timeline_spine_medications.py \
  backend/tests/test_atomic_capabilities.py \
  -q --no-cov
```

Expected:all pass on their established isolated SQLite fixture path. These legacy regression files must never inherit the marked Phase 1a PostgreSQL URL or DDL opt-in:their shared `db` fixture calls global `Base.metadata.drop_all/create_all` in `public` under a weaker historical guard. Empty `POSTGRES_HOST` and `POSTGRES_PASSWORD` are explicit because project settings otherwise prefer non-empty `.env` PostgreSQL fields over `DATABASE_URL`,including inside nested `SessionLocal` calls. Their parent autouse cache fixture also scans/deletes real Redis keys,so the command pins an impossible Unix-socket URL before Python imports config;connection failure is immediate and no developer/shared Redis can be reached. `scripts/test_release_ci_contract.py` locks this exact isolation tuple. A true regression returns to the responsible task;do not weaken legacy tests or no-write guards.

**Step 3: Make PostgreSQL semantics a blocking CI path**

First extend `scripts/test_release_ci_contract.py` and confirm RED. The contract must assert:

- all five exact modules,local `conftest.py` and fixture helper live under `backend/health_day_shadow_tests/`,which is outside `backend/pytest.ini`'s exact `testpaths=tests`. No SQLite shard path/default runner (`backend-test-shards`,`backend/scripts/system_health_score.py`,root `scripts/run-all-tests.sh`) names or discovers this sibling tree,and no directory-ignore workaround is needed. The source/fixture contract scans the whole sibling tree and proves it neither loads `backend/tests/conftest.py` nor requests its shared fixtures;
- a new blocking job named exactly `health-day-shadow-postgres` has its own PostgreSQL 16 service database `health_day_shadow_test`,`needs: classify-changes`,`if: run_backend == true`,and a bounded whole-job `timeout-minutes: 30`. It installs the locked backend dependencies and runs all five exact Phase 1a modules,not only helper-only pure tests. Per-test timeout is also exact `--timeout=120 --timeout-method=signal`;changing either budget requires measured evidence and a reviewed contract update;
- the aggregate `backend-tests` job adds `health-day-shadow-postgres` to `needs`,exports its result as `HEALTH_DAY_SHADOW_POSTGRES`,prints it in the aggregate line,and requires `success` whenever backend scope runs. The existing `agent-runtime-postgres` job and its 20-minute budget remain unchanged;
- that PostgreSQL step contains none of the Step 2 legacy regression modules;those remain on their normal SQLite shards. A contract fixture for the documented/manual regression command requires explicit `env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN`, `DATABASE_URL=sqlite:///:memory:`,empty `POSTGRES_HOST`/`POSTGRES_PASSWORD`,and `REDIS_URL=unix:///nonexistent/health-day-shadow-regression.sock` so an exported or `.env` database target cannot leak into shared/nested sessions and its parent cache cleanup cannot reach real Redis;
- the step starts with `set -euo pipefail` and declares its own complete env because step env does not carry over:`DATABASE_URL`/`TEST_DATABASE_URL` pointing at the service DB,empty `POSTGRES_HOST`/`POSTGRES_PASSWORD` so `.env` cannot override them,`REDIS_URL=unix:///nonexistent/health-day-shadow-phase1a.sock`,`TZ=Asia/Shanghai`,`HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN=drop-generated-health-day-shadow-schemas-v1`,and the same test-only `SECRET_KEY` plus valid `GARMIN_ENCRYPTION_KEY` already used by the Runtime/medication step. Before any pytest process can see the PostgreSQL URL,the step first runs the architecture/shared-fixture preflight in a subprocess with `TEST_DATABASE_URL` and DDL opt-in explicitly unset;only a green preflight proceeds to marker bootstrap/PG tests. The release contract asserts this order and every key/value class without printing secrets;
- before pytest,the ephemeral PostgreSQL job executes the exact idempotent control-marker bootstrap below with `psql -v ON_ERROR_STOP=1`;the release contract checks the schema/table/key/value literals and proves the pytest command follows a successful bootstrap. Test code itself must still refuse to create/repair the marker;
- after the deliberate no-PG architecture preflight,the full JUnit pytest argv runs with `--no-cov`/bounded timeout and lists each of the five module paths exactly once;it immediately runs `assert_pytest_no_skips.py` with each of the five exact `--require-module` arguments exactly once plus exact `--max-case-seconds 90 --max-suite-seconds 1500`;
- source-contract tests prohibit `skip`, `skipif` and `importorskip` across the entire Phase 1a test tree and prohibit shared `db`/public `Base.metadata` paths in every module,local plugin and helper.

```bash
backend/venv/bin/python -m pytest scripts/test_release_ci_contract.py -q --no-cov
```

Then update `.github/workflows/ci.yml` with the dedicated job described above;do not alter the existing SQLite shard discovery or reuse the Runtime PostgreSQL job/database. The Health Day job's test step has `working-directory: backend` and its own DB URLs,TZ,test-only `SECRET_KEY`,valid `GARMIN_ENCRYPTION_KEY`,`PGPASSWORD` and exact DDL opt-in;do not assume another job/step's env persists. Its multiline shell is mechanically equivalent to:

```bash
set -euo pipefail
env -u TEST_DATABASE_URL -u HEALTH_DAY_SHADOW_TEST_DDL_OPT_IN \
  DATABASE_URL="sqlite:///:memory:" \
  TZ=Asia/Shanghai python -m pytest \
  health_day_shadow_tests/test_health_day_shadow_architecture.py -q --no-cov
psql "$TEST_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
CREATE SCHEMA IF NOT EXISTS health_day_shadow_test_control;
CREATE TABLE IF NOT EXISTS health_day_shadow_test_control.safety_marker (
  marker_key text PRIMARY KEY,
  marker_value text NOT NULL
);
INSERT INTO health_day_shadow_test_control.safety_marker(marker_key, marker_value)
VALUES ('health-day-shadow-v1', 'schema-ddl-authorized-v1')
ON CONFLICT (marker_key) DO UPDATE SET marker_value = EXCLUDED.marker_value;
SQL
PHASE1A_TMP_DIR="$(mktemp -d "${RUNNER_TEMP}/health-day-phase1a.XXXXXX")"
PHASE1A_JUNIT="$PHASE1A_TMP_DIR/report.xml"
trap 'rm -f "$PHASE1A_JUNIT"; rmdir "$PHASE1A_TMP_DIR"' EXIT
python -m pytest \
  health_day_shadow_tests/test_health_day_composer.py \
  health_day_shadow_tests/test_health_day_projection_contract.py \
  health_day_shadow_tests/test_health_day_shadow_postgres.py \
  health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  health_day_shadow_tests/test_health_day_shadow_architecture.py \
  -q --no-cov --timeout=120 --timeout-method=signal \
  --junitxml="$PHASE1A_JUNIT"
python scripts/assert_pytest_no_skips.py "$PHASE1A_JUNIT" \
  --require-module test_health_day_composer \
  --require-module test_health_day_projection_contract \
  --require-module test_health_day_shadow_postgres \
  --require-module test_health_day_shadow_assembled_postgres \
  --require-module test_health_day_shadow_architecture \
  --max-case-seconds 90 \
  --max-suite-seconds 1500
```

This bootstrap is allowed only because the CI service database is ephemeral;local test code never executes it. The job-level service/env contract pins `postgresql://postgres:postgres@localhost:5432/health_day_shadow_test` without exposing credentials in test output. Leave the existing Runtime/medication job unchanged,wire the new result into `backend-tests`,then run the contract command again and require GREEN.

**Step 4: Regenerate code-derived system facts**

New backend service files change architecture inventory, so run:

```bash
python3.12 scripts/dump_system_map.py
./scripts/system-map-check.sh
```

Never hand-edit architecture counts.

**Step 5: Update Dossiers with real evidence**

Only after fresh commands pass:

- move the child from S3/S4 to the actual reached Gate;
- record exact test counts, PostgreSQL target class (not credentials), commit SHA and independent G4 review;
- leave the parent umbrella G2 blocked and link the completed Phase 1a evidence;
- do not call the Health Day user experience shipped.

**Step 6: Run repository document gates**

```bash
python3.12 backend/scripts/check_dossier_consistency.py
python3.12 scripts/validate.py
./scripts/system-map-check.sh
git diff --check
```

**Step 7: Inspect the exact diff and stage only owned files**

```bash
git status --short
git diff --stat
git diff -- backend/app/services/health_day_composer.py \
  backend/app/services/health_day_shadow_contracts.py \
  backend/app/services/health_day_shadow_source_tables.py \
  backend/app/services/health_day_shadow.py \
  backend/app/services/health_day_shadow_loader.py \
  backend/app/services/health_day_surface_projection.py \
  backend/app/services/health_day_legacy_projection.py \
  backend/app/services/health_day_shadow_diff.py \
  backend/health_day_shadow_tests/conftest.py \
  backend/health_day_shadow_tests/test_health_day_composer.py \
  backend/health_day_shadow_tests/test_health_day_projection_contract.py \
  backend/health_day_shadow_tests/test_health_day_shadow_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_assembled_postgres.py \
  backend/health_day_shadow_tests/test_health_day_shadow_architecture.py \
  backend/health_day_shadow_tests/fixtures/health_day_projection.py \
  backend/scripts/assert_pytest_no_skips.py \
  .github/workflows/ci.yml \
  scripts/test_release_ci_contract.py \
  docs/dossiers/2026-08-15-health-day-read-only-shadow.md \
  docs/dossiers/2026-08-15-quiet-proactive-health-day.md \
  docs/_generated/system-map.json \
  docs/_generated/system-map-agent-context.md
```

Then add only files that actually changed. Never use `git add -A`.

**Step 8: Final implementation commit and push**

```bash
git commit -m "feat(health-day): add read-only shadow composer"
git push origin main
```

If earlier tasks already created all source commits, this final commit contains only Dossier/generated-doc evidence. Do not deploy:Phase 1a deliberately has no runtime caller.

## G3/G4 handoff checklist

- [ ] New suite ran on isolated PostgreSQL with no skip.
- [ ] All five modules/helpers stayed in the isolated sibling test tree,were absent from default SQLite discovery,and appeared exactly once in the dedicated job's full JUnit suite;the architecture module additionally passed its deliberate no-PG preflight before marker bootstrap. The blocking `health-day-shadow-postgres` result was wired into `backend-tests`.
- [ ] Every legacy surface ran in its own baseline-identical schema;oracle deltas never entered the untouched candidate, and order permutation did not change normalized payloads.
- [ ] Measured session proved `repeatable read` + `read only`.
- [ ] A second connection committed while the measured Session retained one MVCC snapshot.
- [ ] Direct DML/sequence/locking plus constructed `FunctionElement`/GUC/notify/volatile-UDF negative tests failed closed;row/sequence/temp/GUC/notification/lock state stayed equivalent.
- [ ] DML/DDL, flush, commit, SessionLocal, Redis/provider and push traps remained untriggered.
- [ ] Real legacy oracle ran only before the measured transaction.
- [ ] Same digest-bound bundle/key produced byte-identical artifact and diff.
- [ ] Every composition-relevant DTO mutation—including any source-row or nested-tuple reorder—changed its keyed source/manifest digest;the signer performed no hidden sorting,and forged payload/manifest pairs were rejected.
- [ ] Bounded Daily Plan subset and medication projectors made no legacy service/registry/clock/logging call;the subset stopped before AdviceGuard/top-5 and never claimed full DOP parity.
- [ ] BID/TID slots stayed distinct.
- [ ] `8:00`/`08:00` normalized equally;duplicate/invalid slots failed visible;effective-timezone New York spring-forward/fall-back wall-clock tests and UTC-instant diagnostic fold/offset/cross-midnight fixtures passed;current all-day/floating cache remained provenance-unknown/non-authorizing,half-open 23h/25h bounds and invalid intervals were covered;protocol cadence windows and unsupported per-meal identity were explicit.
- [ ] Fixed and rejected Schedule items stayed visible with correct actionability;canonical deferred facts stayed visible,while an unreachable legacy med/supp deferred tuple failed to the controlled unknown branch.
- [ ] Calendar/safety unknown stayed degraded, never free/safe.
- [ ] Every legacy row received a coverage classification.
- [ ] Every canonical row received a surface-policy classification;top-N/horizon/dedupe/rank semantics were surface-specific.
- [ ] Aggregate summary passed privacy allowlist tests.
- [ ] RFC 8785 restricted-subset golden vectors, I-JSON integer bounds, Unicode preservation and fresh-process determinism passed.
- [ ] No API/client/task/scheduler/DB migration/runtime wiring exists.
- [ ] Independent safety review found no blocker/high issue.
- [ ] Parent umbrella Dossier remains G2 BLOCK.

## Rollback

The code is dormant. Rollback is deletion/revert of the eight new internal service modules,the no-skip test utility,their fixtures/tests and generated system-map changes. There is no data migration, persisted shadow state, endpoint, client contract, notification, scheduled work or production flag to clean up. Never “rollback” by wiring the shadow to an existing writeful legacy builder.
