# App Store MVP Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship a focused Reva Mobile App Store MVP that has a unified UI, a core daily health flow, privacy/account controls, and a realistic submission path for next week.

**Architecture:** Keep Backend as truth source and Mobile as the consumer MVP. Do not create new medical semantics; reuse existing HealthKit, report import, Chat, Record, Today, Agenda, and Review paths. App Store compliance work is additive and auditable.

**Tech Stack:** FastAPI, SQLAlchemy, React Native / Expo Router, Jest, pytest.

---

## Scope

P0 for this batch:

- Reframe Mobile “Me” as a user-facing App Store hub instead of an internal feature index.
- Add an authenticated account deletion request endpoint that records an audit row and fails loud if the request cannot be recorded.
- Add Mobile UI to start the deletion request with a destructive confirmation flow.
- Update privacy-policy wording to explain HealthKit, AI, account deletion, and non-diagnostic boundary.

Deferred:

- Full hard-delete/anonymization across all health tables.
- New onboarding wizard.
- New native entitlements.
- Rokid/IoT/supply-chain as App Store v1 selling points.

## Execution Status

- [x] Task 1: Backend Account Deletion Request
- [x] Task 2: Mobile Account Deletion Flow
- [x] Task 3: Mobile Me Information Architecture
- [x] Task 4: Privacy Policy Wording
- [x] Task 5: Verification
- [ ] Release batch: App Store metadata, screenshots, native archive, App Store Connect submission, true-device validation.
  - Batch 2 plan/materials: `docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md`
  - Batch 3 simulator build / QR path: `docs/plans/2026-06-28-app-store-mvp-release-batch3-plan.md`
  - Batch 4 screenshot compliance gate: `docs/plans/2026-06-28-app-store-mvp-release-batch4-plan.md`
  - Batch 5 final screenshot export gate: `docs/plans/2026-06-28-app-store-mvp-release-batch5-plan.md`
  - Batch 6 iOS submission preflight gate: `docs/plans/2026-06-28-app-store-mvp-release-batch6-plan.md`
  - App Store Connect source pack: `docs/release/app-store/`
  - Deterministic gate: `python3 scripts/check_app_store_release_pack.py`

## Task 1: Backend Account Deletion Request

**Files:**

- Modify: `backend/app/api/auth.py`
- Test: `backend/tests/test_account_deletion_request.py`

**Steps:**

1. Write failing tests:
   - unauthenticated `POST /api/v1/auth/me/deletion-request` returns 401.
   - authenticated request returns `requested` and writes one `AgentAuditLog` with `agent_type=account_privacy`, `action=account_deletion_requested`.
2. Implement endpoint using `get_current_user_required`.
3. Write `AgentAuditLog` directly, commit before response, and raise 500 if audit write fails.
4. Run focused pytest.

## Task 2: Mobile Account Deletion Flow

**Files:**

- Modify: `mobile/services/auth.ts`
- Modify: `mobile/app/settings.tsx`
- Test: `mobile/app/__tests__/settings.test.tsx`

**Steps:**

1. Add `requestAccountDeletion()` service calling `/auth/me/deletion-request`.
2. Add “账号与隐私” section in Settings/Me.
3. Add destructive “删除账号与数据” row with `Alert.alert()` confirmation.
4. On success, show status and call `logout()`.
5. Update tests to verify the row exists and calls the endpoint after confirm.

## Task 3: Mobile Me Information Architecture

**Files:**

- Modify: `mobile/app/settings.tsx`
- Test: `mobile/app/__tests__/settings.test.tsx`

**Steps:**

1. Group visible rows into App Store MVP sections:
   - 数据连接
   - 健康档案
   - 复盘与计划
   - 通知与安全
   - 账号与隐私
2. Hide or move experimental/internal entries below a debug section that is clearly not primary.
3. Keep routes reachable; do not delete files.
4. Run focused Jest.

## Task 4: Privacy Policy Wording

**Files:**

- Modify: `mobile/app/privacy-policy.tsx`

**Steps:**

1. Update summary sections for App Store submission:
   - HealthKit data use.
   - AI context minimization.
   - Account deletion request.
   - Non-diagnostic medical boundary.
2. Keep wording concise and non-legalistic.
3. Run TypeScript and settings tests.

## Task 5: Verification

**Commands:**

- `DATABASE_URL=sqlite:///:memory: TZ=Asia/Shanghai /Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python -m pytest backend/tests/test_account_deletion_request.py -q --no-cov`
- `cd mobile && /Users/liqiuhua/work/personal/health-llm-driven/mobile/node_modules/.bin/jest --runTestsByPath app/__tests__/settings.test.tsx --runInBand`
- `cd mobile && /Users/liqiuhua/work/personal/health-llm-driven/mobile/node_modules/.bin/tsc --noEmit`
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python backend/scripts/check_dossier_consistency.py`
- `/Users/liqiuhua/work/personal/health-llm-driven/backend/venv/bin/python scripts/check_doc_drift.py`

## Release Notes

This batch does not submit to App Store yet. It prepares the first compliance/UI slice. The next batch should cover screenshots, metadata, native build, App Store Connect submit, and true-device verification.
