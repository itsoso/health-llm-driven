# Mobile Agent Reliability Kernel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make every Mobile Agent turn, health write, voice transition and unsent attachment recoverable, mutually consistent and visibly verified.

**Architecture:** Add pure state contracts around the existing Chat engine, card dispatcher and voice hooks. Backend adds only deterministic receipt metadata to existing stream events; Mobile remains fail-closed and derives UI from `AgentTurnState`, `WriteReceipt` and `ComposerState`.

**Tech Stack:** Expo SDK 55, React Native 0.83, TypeScript, React hooks/reducers, AsyncStorage, expo-file-system, FastAPI/Python, Jest, pytest.

---

## Phase P0.1: AgentTurn

### Task 1: Add Pure AgentTurn State Contract

**Files:**
- Create: `mobile/utils/agentTurnState.ts`
- Create: `mobile/utils/__tests__/agentTurnState.test.ts`

**Steps:**
1. Write failing table tests for submit, status mapping, write/tool transitions, done, fail, interrupt and recover.
2. Run `cd mobile && npm test -- --runInBand --runTestsByPath utils/__tests__/agentTurnState.test.ts`; expect module-not-found/failing assertions.
3. Implement `createIdleAgentTurn`, `reduceAgentTurn`, `isAgentTurnTerminal`, and `agentTurnPhaseFromStatus` with no React dependency.
4. Re-run the focused test; expect PASS.
5. Run `npx tsc --noEmit --pretty false`.

### Task 2: Integrate AgentTurn With Chat Stream And Recovery

**Files:**
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/hooks/__tests__/useChatEngineHistory.test.ts`

**Steps:**
1. Write failing tests asserting submit creates a turn, status/tool/done update it, errors keep content, and foreground recovery resolves a persisted pending turn.
2. Run the focused hook tests and confirm the expected failures.
3. Add `activeTurn` reducer state, stable client turn ID, small AsyncStorage snapshot, and reconciliation with authoritative history.
4. Keep existing 30-second local-stream ownership guard; AgentTurn replaces only the boolean lifecycle semantics, not message buffering.
5. Re-run hook tests and TypeScript.

## Phase P0.2: WriteReceipt

### Task 3: Normalize Card Action Receipts

**Files:**
- Create: `mobile/services/writeReceipt.ts`
- Create: `mobile/services/__tests__/writeReceipt.test.ts`
- Modify: `mobile/services/chatCardActions.ts`
- Modify: `mobile/services/__tests__/chatCardActions.test.ts`

**Steps:**
1. Write failing tests for diet record ID, WriteIntent executed_ref, agenda execution reference and missing identity.
2. Verify RED with focused Jest.
3. Add `WriteReceipt` and normalization helpers. For write actions, return `receipt` on `ChatCardActionResult`; throw `write_receipt_missing_identity` when persistence cannot be verified.
4. Preserve `route.open` and inline UI patch behavior without write receipts.
5. Verify GREEN and TypeScript.

### Task 4: Present Receipt State In Cards

**Files:**
- Modify: `mobile/components/chat/cards/types.ts`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/components/chat/cards/__tests__/registry.test.tsx`

**Steps:**
1. Write failing tests: verified receipt renders completed; missing receipt stays error/retryable; duplicate press while running/done does not dispatch.
2. Verify RED.
3. Store receipt by action key, expose a concise “已写入 · #ID” or `executed_ref` state, and keep payload for retry.
4. Invalidate Today/Agenda/Diet only after receipt validation.
5. Verify focused ChatBubble/registry tests.

### Task 5: Add Deterministic Agent Tool Receipt

**Files:**
- Modify: `backend/app/services/agent_executor.py`
- Modify: `backend/tests/test_agent_executor_fast_routing.py`
- Modify: `mobile/services/chat.ts`
- Modify: `mobile/services/__tests__/chatStream.test.ts`

**Steps:**
1. Write failing Python helper tests for JSON results with `id`, `record_id`, nested resource, malformed JSON and soft failures.
2. Write failing stream parser test for additive `tool_result.data.receipt`.
3. Implement a pure `_write_receipt_from_tool_result` helper and attach its output only for successful write tools.
4. Add optional receipt to Mobile `StreamEvent`; old events remain valid.
5. Run focused backend/mobile tests and Python compile.

## Phase P0.3: ComposerController

### Task 6: Add Composer State Reducer

**Files:**
- Create: `mobile/components/chat/composerState.ts`
- Create: `mobile/components/chat/__tests__/composerState.test.ts`

**Steps:**
1. Write failing transition tests for text/hold toggle, hold start/record/transcribe, live dictation enable/disable, submit and background reset.
2. Verify RED.
3. Implement pure reducer and selectors `canStartHold`, `canStartDictation`, `shouldShowDisabledMic`, `isComposerBusy`.
4. Verify GREEN.

### Task 7: Refactor ChatInputBar To Use Composer State

**Files:**
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Modify: `mobile/hooks/useRealtimeDictation.ts`
- Modify: `mobile/hooks/useVoiceRecording.ts`
- Modify: `mobile/hooks/__tests__/useRealtimeDictation.test.ts`
- Modify: `mobile/hooks/__tests__/useVoiceRecording.test.ts`

**Steps:**
1. Add failing component tests for mutual exclusion, second mic click disable, submit cleanup, mode switch cleanup and AppState background cleanup.
2. Verify RED.
3. Replace duplicated mode/audio booleans with reducer events while retaining current gesture thresholds and WeChat visuals.
4. Add explicit `stop/cancel` lifecycle methods and ensure audio release is awaited before the next mode starts.
5. Re-run all composer/voice tests and TypeScript.

