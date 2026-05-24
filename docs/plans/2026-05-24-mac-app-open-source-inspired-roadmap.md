# Mac App Open-Source-Inspired Optimization Roadmap

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the Swift-native Mac app from a data viewer plus chat client into a reliable health operating workbench: fast launch, transparent context, clickable evidence, inspectable trends, low-friction capture, and reviewable Agent actions.

**Architecture:** Keep health reasoning, persistence, jobs, and evidence ownership in the backend. The Mac app owns native interaction: split-view workspace, global entry points, charts, local file intake, context assembly, Keychain/local cache, and permission-aware capture. Every Agent handoff should be represented as explicit context items and traceable events.

**Tech Stack:** Swift 6, SwiftUI, AppKit interop, URLSession async/await, Security Keychain, Swift Charts where justified, UserNotifications, Speech/AVFoundation, optional SPM dependencies only after license/security review.

---

## 1. Research Summary

### 1.1 GitHub/Open-Source References

| Project / Source | What It Shows | Relevant Lesson |
|---|---|---|
| CodeEdit (`CodeEditApp/CodeEdit`) | Large native macOS app using Swift/SwiftUI/AppKit, with IDE-like navigation and document/workbench concepts. | Mac UI should be a workbench with sidebar, detail, inspector, keyboard commands, not a stretched mobile screen. |
| Apple Food Truck sample (`apple/sample-food-truck`) | Multiplatform SwiftUI app using `NavigationSplitView`, custom layouts, and Swift Charts for trends. | Use native split navigation and first-party chart primitives before adding custom chart dependencies. |
| Apple Swift Charts docs | First-party chart framework with marks, scales, axes, legends, localization, and accessibility. | Trend/detail pages should move from handmade bars to accessible, inspectable charts where interaction matters. |
| OpenHands (`OpenHands/OpenHands`) | Agent system with explicit state, event stream, tool/action display, microagents, and context loading rules. | Agent UX must expose state, actions, observations, context, and failure reasons instead of hiding everything in chat bubbles. |
| OpenSail (`TesslateAI/OpenSail`) | Agent workspaces with reviewable trails, connectors, triggers, schedules, permissions, and context that travels. | Health Agent needs workspaces/runs with trigger, context, cost, outputs, approval history, and reusable instructions. |
| SuperCmd (`SuperCmdLabs/SuperCmd`) | macOS launcher combining global hotkeys, voice workflows, selected text capture, permissions, and AI actions. | Desktop health input should support global capture, hold-to-speak, selected-text/file intake, and permission preflight. |
| KeyboardShortcuts (`sindresorhus/KeyboardShortcuts`) | User-customizable global shortcuts, sandboxed and Mac App Store compatible. | If we add global hotkeys, use a proven pattern and make shortcuts user-configurable. |
| DesktopCtl | Local desktop control for agents with structured UI tokens and deterministic primitives. | If we ever let Agent operate the desktop, separate perception from execution and keep local privacy/approval indicators. |
| SwiftUICharts | Rich chart types across Apple platforms with accessibility support. | Keep as a reference, but do not add dependency until Swift Charts proves insufficient for specific health charts. |

### 1.2 First-Principles Product Model

A health Mac app has five jobs:

1. **See:** Make recent health state visible quickly: today, 7 days, 30 days, and high-priority exceptions.
2. **Understand:** Explain why a metric matters using trend, personal history, genetics, labs, supplements, and knowledge evidence.
3. **Act:** Convert findings into one or two concrete actions, not long generic advice.
4. **Capture:** Reduce input friction through text, voice, file/image drag-and-drop, selected text, and device sync.
5. **Trust:** Show what data the Agent saw, what tools it ran, what evidence it used, and where uncertainty remains.

Everything else is secondary.

---

## 2. Current Mac App State

The current app already has a credible P0:

