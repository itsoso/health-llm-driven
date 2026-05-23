# Swift Native Mac Health Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Swift-native macOS client that has the core daily operating capabilities of the mobile app, while keeping the backend orchestrator, Twin, knowledge base, and database as the single source of truth.

**Architecture:** The Mac app is a first-class client, not a second brain. It reuses backend APIs for health judgment, records, agent chat, evidence, jobs, and action feedback; local code is limited to native desktop UX, file access, upload orchestration, local cache, Keychain, notifications, and menu bar status.

**Tech Stack:** Swift 6, SwiftUI, AppKit interop where needed, URLSession async/await, URLSession background transfers, Keychain via Security framework, Core Data or SQLite cache, QuickLook, Charts, UserNotifications, AVFoundation/Speech for local TTS.

---

## 1. Product Position

### 1.1 Device Roles

| Surface | Role | Primary Strength |
|---|---|---|
| Backend | Brain and source of truth | Orchestrator, specialists, Twin, KB, evidence, records, audit, jobs |
| Mobile | Pocket execution client | Capture in the moment, voice, camera, push, Apple Health device bridge |
| Mac App | Desktop execution client and workbench | Large files, long tasks, evidence inspection, batch import, richer tables and traces |

The Mac app must support daily use directly. It is not only an admin console. The user should be able to ask the Agent, record food/supplements/water/weight/BP, review today's plan, give feedback, inspect labs/genes/trends, and run long imports without touching the phone.

### 1.2 Non-Goals

- Do not run a separate local health reasoning engine in the Mac app.
- Do not fork health record schemas in Swift.
- Do not copy mobile screens one-to-one; desktop layout should use sidebar, split views, tables, drag-and-drop, and multi-window where useful.
- Do not upload raw local files by default when structured extraction is enough.
- Do not add third-party Swift dependencies in P0 unless a native framework cannot cover the job.

---

## 2. P0 Capability Map

### 2.1 Mac App Sections

Use `NavigationSplitView` with these top-level destinations:

| Section | P0 Scope | Backend Source |
|---|---|---|
| Today | Daily plan, action cards, recent memory, feedback buttons, today's diet/supplement/water/activity summary | `/daily-plan/me`, `/trajectory/me`, `/action-cards`, `/memory-facts`, record APIs |
| Agent | Chat, model picker, image/file upload, source chips, evidence side panel, message history | `/agent/stream`, `/agent/conversations`, `/admin/llm/models` or existing LLM preference APIs |
| Record | Natural language record, structured record forms, recent editable records | `health_record` tool path plus direct diet/supplement/water/weight/BP APIs |
| Data | Labs, body metrics, sleep, workouts, HRV, SpO2, trends | existing mobile service endpoints |
| Genetics | Genetic report, SNP detail, reanalysis status, boundaries | `/genetic-data`, report APIs, job APIs |
| Knowledge | System KB coverage, Dedao import status, protocol artifacts | `/system-knowledge`, job APIs |
| Jobs | Long-running import/reanalysis/eval tasks with progress and retry | new desktop job API |
| Settings | Auth, API base URL, voice, privacy, local cache, file permissions | auth/profile/settings APIs |

### 2.2 Menu Bar Extra

Use `MenuBarExtra` as a lightweight always-available surface:

- Today's top 3 actions.
- Current long-running job status.
- Quick commands: "Ask Agent", "Record Food", "Import File", "Open Full App".
- Sync/error badge.

The menu bar must not contain full chat in P0. It should route into the main app.

---

## 3. API Contract Strategy

### 3.1 Reuse First

Before adding Mac-specific APIs, map existing mobile services:

| Mobile Service | Mac Equivalent |
|---|---|
| `mobile/services/chat.ts` | `AgentStreamClient.swift` |
| `mobile/services/llmPreference.ts` | `ModelPreferenceClient.swift` |
| `mobile/services/dailyPlan.ts` | `DailyPlanClient.swift` |
| `mobile/services/trajectory.ts` | `TrajectoryClient.swift` |
| `mobile/services/actionCards.ts` | `ActionCardClient.swift` |
| `mobile/services/diet.ts` | `DietClient.swift` |
| `mobile/services/medicalExams.ts` | `MedicalExamClient.swift` |
| `mobile/services/geneticData.ts` / `geneticReport.ts` | `GeneticClient.swift` |
| `mobile/services/memory.ts` | `MemoryClient.swift` |
| `mobile/services/cloudTts.ts` | `SpeechClient.swift` |

