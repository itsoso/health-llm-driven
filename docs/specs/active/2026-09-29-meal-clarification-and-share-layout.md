# Meal clarification and share-location layout

> 历史本地审计补录（2026-10-03）：以下状态、测试数、发布 SHA 与回执来自原工作树既有记录，未在本次整合中重新验证；不是当前生产状态或本轮发布 Gate 的新鲜证据。本轮整合与验证见 docs/dossiers/2026-10-03-local-change-integration.md。

> Status: shipped (runtime 8bd2655b6; post-release audit in related dossier)
> Updated: 2026-09-29
> Related: R5/R10; dossier 2026-09-29-share-location-and-meal-continuation

## Decision / admission

Repair existing meal interaction truth and poster layout, without adding implicit
write authority. Objects: ExecutionEvent and existing meal WriteIntent. Mobile is
the daily surface; backend authenticated execution facts remain source of truth.
The first-user benefit is fewer duplicate/mislabelled meals and a readable public
share. This is a health-write/privacy-sensitive bugfix with no medical claim,
no autonomy elevation and same-turn verification. One clarification question is
justified when the required image or target is missing. No GPS, new database
schema, provider, native permission or automatic public-location inference.

## User and surface contracts

- Confirmed location -> compact badge in the poster content panel -> image and
  caption use the same normalized value. Empty means absent. Long food/location
  copy may grow the panel; nutrition and footer must not be clipped.
- A current request to record a meal from an absent image -> no create/update
  dispatch -> explicit request to attach the image and waiting_for_user outcome.
- Bare portion or meal-type correction without an authenticated, unambiguous
  target -> one target clarification, no guessed meal/time and no new record.
  Existing explicit named-meal/latest-meal correction paths remain unchanged.
- Backend uses existing turn-outcome/goal states; stream, panel and persisted
  reply agree. Mobile's existing waiting-for-user presentation is reused.
  No new API, enum or migration. Legacy fields retain existing compatibility.

## Safety and AI boundary

Recognition of a missing input is not authorization to read or write. Quotes,
negation, cancelled actions, third-party subjects and unsupported compound
requests cannot be reduced to a permitted write. Existing gateway, owner,
record/date verification, idempotency and receipt checks remain authoritative.
Model prose cannot establish success or record identity. No private health data
or image is added to committed fixtures; synthetic fixtures only.

## Acceptance / verification

RED/GREEN UI tests prove no photo overlay, compact width, absent blank label and
long-label containment. iOS simulator renders current component bytes with
clearly labelled synthetic fixture data; no claim of live GPS or hardware QA.
Backend tests reproduce absent-image and referential correction failures through
ordinary/panel trajectories; assert no mutation and identical public/persisted
outcomes. Existing explicit-correction tests remain green; PostgreSQL is required
if persistence semantics change. Run CI-mode integration, relevant Jest/tsc,
System Map, secret scan, live-model gate when required, and independent G4.

## Rollout / rollback

Only owned files enter a clean candidate. Backend and JS-only UI use their
separate release gates. Uncommitted GPS/AMap/native/privacy work is excluded.
Do not bypass failed gates or include unrelated changes to make an OTA build.
Rollback is the previous reviewed runtime revision/update, without data rewrite.

## Changelog

2026-09-29: bounded missing-input/target clarification and location layout repair.
Shipped after non-image attachment safety remediation, fixed-commit GO, exact CI,
backend health verification and production iOS 1.3.4 OTA readback. No GPS/native
permission rollout or automatic historical meal targeting included.