- `Today`: dashboard, plan/actions, active jobs.
- `Agent`: streaming chat, model selection, web-search intent, attachments, evidence sidebar.
- `Record`: natural language and structured record entry.
- `Data`: metrics, 7/30 day summaries, trend detail sheet, Agent handoff for trend context.
- `Genetics`: summary, top findings, category cards, detail handoff.
- `Knowledge`: source and job summaries.
- `Jobs`: job list/detail/retry/trace handoff.
- `Trace`: provider/model/timing/tool/evidence diagnostics.
- `Settings`: auth, API base URL, voice preference, privacy notes.

The main gap is not missing screens. The gap is that screens are still too independent. The next generation should make the whole app feel like one health operating loop:

```text
capture -> structure -> trend -> explain -> act -> track completion -> learn
```

---

## 3. Design Principles

### 3.1 Workbench, Not Mobile Clone

Use a three-zone pattern where useful:

- **Sidebar:** stable section navigation and command entry.
- **Main canvas:** current work: today, data, gene, knowledge, record, or Agent.
- **Inspector:** selected context, evidence, trace, actions, or details.

This follows the same class of UI pattern seen in CodeEdit/OpenHands-style workspaces: selection on the left, work in the center, evidence/state on the right.

### 3.2 Every Card Is a Door

Any visible health card should answer:

- What is the value?
- What period does it represent?
- Can I inspect the raw records?
- Can I ask Agent with this exact context?
- Can I create or update an action from it?

If a card cannot be clicked, it should look static. If it can drive a decision, it should have hover, focus, disclosure, and keyboard activation.

### 3.3 Agent Context Must Be Visible

Before sending an Agent question, the app should show a context basket:

- selected health records
- selected trend chart
- selected genomic finding
- selected knowledge docs/claims
- current action cards
- recent wearable data
- attached files/images

Agent replies should show:

- used context
- tool calls
- evidence refs
- uncertainty boundaries
- generated actions
- whether a record/action/job was actually persisted

This borrows from OpenHands action/observation visibility and OpenSail reviewable trails.

### 3.4 Native Performance Over Decorative UI

Mac App success is mostly about latency and density:

- shell render under 500 ms
- cached dashboard appears before network returns
- chart interactions do not re-render the full page
- chat streaming appends incrementally
- large lists avoid eager rendering
- file hashing/imports never block the main actor

### 3.5 Health Safety Boundary

The Mac app may format, route, visualize, and assemble context. It must not become a second diagnostic engine. Risk interpretation remains backend-owned and evidence-scoped.

---

## 4. Target UX Architecture

### 4.1 Today: Daily Decision Board

Purpose: answer "what should I do today?"

Target layout:

1. **Status header**
   - health state sentence
   - date, data freshness, sync state
   - primary action button: ask Agent about today

2. **Three command cards**
   - Recovery: sleep, HRV, SpO2, readiness, training boundary.
   - Intake: calories, water, supplements, protein/fiber if available.
   - Risk/watchlist: gene/lab/action cards that matter today.

3. **Priority actions**
   - at most 3 primary actions
   - each has complete / snooze / ask why

4. **Recent memory and feedback**
   - compact, not noisy
   - feedback updates state immediately

Implementation targets:

- Modify: `apps/mac/Sources/HealthAgentMac/HealthAgentMacApp.swift`
- Modify presentation layer: `DesktopDashboardPresentation.swift`
- Add tests: `DesktopDashboardPresentationTests.swift`

### 4.2 Data: Interactive Trend Workbench

Current state: summary cards and trend detail sheet are present.

Next target:

- Replace mini custom bars with reusable `HealthTrendChartView`.
- Add metric detail drawer for all metric types:
  - diet, water, supplements: daily chart + records table
  - weight/BP: latest plus history when backend supports series
  - steps/sleep/HRV/SpO2: wearable trend when backend exposes daily points
- Support period switching: 1D / 7D / 30D / 90D.
- Add "Explain this trend" Agent entry from every chart.
- Add "Create action from trend" when the Agent returns a concrete recommendation.

Implementation targets:

