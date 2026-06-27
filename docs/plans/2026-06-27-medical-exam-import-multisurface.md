# Medical Exam Import Multisurface Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a unified medical exam import experience on Web, Mac, and Mobile.

**Architecture:** Keep backend `/medical-exams/import/*` as the canonical write path. Add thin client-side normalization and UI entry points so each surface can import reports, show a consistent result summary, and route users to record review or Reva follow-up.

**Tech Stack:** FastAPI existing API, Next.js/Vitest for Web, Expo React Native/Jest for Mobile, SwiftUI/XCTest for Mac.

---

### Task 1: Mobile Import Result Contract

**Files:**
- Modify: `mobile/services/medicalExams.ts`
- Modify: `mobile/services/__tests__/medicalExams.test.ts`

**Steps:**
1. Add failing tests for `normalizeMedicalExamImportResult`, PDF upload, and image upload.
2. Run `cd mobile && npm test -- services/__tests__/medicalExams.test.ts --runInBand`.
3. Implement normalized import result fields while keeping snake-case compatibility.
4. Re-run the same Jest test.

### Task 2: Mobile Focused Medical Import Flow

**Files:**
- Modify: `mobile/app/import.tsx`
- Modify: `mobile/app/medical-exams.tsx`
- Create: `mobile/app/__tests__/medical-exams.test.tsx`

**Steps:**
1. Add a failing screen test that pressing “导入体检报告” routes to `/import?focus=medical`.
2. Add focused import mode in `/import`: title/lead/tips become medical-specific; PDF skips gene-vs-medical disambiguation.
3. Add success action to open `/medical-exams`.
4. Run targeted mobile Jest tests.

### Task 3: Web Canonical Import Client And UI

**Files:**
- Create: `frontend/src/services/api/medicalExams.ts`
- Create: `frontend/src/services/api/medicalExams.test.ts`
- Modify: `frontend/src/app/medical-exams/page.tsx`
- Modify: `frontend/src/app/medical-exams/components/PdfUploadSection.tsx`

**Steps:**
1. Add failing Vitest coverage for PDF/image/text import normalization.
2. Implement Web API client using `api` interceptor auth, without `user_id` query parameters.
3. Update the medical exams page import panel to accept PDF/images and text fallback.
4. Run targeted frontend Vitest.

### Task 4: Mac Import Presentation

**Files:**
- Create: `apps/mac/Sources/HealthAgentMacCore/LabUploadPresentation.swift`
- Create: `apps/mac/Tests/HealthAgentMacCoreTests/LabUploadPresentationTests.swift`
- Modify: `apps/mac/Sources/HealthAgentMac/FeatureViews.swift`

**Steps:**
1. Add failing XCTest for medical exam import summary and review warning.
2. Implement reusable presentation helper.
3. Update RecordHub lab upload card copy and Agent prompt to use medical exam wording.
4. Run `swift test --package-path apps/mac --filter LabUpload`.

### Task 5: Web Chat Runtime Skill

**Files:**
- Create: `frontend/src/services/chatMedicalExamImportSkill.ts`
- Create: `frontend/src/services/chatMedicalExamImportSkill.test.ts`
- Modify: `frontend/src/app/ai-assistant/page.tsx`
- Modify: `frontend/src/app/ai-assistant/__tests__/page-url.test.tsx`
- Modify: `frontend/src/components/assistant/inlineCards/cards.tsx`
- Modify: `frontend/src/components/assistant/inlineCards/registry.tsx`

**Steps:**
1. Add failing Vitest coverage for skill execution, card rendering, and composer upload behavior.
2. Implement Web runtime skill on top of `importMedicalExamFile`.
3. Add `medical_exam_import_result` to the Web inline card registry.
4. Add a composer file button that imports PDF/images, appends the result card, and pre-fills a follow-up interpretation prompt.
5. Run targeted frontend Vitest for the service, card registry, and `/ai-assistant` page.

### Task 6: Final Verification

**Commands:**
- `cd mobile && npm test -- services/__tests__/medicalExams.test.ts app/__tests__/medical-exams.test.tsx --runInBand`
- `cd frontend && npm test -- src/services/api/medicalExams.test.ts`
- `cd frontend && npm test -- src/services/chatMedicalExamImportSkill.test.ts src/components/assistant/inlineCards/__tests__/registry.test.tsx src/app/ai-assistant/__tests__/page-url.test.tsx`
- `swift test --package-path apps/mac --filter LabUpload`
- `git status --short`

**Commit:**
```bash
git add docs/plans/2026-06-27-medical-exam-import-multisurface-design.md \
  docs/plans/2026-06-27-medical-exam-import-multisurface.md \
  mobile/services/medicalExams.ts mobile/services/__tests__/medicalExams.test.ts \
  mobile/app/import.tsx mobile/app/medical-exams.tsx mobile/app/__tests__/medical-exams.test.tsx \
  frontend/src/services/api/medicalExams.ts frontend/src/services/api/medicalExams.test.ts \
  frontend/src/app/medical-exams/page.tsx frontend/src/app/medical-exams/components/PdfUploadSection.tsx \
  apps/mac/Sources/HealthAgentMacCore/LabUploadPresentation.swift \
  apps/mac/Tests/HealthAgentMacCoreTests/LabUploadPresentationTests.swift \
  apps/mac/Sources/HealthAgentMac/FeatureViews.swift
git commit -m "feat(medical-exams): add multisurface import experience"
```