### 3.2 P0 Backend Gaps

Add only the APIs needed to make Mac feel complete:

1. `GET /api/v1/desktop/bootstrap`
   - Returns today's plan, trajectory summary, active action cards, recent memory, recent records summary, model preference, active jobs.
   - Purpose: one fast launch request for desktop home/menu bar.

2. `POST /api/v1/desktop/import-jobs`
   - Creates a job for gene txt, medical PDF/image, Apple Health export, or Dedao directory manifest.
   - Must require current user auth and record file hash/source metadata.

3. `GET /api/v1/desktop/jobs`
   - Lists active/recent user jobs.

4. `GET /api/v1/desktop/jobs/{job_id}`
   - Returns progress, status, result refs, errors, and retry eligibility.

5. `POST /api/v1/desktop/jobs/{job_id}/retry`
   - Retries failed idempotent jobs.

6. `GET /api/v1/desktop/traces/{conversation_id_or_run_id}`
   - Aggregates message, provider, finish reason, tool calls, evidence refs, memory injection, specialist findings, and audit refs.

If an existing route already covers one item, the desktop route should be a thin aggregator or omitted.

---

## 4. Native macOS Design Principles

### 4.1 Desktop Interaction

- Use `NavigationSplitView`, not tab bar.
- Use tables for labs, records, SNPs, jobs, and source lists.
- Use detail sidebars for evidence and trace rather than expanding long inline sections.
- Support drag-and-drop into Agent and Import Center.
- Support keyboard shortcuts:
  - `Cmd+N`: new Agent thread.
  - `Cmd+Shift+I`: import file.
  - `Cmd+R`: refresh current view.
  - `Cmd+K`: command palette or quick action search in later phase.
- Support multi-window only after P0 is stable; first release stays single-window plus menu bar.

### 4.2 Performance

- App launch should render cached shell within 500 ms on Apple Silicon.
- Desktop bootstrap network request should not block rendering.
- Large file hash/preview/metadata extraction must run off the main actor.
- Chat streaming must append tokens incrementally without re-rendering the full message list on every token.
- Jobs list should poll with backoff and stop polling completed jobs.
- Tables should page or virtualize server-side where possible.

### 4.3 Privacy

- Store auth token in Keychain.
- Store authorized local folders as security-scoped bookmarks.
- Keep local cache scoped to current authenticated account.
- Default import flow uploads file hash and extracted structured metadata first; raw upload requires explicit action.
- Never log token, health data payloads, raw genome rows, or full PDF text to console.

---

## 5. Implementation Tasks

### Task 1: Add Mac Product Plan and API Inventory

**Files:**
- Create: `docs/plans/2026-05-23-swift-native-mac-health-agent.md`
- Later modify: `docs/ARCHITECTURE.md` with final link after P0 lands.

**Step 1: Verify current mobile and backend capability inventory**

Run:

```bash
find backend/app/api -maxdepth 1 -type f | sort
find mobile/services mobile/app mobile/components/chat -maxdepth 2 -type f | sort
```

Expected: existing mobile services cover chat, daily plan, trajectory, records, genetics, labs, memory, and TTS.

**Step 2: Save this plan**

Commit this document before implementation starts.

---

### Task 2: Create Backend Desktop Bootstrap API

**Files:**
- Create: `backend/app/api/desktop.py`
- Modify: `backend/app/api/main.py` or router registration file.
- Test: `backend/tests/test_desktop_api.py`

**Step 1: Write failing tests**

Test cases:

- Auth required.
- Response is scoped to current user.
- Response contains `daily_plan`, `trajectory`, `action_cards`, `recent_memory`, `recent_records_summary`, `model_preference`, `active_jobs`.
- Missing optional modules return empty arrays or nulls, not 500.

**Step 2: Implement minimal endpoint**

Use existing services where possible:

- `build_daily_operating_plan`
- `build_health_trajectory_snapshot`
- action card query scoped by `user_id`
- memory facts query scoped by `user_id`
- model preference from `UserProfile.llm_model_id`
- desktop jobs table once Task 3 exists; before that return `[]`

**Step 3: Verify**

Run:

```bash
cd backend
source venv/bin/activate
pytest tests/test_desktop_api.py -q --no-cov
```