- Create: `apps/mac/Sources/HealthAgentMac/FeatureViews.swift` chart components or split out `TrendViews.swift` if file size becomes painful.
- Extend: `DesktopHealthTrendContext.swift`
- Extend: `DesktopWorkspaceContextFactory.swift`
- Backend gap: add series fields for weight, BP, sleep, HRV, SpO2, steps to `/desktop/bootstrap` or a dedicated trend endpoint.

### 4.3 Agent: Analysis Workbench

Current state: chat works, context/evidence exists.

Target:

```text
left: context basket and saved context bundles
center: conversation stream
right: evidence / tool timeline / generated actions / trace
```

Required behavior:

- Context chips are selectable, removable, and expandable.
- The app shows the exact context items that will be sent before submit.
- Tool calls are collapsible timeline rows.
- "No effective reply" states show model/provider/finish reason and retry choices.
- Generated structured commands are never just printed as JSON; they become confirmable UI actions.

Borrowed idea:

- OpenHands treats actions as first-class UI events.
- OpenSail treats runs as reviewable work with context, permissions, and outputs.

Implementation targets:

- Modify: `AgentChatViewModel.swift`
- Modify: `AgentStreamParser.swift`
- Modify UI: `HealthAgentMacApp.swift` / `FeatureViews.swift`
- Extend tests: `AgentStreamClientTests.swift`

### 4.4 Record: Low-Friction Capture

Current state: natural language and structured forms exist.

Target:

- Natural language parser result becomes a visible draft.
- User confirms or edits fields; successful save appears in local recent records immediately.
- Add repeat actions:
  - same as last breakfast
  - drink 500 ml
  - supplements done
  - weight today
- Add drag/drop and clipboard intake:
  - food image
  - lab PDF/image
  - selected text from another app in later phase
- Voice capture should be a first-class input mode, but typed input does not need over-optimization.

Implementation targets:

- Modify: `RecordHubPresentation.swift`
- Modify: `StructuredRecordDraft.swift`
- Modify: `RecordClient.swift`
- UI: `FeatureViews.swift`

### 4.5 Genetics: Risk Workbench

Current state: summary and finding detail exist.

Target:

- Category drilldown with filter/sort:
  - high risk
  - requires confirmation
  - actionability
  - evidence level
- Finding detail:
  - SNP/genotype
  - source and confidence
  - why this is or is not clinically actionable
  - linked labs/records/actions
  - Agent entry with current finding and relevant recent data
- Add reanalysis job detail and delta view:
  - what changed since last analysis
  - which calls were downgraded/upgraded
  - which require raw-data confirmation

Implementation targets:

- Existing UI: `geneticsWorkspaceDetails` in `HealthAgentMacApp.swift`
- Core context: `DesktopWorkspaceContextFactory.swift`
- Backend: genetic finding detail endpoint or richer bootstrap payload.

### 4.6 Knowledge: Evidence Control Tower

Current state: knowledge page shows tasks and counts.

Target:

- Show coverage by domain:
  - genetics
  - nutrition
  - exercise
  - sleep/recovery
  - pharmacogenomics
  - labs
- Show source mix:
  - Dedao
  - PubMed
  - system rules
  - user records
- Show "weak evidence" queues:
  - claims without citations
  - stale claims
  - claims not connected to actionable workflows
- Agent answer audit:
  - last N answers and whether evidence was used
  - missing source warnings

Implementation targets:

- Backend: knowledge coverage endpoint.
- UI: knowledge workspace detail sections.
- Tests: workspace summary decoding and presentation tests.

### 4.7 Jobs and Trace: Reviewable Runs

Target:

- Jobs are not just status rows. Each job should show:
  - trigger
  - input context
  - files/source hashes
  - provider/model
  - tool timeline
  - cost/latency if available
  - output artifacts
  - retry/continue/fork actions

This is directly inspired by OpenSail's run metadata and OpenHands event stream approach.

Implementation targets:

- Extend: `DesktopJobOutcomePresentation.swift`
- Extend: `TraceClient.swift`
- UI: job detail sheet and trace page.

### 4.8 Global Entry and Permissions

Target:

- Menu bar actions:
  - open today
  - ask Agent
  - quick record
  - import file
  - quit
  - sync status
- Global command palette:
  - `Cmd+K` in app
  - optional user-configurable global shortcut after permission review
- Hold-to-speak:
  - optional; useful only after speech crash path is stable.
- Permission preflight screens:
  - microphone
  - input monitoring if global hotkey/selected text capture is added
  - automation if selected text capture uses AppleScript

Dependency note:

- Prefer native commands first.
- If user-configurable global hotkeys are needed, evaluate `sindresorhus/KeyboardShortcuts`.
- Add exact package version/revision only after license/security review.

---

## 5. Implementation Roadmap

### Phase 1: Make Data and Today Fully Inspectable

**Goal:** Every major metric and action on Today/Data opens detail and can start Agent with context.

Tasks:

1. Add reusable chart/detail components for metric trends.
2. Move current `HealthTrendDetailSheet` into a dedicated component file if `HealthAgentMacApp.swift` grows too large.
3. Add hover/focus/keyboard affordances to clickable metric cards.
4. Add "Create action from this trend" placeholder route that starts as Agent prompt only.
5. Add tests for trend context construction for diet/water/supplements/steps.
6. Add snapshot-like view-model tests for Today command cards.

Acceptance:

- Data page: clicking any non-empty card opens detail.
- Detail: has chart, raw points/records, Agent context handoff.
- Today page: top cards can ask Agent with specific context.
- `swift test --package-path apps/mac` passes.

### Phase 2: Agent Workbench and Context Basket

**Goal:** Users can see and control what the Agent sees.

Tasks:

1. Introduce `AgentContextBasketPresentation`.
2. Add context item grouping: health trend, record, gene finding, knowledge doc, job/trace.
3. Make context chips expandable.
4. Add "send with context" preview before submit.
5. Convert JSON command-looking assistant output into confirmable action rows.
6. Add stream error panel with provider/model/timing/finish reason.

Acceptance:

- Agent page makes selected context obvious.
- No structured tool command is displayed as raw JSON without an action affordance.
- Failed/empty model responses show retry/switch model actions.

### Phase 3: Record Capture Loop

**Goal:** Desktop capture is fast but still auditable.

Tasks:

1. Natural language input returns structured preview before saving.
2. Add repeat-last shortcuts from local recent records.
3. Add file/image drop to record page with explicit classification.
4. Add "save locally pending sync" state if network fails.
5. Add local recent record optimistic update after save.

Acceptance:

- "晚餐 半碗米饭 牛肉 西兰花 喝水500ml" produces separate draft rows.
- Save success updates local recent records immediately.
- Network failure is visible and recoverable.

### Phase 4: Genetics and Knowledge Drilldown

**Goal:** Genetic and knowledge pages become evidence workbenches, not count dashboards.

Tasks:

1. Add category/finding detail routes and keyboard navigation.
2. Add gene finding "related data" section.
3. Add reanalysis delta view if backend provides previous report.
4. Add knowledge source coverage cards.
5. Add weak-evidence queue.
6. Add Agent handoff from every finding/category/claim.

Acceptance:

- A high-risk finding can be opened, inspected, and discussed with Agent using exact SNP/genotype/evidence context.
- Knowledge page shows where the system is strong or weak.

### Phase 5: Global Entry and Desktop-Native Automation

**Goal:** Mac app becomes available from anywhere without becoming intrusive.

Tasks:

1. Harden menu bar state and quit/open actions.
2. Add command palette coverage for all primary routes/actions.
3. Add optional launch-at-login setting.
4. Evaluate global hotkey dependency.
5. Add permission preflight screens before microphone/input monitoring/automation.
6. Add selected-text capture only after explicit permission and visible indicator.

Acceptance:

- User can open quick record/Agent from menu bar reliably.
- Permission prompts explain why they are needed before macOS asks.
- No background capture happens silently.

---

## 6. Data/API Gaps

The Mac UI can improve immediately, but these backend gaps limit full value:

1. Dedicated trend endpoint:
   - `GET /api/v1/desktop/trends?metric=diet&range=7d`
   - supports diet, water, supplements, weight, BP, steps, sleep, HRV, SpO2.

2. Agent context preview endpoint:
   - returns normalized context that backend will actually inject.
   - prevents Mac UI and backend context from drifting.

3. Structured command confirmation endpoint:
   - assistant proposes record/action/job.
   - Mac confirms and sends typed command, never raw JSON pasted in chat.

4. Knowledge coverage endpoint:
   - claim counts by domain, source mix, stale/weak evidence.

5. Genetic report detail endpoint:
   - finding detail, category detail, delta from previous analysis.

---

## 7. Testing Strategy

### 7.1 Core Tests

Add/extend tests under:

- `apps/mac/Tests/HealthAgentMacCoreTests/MacP0FeatureTests.swift`
- `AgentStreamClientTests.swift`
- `DesktopDashboardPresentationTests.swift`
- `RecordHubPresentationTests.swift`

Required test themes:

- context factory payloads for every selectable detail
- trend context contains selected range and points
- Agent basket includes/removes context predictably
- structured commands become action models
- failed/empty stream gets user-visible state
- record drafts validate before save

### 7.2 Manual Verification

Before claiming completion for UI phases:

1. `swift test --package-path apps/mac`
2. `apps/mac/scripts/package-app.sh --install`
3. launch `/Applications/健康 Agent.app`
4. verify:
   - Today loads
   - Data card click opens detail
   - Agent handoff includes context
   - Record save still works
   - model picker is usable
   - menu bar still opens/quit works

---

## 8. Dependency Policy

Do not add new dependencies by default.

Potential dependencies:

| Dependency | Use Only If | Review Needed |
|---|---|---|
| `sindresorhus/KeyboardShortcuts` | native command shortcuts are insufficient for global hotkeys | exact version, MIT license, recent release, SPM integration |
| `SwiftUICharts` | Swift Charts cannot support needed health chart interaction/performance | exact version, activity, accessibility, maintenance |

Preferred path:

1. Use first-party SwiftUI/AppKit/Charts.
2. Add small local component.
3. Add third-party dependency only when it removes clear complexity.

---

## 9. Priority Decision

Recommended order:

1. **Phase 1: Data/Today inspectability**
   - Highest user value.
   - Uses data already present.
   - Low backend risk.

2. **Phase 2: Agent workbench**
   - Fixes trust and "model saw what?" problem.
   - Reduces false bug reports caused by hidden context/tool state.

3. **Phase 3: Record capture**
   - Improves daily usage loop.
   - Needed before Mac can replace mobile for desk-time health tracking.

4. **Phase 4: Genetics/Knowledge**
   - Important for evidence quality and long-term differentiation.
   - More dependent on backend detail endpoints.

5. **Phase 5: Global entry**
   - Powerful but permission-sensitive.
   - Should wait until core windows and crash paths are stable.

---

## 10. Source Links

- CodeEdit: https://github.com/CodeEditApp/CodeEdit
- Apple Food Truck sample: https://github.com/apple/sample-food-truck
- Apple Swift Charts: https://developer.apple.com/documentation/Charts
- OpenHands: https://github.com/OpenHands/OpenHands
- OpenHands AGENTS guidance: https://github.com/OpenHands/OpenHands/blob/main/AGENTS.md
- OpenSail: https://github.com/TesslateAI/OpenSail
- SuperCmd: https://github.com/SuperCmdLabs/SuperCmd
- KeyboardShortcuts: https://github.com/sindresorhus/KeyboardShortcuts
- DesktopCtl: https://desktopctl.com/
- SwiftUICharts: https://github.com/willdale/SwiftUICharts

