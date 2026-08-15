# Surface Ownership Inventory

> Status: active · reconciled with Chat-first shell
> Owner: Reva / Personal Health OS
> Updated: 2026-08-15
> Related PRD/PDD: docs/specs/reva-product-governance-spec.md · docs/prd/reva-personal-health-os-prd.md · docs/prd/2026-06-15-global-product-requirements.md · docs/plans/2026-06-26-reva-global-product-architecture-plan.md · docs/specs/active/2026-08-15-quiet-proactive-health-day.md
> Related code: mobile/app · apps/watch · apps/mac · apps/rokid-pushup-glasses · frontend/src/app · mcp-server · backend/app/api

## 1. Decision

Use this inventory as the surface ownership source of truth. Mobile's primary shell is Chat-first XiaoBa; Today, Agenda, Capture, Programs and Review are contextual product destinations inside that shell, not competing top-level tabs. New product work must name the owning surface and should not create duplicate daily-loop workflows outside that surface without an explicit cross-surface contract.

Disposition vocabulary:

| Disposition | Meaning |
|---|---|
| Keep | Keep as a first-class surface or route. |
| Converge | Merge behavior into the owning surface or reuse the shared backend contract. |
| Archive | Hide, de-prioritize, or move to secondary/history/admin use. |

## 2. Surface Contract

| Surface | Role | Owns | Must Not Own | Disposition |
|---|---|---|---|---|
| Mobile | Primary daily product | Chat-first XiaoBa shell, Health Day summary, Today/Agenda detail, Capture, Programs, Review, settings/consent | Admin console, trace-heavy debugging, long file triage, a second daily shell | Keep |
| Apple Watch | Low-friction execution | top action, due item, confirm/later/skip, quick voice/food/water/symptom, freshness | long reports, complex editing, model selection | Keep |
| Rokid | Hands-free execution | food photo/voice, push-up coaching, workout guidance, voice agenda when command-ready | dashboard, multi-page admin, noisy proactive broadcast | Keep |
| Mac | Workbench | file/lab import, long agent workflows, trace review, calendar/planning review, local QR/release ops | replace mobile daily loop, duplicate health judgment | Keep |
| Web | Admin/history/doctor/family | reports, history, doctor/family/admin, compatibility and generated API inspection | lead consumer daily execution | Converge / Archive daily pages |
| MCP | Controlled extension | documented health query/record/analyze tools with auth and audit | bypass safety, direct unmanaged writes, private data fanout | Keep with guardrails |
| Backend | Product source of truth | Health Twin, Safety Gate, Agenda, Router, Program, Audit, Write autonomy | client-owned health decisions | Keep |

## 3. Mobile Inventory

Mobile has one primary shell and five contextual capability destinations. Existing routes can remain temporarily, but they must map to one owner and return safely to the XiaoBa shell.

| Target Entry | Owns | Current Representative Files | Disposition |
|---|---|---|---|
| XiaoBa shell | cold start, conversation, Health Day summary, contextual dynamic actions and navigation | `mobile/app/(tabs)/index.tsx`(redirect), `mobile/app/(tabs)/chat.tsx` | Keep · sole primary entry |
| Today | readiness, top action, urgent safety, next due item and current-day detail | `mobile/app/(tabs)/today.tsx`, `mobile/app/reva.tsx`, `mobile/app/day-schedule.tsx`, `mobile/app/timeline.tsx` | Keep detail / Converge duplicate planners |
| Agenda | day/week/month/quarter health schedule | `mobile/app/agenda.tsx`, `mobile/app/calendar.tsx`, `mobile/app/calendar-sources.tsx`, `mobile/app/calendar-connect.tsx` | Keep |
| Capture | food, water, symptoms, meds, supplements, measurements, voice/photo/manual | `mobile/app/(tabs)/record.tsx`, `mobile/app/diet.tsx`, `mobile/app/symptom-record.tsx`, `mobile/app/medications.tsx`, `mobile/app/body-measurements.tsx`, `mobile/app/import.tsx`, `mobile/app/voice-chat.tsx` | Keep / Converge |
| Programs | metabolic, recovery/training, sleep/breathing, medication/supplement, checkup | `mobile/app/intervention-cycle.tsx`, `mobile/app/metabolic-profile.tsx`, `mobile/app/movement-plan.tsx`, `mobile/app/fitness-plan.tsx`, `mobile/app/sleep.tsx`, `mobile/app/sleep-spo2-analysis.tsx`, `mobile/app/doctor-loop.tsx` | Keep / Converge |
| Review | execution, metrics, N-of-1, retest, causal ledger | `mobile/app/my-progress.tsx`, `mobile/app/weekly-briefing.tsx`, `mobile/app/monthly-reports.tsx`, `mobile/app/indicator-history.tsx`, `mobile/app/liver-trend.tsx`, `mobile/app/device-sources.tsx`, `mobile/app/data-integrity.tsx` | Keep |