Expected: PASS.

---

### Task 3: Add Desktop Job Model and API

**Files:**
- Create: `backend/app/models/desktop_job.py`
- Create: `backend/app/api/desktop_jobs.py` or include inside `desktop.py` if small.
- Create: `backend/migrations/20260523_120000_create_desktop_jobs.sql`
- Test: `backend/tests/test_desktop_jobs.py`

**Schema:**

```sql
CREATE TABLE IF NOT EXISTS desktop_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'queued',
    progress INTEGER NOT NULL DEFAULT 0,
    source_kind VARCHAR(50),
    source_name VARCHAR(500),
    source_hash VARCHAR(128),
    request_payload JSONB,
    result_payload JSONB,
    error_message TEXT,
    retry_of_job_id INTEGER REFERENCES desktop_jobs(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);
CREATE INDEX IF NOT EXISTS idx_desktop_jobs_user_created ON desktop_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_desktop_jobs_user_status ON desktop_jobs(user_id, status);
```

**Step 1: Write failing tests**

Test cases:

- Create gene reanalysis job.
- Create system KB rebuild job.
- List only current user's jobs.
- Retry only failed idempotent jobs.
- Reject cross-user job access.

**Step 2: Implement model and routes**

Allowed P0 job types:

- `gene_reanalysis`
- `medical_import`
- `system_kb_rebuild`
- `dedao_compile`
- `eval_run`

**Step 3: Wire Celery later**

In P0 API, job creation may enqueue existing Celery tasks when available. If a task is not wired yet, create `queued` job and return `501-like` domain status in `error_message` only for unsupported job types. Do not crash.

---

### Task 4: Scaffold Swift Native Mac App

**Files:**
- Create: `apps/mac/README.md`
- Create: `apps/mac/HealthAgentMac/HealthAgentMacApp.swift`
- Create: `apps/mac/HealthAgentMac/AppRootView.swift`
- Create: `apps/mac/HealthAgentMac/SidebarDestination.swift`
- Create: `apps/mac/HealthAgentMac/Networking/APIClient.swift`
- Create: `apps/mac/HealthAgentMac/Security/KeychainStore.swift`
- Create: `apps/mac/HealthAgentMac/Models/*.swift`
- Create: `apps/mac/HealthAgentMacTests/APIClientTests.swift`

**Step 1: Choose project format**

Prefer Xcode macOS App project when created locally in Xcode. If generating from CLI, start with a Swift Package skeleton and document the Xcode target creation steps in `apps/mac/README.md`.

**Step 2: Minimal app shell**

Use:

```swift
@main
struct HealthAgentMacApp: App {
    var body: some Scene {
        WindowGroup {
            AppRootView()
        }
        MenuBarExtra("Health Agent", systemImage: "heart.text.square") {
            MenuBarRootView()
        }
    }
}
```

**Step 3: Verify**

Run one of:

```bash
cd apps/mac
swift test
```

or in Xcode:

```bash
xcodebuild test -scheme HealthAgentMac -destination 'platform=macOS'
```

Expected: app builds and tests pass.

---

### Task 5: Implement Auth and API Client

**Files:**
- Create/modify: `apps/mac/HealthAgentMac/Networking/APIClient.swift`
- Create/modify: `apps/mac/HealthAgentMac/Networking/AuthClient.swift`
- Create/modify: `apps/mac/HealthAgentMac/Security/KeychainStore.swift`
- Test: `apps/mac/HealthAgentMacTests/APIClientTests.swift`

**Behavior:**

- Base URL configurable, default `https://health.executor.life/api/v1`.
- Token stored in Keychain.
- Every authenticated request sets `Authorization: Bearer`.
- 401 clears in-memory session and routes user to login.
- JSON decoding errors produce visible structured error, not silent empty UI.

**Test:**

Use `URLProtocol` stub to verify headers, decoding, and error handling.

---

### Task 6: Build Desktop Home and Menu Bar

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Today/TodayView.swift`
- Create: `apps/mac/HealthAgentMac/Features/MenuBar/MenuBarRootView.swift`
- Create: `apps/mac/HealthAgentMac/Services/DesktopBootstrapService.swift`
- Test: Swift view model tests.

**Behavior:**

- App shows cached shell instantly.
- Fetches `/desktop/bootstrap` after auth.
- Shows daily plan, action cards, memory, and active jobs.
- Menu bar shows top actions and job status.
- Feedback buttons call the same action feedback endpoint as mobile.

---

### Task 7: Build Agent Chat with Model Picker and File Drop

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Agent/AgentChatView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Agent/AgentStreamClient.swift`
- Create: `apps/mac/HealthAgentMac/Features/Agent/ModelPickerView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Agent/EvidenceSidebar.swift`
- Test: stream parser tests.