## Phase P0.4: Drafts, Images And Context

### Task 8: Persist Text And Image Drafts Privately

**Files:**
- Create: `mobile/services/chatDraftStorage.ts`
- Create: `mobile/services/__tests__/chatDraftStorage.test.ts`
- Modify: `mobile/hooks/useMediaPicker.ts`
- Modify: `mobile/components/chat/ChatInputBar.tsx`
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`

**Steps:**
1. Write failing tests for metadata restore, corrupt/missing file pruning, explicit remove and acknowledged-send cleanup.
2. Verify RED.
3. Debounce text to AsyncStorage; copy image bytes to an App-private draft directory and persist metadata only.
4. Restore on mount. Do not clear until `onSend` accepts the operation; retain on immediate failure.
5. Verify focused tests and TypeScript.

### Task 9: Preserve Deterministic Context Across The Turn

**Files:**
- Modify: `mobile/hooks/useChatEngine.ts`
- Modify: `mobile/hooks/__tests__/useChatEngine.test.ts`
- Modify: `mobile/hooks/__tests__/useChatEngineHistory.test.ts`

**Steps:**
1. Write failing tests for latest verified receipt, pending draft context and history image/card restoration.
2. Verify RED.
3. Attach only structured recent receipt/context metadata to the next request; never infer it from visible prose.
4. Clear ephemeral context after server acknowledgment, not on navigation.
5. Verify hook/history tests.

## Phase P1: Lower Density And Better Waiting

### Task 10: Remove Generic Four-Action Reply Grid

**Files:**
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/services/chatResultActions.ts`
- Modify: `mobile/services/__tests__/chatResultActions.test.ts`

**Steps:**
1. Write failing tests that a normal reply and a completed `health_record` reply do not render generic Generate Record / Save Memory / Add Plan actions.
2. Verify RED.
3. Remove the fixed grid. Keep server-card actions authoritative and retain copy/share/speech as secondary controls.
4. Delete now-unused assistant-prose-to-record write path if no remaining caller exists.
5. Verify focused tests and `rg` no dead imports.

### Task 11: Adaptive Today Focus And Turn Status

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Modify: `mobile/components/chat/ChatTodayFocusCard.tsx`
- Modify: `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`
- Modify: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Steps:**
1. Write failing tests for full empty-state focus, compact active-conversation focus and keyboard-hidden restoration.
2. Verify RED.
3. Add compact variant with one-line title/status; collapse on messages, keyboard or active turn.
4. Use `activeTurn` label for one human-readable progress line and retry action on recoverable failure.
5. Verify focused Chat tests.

### Task 12: Stabilize Bootstrap Loading

**Files:**
- Modify: `mobile/app/(tabs)/chat.tsx`
- Create or modify: `mobile/services/agentHomeBootstrap.ts`
- Test: `mobile/app/(tabs)/__tests__/chat.test.tsx`

**Steps:**
1. Write failing test preventing opener/default chips/focus from flickering while boot queries settle.
2. Verify RED.
3. Add a client bootstrap coordinator over existing queries; do not add a backend endpoint unless profiling proves network overhead is dominant.
4. Render one stable loading state and keep cached values during refresh.
5. Verify tests.

## Phase P2: Trust, Persona And Metrics

### Task 13: Make Memory Use Visible

**Files:**
- Modify: `mobile/components/chat/EmptyStateHome.tsx`
- Modify: `mobile/components/chat/AttributionChips.tsx`
- Modify: `mobile/components/chat/__tests__/EmptyStateHome.test.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`

**Steps:**
1. Write failing tests for concise memory/data chips and route to memory management.
2. Verify RED.
3. Show only structured memory/source metadata already supplied by backend; no prose inference.
4. Preserve XiaoBa avatar/name and reduce decorative duplication.
5. Verify focused tests.

### Task 14: Add Reliability Telemetry

**Files:**
- Modify: `mobile/services/clientEvents.ts`
- Modify: `backend/app/api/client_events.py`
- Modify: corresponding client event tests

**Steps:**
1. Write failing allowlist/shape tests for `agent_turn_terminal`, `voice_input_terminal`, and `write_receipt_terminal`.
2. Verify RED.
3. Emit privacy-safe metadata: phase, duration bucket, error code, action type and verified boolean; never content/audio/base64.
4. Verify backend/mobile tests.

## Phase G3-G6: Verification And Release

### Task 15: Integrated Verification And Safety Review

1. Run all focused Mobile suites without output truncation.
2. Run `cd mobile && npx tsc --noEmit --pretty false`.
3. Run focused backend pytest and `python3 -m py_compile`.
4. Run `python3 backend/scripts/check_dossier_consistency.py` and `python3 scripts/check_doc_drift.py`.
5. Run `git diff --check` on touched files.
6. Review diff for manual-confirm, user isolation, audio privacy, attachment logging and false-success regressions; fix blockers and rerun.

### Task 16: Simulator And Release Gate

1. Build/launch with `./scripts/sim-build.sh "iPhone 17 Pro"`.
2. Exercise the simulator matrix from the Feature Spec and capture screenshots.
3. Do not deploy from the dirty/behind workspace. Reconcile or land the exact commits, then deploy backend from a clean `origin/main` worktree.
4. Publish Mobile production OTA only after backend health and contract smoke pass.
5. Record deploy IDs, health score and rollback point in the Dossier.
6. Ask for user true-device confirmation before G6 PASS.