Secondary mobile pages:

| Group | Representative Files | Target |
|---|---|---|
| Settings and consent | `mobile/app/settings.tsx`, `mobile/app/notification-settings.tsx`, `mobile/app/llm-preference.tsx`, `mobile/app/location.tsx`, `mobile/app/privacy-policy.tsx` | Keep under Me/Settings |
| Admin/debug | `mobile/app/admin-llm.tsx`, `mobile/app/app-diagnostics.tsx`, `mobile/app/rokid-diagnostics.tsx`, `mobile/app/trace/*` | Archive from daily nav; keep deep links |
| Share/public | `mobile/app/shared/[shareToken].tsx` | Keep as external share surface |
| Rokid support | `mobile/app/rokid-health.tsx`, `mobile/app/rokid-pushup-coach.tsx` | Converge under device setup/execution |

## 4. Mac Inventory

Mac is a workbench, not the daily-loop replacement.

| Area | Representative Files | Disposition |
|---|---|---|
| Today dashboard | `apps/mac/Sources/HealthAgentMac/App/AppRootView.swift`, `apps/mac/Sources/HealthAgentMacCore/DesktopDashboardPresentation.swift` | Keep, but consume backend Agenda contract |
| Agent long workflow | `AgentChatViewModel.swift`, `AgentStreamClient.swift`, `AgentConversationClient.swift`, `ChatTranscriptHTML.swift` | Keep |
| Import and local file handling | `FileIntakeService.swift`, `LabUploadClient.swift`, `DesktopJobClient.swift`, `DesktopWorkspaceContextFactory.swift` | Keep |
| Trace and diagnostics | `TraceClient.swift`, `DesktopTaskCenterPresentation.swift`, `DeviceSourcesClient.swift` | Keep |
| Quick capture | `RecordClient.swift`, `RecordHubPresentation.swift`, `StructuredRecordDraft.swift` | Keep only as desktop convenience; records stay backend-owned |
| Lifecycle | `MacAppLifecyclePolicy.swift`, `MacSingleInstanceLaunchGuard.swift` | Keep |

## 5. Web Inventory

Web is secondary for consumer daily use. It should become admin/history/doctor/family and compatibility.

| Group | Representative Files | Disposition |
|---|---|---|
| Admin/ops | `frontend/src/app/admin/page.tsx`, `frontend/src/app/llm-preference/page.tsx`, `frontend/src/app/skills/page.tsx` | Keep |
| History/report/review | `frontend/src/app/review/page.tsx`, `frontend/src/app/health-report/page.tsx`, `frontend/src/app/weekly-briefing/page.tsx`, `frontend/src/app/my-progress/page.tsx` | Keep |
| Doctor/family | `frontend/src/app/family/page.tsx`, `frontend/src/app/health-consultations/page.tsx` | Keep |
| Legacy daily pages | `frontend/src/app/dashboard/page.tsx`, `frontend/src/app/agenda/page.tsx`, `frontend/src/app/diet/page.tsx`, `frontend/src/app/workout/page.tsx`, `frontend/src/app/water/page.tsx` | Converge to backend contracts; Archive from primary positioning |
| Generated API/types | `frontend/src/types/api.generated.ts` | Keep as compatibility artifact |

## 6. Watch Inventory

| Area | Representative Files | Disposition |
|---|---|---|
| Top action / today | `apps/watch/WatchApp/TodayStatusView.swift`, `apps/watch/Sources/WatchCompanionCore/WatchSummary.swift` | Keep |
| Push list and due items | `apps/watch/WatchApp/PushListView.swift`, `WatchEventClient.swift` | Keep |
| Quick capture | `QuickRecordView.swift`, `WatchDictation.swift`, `QuickRecord.swift`, `VoiceFoodDraft.swift` | Keep |
| Connectivity/auth | `WatchConnectivityClient.swift`, `WatchCredentialStore.swift`, `WatchDirectAPIClient.swift` | Keep |
| Complication | `apps/watch/WatchComplication/RevaComplication.swift`, `ComplicationState.swift` | Keep |