**Behavior:**

- Stream `/agent/stream` and render tokens incrementally.
- Preserve `conversation_id` from `agent_start`.
- Model picker remains usable while a prior request is stuck or failed.
- Dragging image/PDF/txt attaches it to next message or starts import depending on file type.
- Evidence/source chips open the side panel.

**Regression tests copied from mobile behavior:**

- Empty final content shows retryable error state.
- `done` event with `completion_status=interrupted` shows continue action.
- Model switching is not disabled by streaming state.

---

### Task 8: Build Record Workflows

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Record/RecordHubView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Record/QuickRecordView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Record/StructuredRecordForms.swift`
- Test: record client tests.

**P0 record types:**

- Diet
- Supplement
- Water
- Weight
- Blood pressure
- Symptom/illness

**Behavior:**

- Natural-language record can send through Agent/tool flow.
- Structured form can call direct APIs where mobile already does.
- High-certainty records follow backend confirmation rules; Mac UI should render confirmation clearly.

---

### Task 9: Build Import Center

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Import/ImportCenterView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Import/FileIntakeService.swift`
- Create: `apps/mac/HealthAgentMac/Features/Import/FileHashService.swift`
- Test: file classification/hash tests.

**Behavior:**

- Drag/select file or folder.
- Classify:
  - genome txt
  - medical PDF/image
  - Apple Health export zip/xml
  - Dedao folder manifest
  - unknown
- Compute SHA-256 off main actor.
- Show what will be uploaded.
- Default to metadata/structured upload. Raw upload requires explicit confirmation.
- Create desktop import job and open job detail.

---

### Task 10: Build Job Center

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Jobs/JobListView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Jobs/JobDetailView.swift`
- Create: `apps/mac/HealthAgentMac/Services/DesktopJobClient.swift`
- Test: job client and view model tests.

**Behavior:**

- List active/recent jobs.
- Show progress, status, created time, source, result refs, and errors.
- Retry failed idempotent jobs.
- Open result in Genetics, Knowledge, Data, or Trace section when available.

---

### Task 11: Build Trace Viewer

**Files:**
- Create: `apps/mac/HealthAgentMac/Features/Trace/TraceView.swift`
- Create: `apps/mac/HealthAgentMac/Features/Trace/TraceClient.swift`
- Test: trace decoding tests.

**Behavior:**

- Show provider/model, duration, finish reason, completion status.
- Show tool calls and tool results.
- Show specialist findings and arbitration.
- Show memory injection stages.
- Show evidence refs and unsupported claims.
- Show failure reason for empty replies, timeouts, and provider errors when logged.

---

### Task 12: Distribution and Verification

**Files:**
- Create: `apps/mac/README.md`
- Create: `docs/plans/2026-05-23-swift-native-mac-health-agent-release-checklist.md` later if needed.

**P0 local verification:**

```bash
cd backend
source venv/bin/activate
pytest tests/test_desktop_api.py tests/test_desktop_jobs.py -q --no-cov

cd apps/mac
swift test
```

**Release path:**

- Internal first: local signed build.
- Then Developer ID distribution or TestFlight for Mac if Apple account setup is ready.
- App Store review is not P0 because health claims and file import behavior need policy review first.

---

## 6. Open Questions Before Implementation

These should be resolved during Task 4, not before writing backend tests:

1. Should the first Swift project be created manually in Xcode or generated from a CLI template?
2. Should local cache use Core Data from day one, or start with file-backed JSON plus Keychain and move to Core Data when data views need offline mode?
3. Should desktop import jobs upload raw files to the existing upload endpoint or create a new presigned/object-storage path?
4. Which user role can see full traces: current user only for own conversation, or admin-only for low-level provider diagnostics?

Default decisions for P0:

- Xcode project is acceptable if created manually, but all source files live under `apps/mac/`.
- Use native frameworks only.
- Use current user auth for all user data; admin diagnostics can come later.
- Prefer structured metadata upload before raw file upload.

