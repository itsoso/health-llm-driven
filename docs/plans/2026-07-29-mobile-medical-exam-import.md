# Mobile Medical Exam Import Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Mobile's nested immediate-write report import with a preview-first, explicitly confirmed, idempotent and recoverable flow.

**Architecture:** Add authenticated no-write preview support for report images and idempotent owner-scoped creation in the existing medical exam API. Build one reusable React Native full-screen flow and use it from both Chat and the focused import route.

**Tech Stack:** FastAPI, SQLAlchemy, React Native, Expo Router, Jest, React Native Testing Library.

---

### Task 1: Backend preview and idempotent save

**Files:**
- Modify: `backend/app/api/medical_exams.py`
- Modify: `backend/app/schemas/medical_exam.py`
- Test: `backend/tests/test_medical_exams.py`

1. Add failing tests proving image preview does not persist and repeated create
   with one `Idempotency-Key` returns one report.
2. Run the two tests and confirm they fail for missing behavior.
3. Add `/parse-image-preview`, owner-scoped fingerprinting and replay handling.
4. Run the focused medical exam API suite.

### Task 2: Mobile preview/save service

**Files:**
- Modify: `mobile/services/medicalExams.ts`
- Create: `mobile/services/__tests__/medicalExamImportFlow.test.ts`

1. Add failing tests for PDF/image preview normalization and idempotency header.
2. Implement preview asset normalization and confirmed create.
3. Run the service tests.

### Task 3: Reusable full-screen flow

**Files:**
- Create: `mobile/components/medical/MedicalExamImportFlow.tsx`
- Create: `mobile/components/medical/__tests__/MedicalExamImportFlow.test.tsx`

1. Add failing tests for source, preview, confirmation, inline retry and draft
   preservation.
2. Implement the smallest three-phase state machine.
3. Run component tests and refactor while green.

### Task 4: Replace duplicate Mobile entry points

**Files:**
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Modify: `mobile/app/import.tsx`
- Modify: `mobile/services/chatMedicalExamImportSkill.ts`

1. Add failing Chat test proving the attachment action opens the full-screen
   flow without an immediate upload.
2. Replace the nested import sheet and direct upload handlers.
3. Reuse the same component for `/import?focus=medical`.
4. Run Chat/import tests.

### Task 5: Contract and release verification

**Files:**
- Regenerate: `mobile/types/api.generated.ts`
- Update: `docs/dossiers/2026-07-29-mobile-medical-exam-import.md`

1. Regenerate API types and run backend/Mobile focused suites.
2. Run TypeScript, design token and repo hygiene checks.
3. Verify on iOS simulator: open Chat, choose report, preview, confirm, retry.
4. Commit, push, deploy backend, verify production, then publish Mobile OTA.