Watch must consume backend Agenda, WatchSummary, and notification decisions. It should not create independent health recommendations.

## 7. Rokid Inventory

| Area | Representative Files | Disposition |
|---|---|---|
| Glasses push-up app | `apps/rokid-pushup-glasses/README.md`, `apps/rokid-pushup-glasses/app/build.gradle.kts` | Keep |
| Mobile bridge | `mobile/app/rokid-health.tsx`, `mobile/app/rokid-pushup-coach.tsx`, `mobile/modules/rokid-bridge/*`, `mobile/services/rokidVoiceControl.ts` | Keep / Converge under device execution |
| Vendor docs | `docs/vendor/rokid-cxr-l-sdk/*` | Keep as reference only |

Rokid is execution-only until auth, BLE, CustomView readiness, voice command readiness, and capture/session persistence are all green.

## 8. MCP Inventory

| Area | Representative Files | Disposition |
|---|---|---|
| MCP server | `mcp-server/` | Keep as controlled extension |

External agents must use documented APIs/tools, auth, audit, and source ownership. They must not bypass SafetyGuardian or write-autonomy gates.

## 9. Backend Inventory

Backend remains the product source of truth.

| Object | Representative Files | Surface Contract |
|---|---|---|
| Health Agenda | `backend/app/services/agenda_service.py`, `agenda_contract.py`, `timeline_agenda_service.py` | All surfaces consume the same item/status/source contract |
| Safety Gate | `backend/app/agents/safety_guardian/*` | Clients display results, never override rules |
| Wearable Router | `backend/app/services/device_source_priority.py`, `device_comparison_service.py`, `wearable_router.py` | Clients show source/freshness/confidence, not local arbitration |
| Notification Decision | `backend/app/services/interruption_budget.py`, `proactive_coordinator.py`, `notification/push_service.py` | Watch/mobile respect P0/P1/P2 and quiet-hours policy |
| Write Autonomy | `backend/app/services/write_intent_service.py`, `backend/app/api/write_intents.py` | Clients confirm/skip; backend owns execution state |
| Desktop jobs | `backend/app/api/desktop.py`, `backend/app/models/desktop_job.py` | Mac creates/retries/inspects jobs; backend owns persistence |

## 10. Cleanup Queue

| Priority | Action | Reason |
|---|---|---|
| P0 | Hide mobile admin/debug pages from primary daily navigation | Reduces product sprawl without deleting tooling |
| P0 | Ensure Mac Today consumes backend Agenda contract only | Prevents parallel daily-loop logic |
| P0 | Move Web daily pages to history/compatibility positioning | Web should not compete with mobile daily execution |
| P1 | Add route metadata for mobile pages: target entry + disposition | Makes future cleanup machine-checkable |
| P1 | Add surface field to proactive notifications and Agenda execution events | Lets Watch/Mobile/Mac/Rokid show consistent provenance |
| P1 | Create stale-page archive list after traffic/user validation | Avoid removing unknown live workflows abruptly |

## 11. Governance Rule

Every non-trivial product feature must answer:

```yaml
surface_owner: Mobile | Apple Watch | Rokid | Mac | Web | MCP | Backend
target_entry: Today | Agenda | Capture | Programs | Review | Workbench | Admin | Execution | Extension
source_of_truth: backend object or client-local state
cross_surface_contract: Agenda | NotificationDecision | WriteIntent | DesktopJob | WatchSummary | other
disposition_for_existing_routes: Keep | Converge | Archive
```

If a feature creates a second daily-loop page or local health decision path, it fails Phase 0 governance unless the spec names the reason and rollback path.

## 12. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-06-26 | Initial inventory | Phase 0 surface ownership cleanup. |
| 2026-08-15 | Reconcile Mobile ownership with shipped Chat-first shell | `index` now redirects to `/chat` and the tab bar is hidden; clarify that Today/Agenda/Capture/Programs/Review are contextual destinations, preventing Health Day from creating a second home. |
