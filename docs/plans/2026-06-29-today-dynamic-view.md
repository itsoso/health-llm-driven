# Today DynamicView Implementation Plan

**Goal:** Make Mobile Today consume an Aheng-generated `mobile.today` DynamicView while preserving the current static Today page as fallback.

**Architecture:** Backend owns the view composition contract and builds it from existing `DailyArtifact` plus `agenda.runtime_range`. Mobile fetches the contract on Today open/refresh and renders allowlisted cards/components through a small renderer.

**Tech Stack:** FastAPI, SQLAlchemy service functions, pytest, Expo React Native, React Query, Jest, TypeScript.

## Task 1: Backend DynamicView Contract

Files:
- Create: `backend/app/services/today_dynamic_view_service.py`
- Create: `backend/app/api/dynamic_views.py`
- Modify: `backend/app/api/main.py`
- Test: `backend/tests/test_today_dynamic_view.py`

Steps:
1. Write failing contract test for `POST /api/v1/dynamic-views/today`.
2. Verify RED: route/service missing.
3. Implement `build_today_dynamic_view(db,user_id,trigger,client_context)` from existing `daily_artifact_service.build_daily_artifact` and `agenda_service.runtime_range_view`.
4. Register router through `get_current_user_required`.
5. Verify GREEN.

## Task 2: Mobile Service And Renderer

Files:
- Create: `mobile/services/todayDynamicView.ts`
- Create: `mobile/components/home/DynamicTodayRenderer.tsx`
- Modify: `mobile/app/(tabs)/index.tsx`
- Test: `mobile/services/__tests__/todayDynamicView.test.ts`
- Test: `mobile/components/home/__tests__/DynamicTodayRenderer.test.tsx`
- Test: `mobile/app/(tabs)/__tests__/home.test.tsx`

Steps:
1. Write failing service and renderer tests.
2. Add service types and POST client.
3. Add renderer for `daily_artifact` plus registered server cards.
4. Integrate TodayScreen with React Query key `['today-dynamic-view','mobile.today']`.
5. Render DynamicView only when sections are present; otherwise keep existing static layout.

## Task 3: Integration Verification

Run:

```bash
DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai backend/venv/bin/python -m pytest backend/tests/test_today_dynamic_view.py backend/tests/test_daily_artifact.py backend/tests/test_inline_cards_runtime_agenda.py -q --no-cov
```

Run:

```bash
cd mobile && npm test -- --runTestsByPath app/\(tabs\)/__tests__/home.test.tsx services/__tests__/todayDynamicView.test.ts components/home/__tests__/DynamicTodayRenderer.test.tsx --runInBand
```

Run:

```bash
cd mobile && npx tsc --noEmit --pretty false
python3 -m compileall -q backend/app/api/dynamic_views.py backend/app/services/today_dynamic_view_service.py
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
```

## Task 4: Release

1. Stage only Today DynamicView related files.
2. Commit and push to `main`.
3. Deploy backend through `./deploy.sh -b`.
4. Publish Mobile OTA through `./scripts/mobile-ota.sh production "<message>"`.
5. Smoke test backend health and `POST /api/v1/dynamic-views/today` authentication behavior.
6. Update Dossier G5/G6 with deployment identifiers.
