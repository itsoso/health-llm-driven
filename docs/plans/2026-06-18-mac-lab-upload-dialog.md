# Mac Lab Upload In Dialog Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Mac upload support for lab report images/PDFs from both the Record surface and the Agent dialog.

**Architecture:** Reuse existing backend endpoints `medical-exams/import/image` and `medical-exams/import/pdf`. Add a small Mac Core upload client, then have `AgentChatViewModel` import medical-file attachments before streaming and include the import result in `extra_context`.

**Tech Stack:** Swift 6, SwiftUI, XCTest, FastAPI existing endpoints.

---

### Task 1: Lab Upload Client

**Files:**
- Create: `apps/mac/Sources/HealthAgentMacCore/LabUploadClient.swift`
- Test: `apps/mac/Tests/HealthAgentMacCoreTests/LabUploadClientTests.swift`

**Steps:**
1. Write failing tests for PDF and image endpoint routing.
2. Run `swift test --package-path apps/mac --filter LabUploadClientTests`.
3. Implement `LabUploadClient`, MIME mapping, and response decoding.
4. Re-run the same test.

### Task 2: Agent Attachment Import

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift`
- Modify: `apps/mac/Tests/HealthAgentMacCoreTests/AgentStreamClientTests.swift`

**Steps:**
1. Write a failing test that attaches a medical image, sends a prompt, and expects `lab_report_imports` in `extra_context`.
2. Run the focused test and confirm failure.
3. Inject optional `LabUploadServicing` into `AgentChatViewModel`.
4. Import medical attachments before stream start and include import context.
5. Re-run the focused test.

### Task 3: Mac UI Entry Points

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMac/App/AppServices.swift`
- Modify: `apps/mac/Sources/HealthAgentMac/App/AppRootView.swift`
- Modify: `apps/mac/Sources/HealthAgentMac/FeatureViews.swift`
- Modify: `apps/mac/Sources/HealthAgentMacCore/AppLocalization.swift`

**Steps:**
1. Add `LabUploadClient` to app services and pass it to Agent/Record views.
2. Add a compact lab upload card on the Record surface.
3. Keep existing Agent paste/attach/drop paths, but route medical attachments through the upload client on send.
4. Add minimal localized strings.
5. Run `swift test --package-path apps/mac`.

### Task 4: Final Verification

**Steps:**
1. Run `git diff --check`.
2. Run focused Mac tests.
3. Inspect `git status --short` and stage only files from this task.
