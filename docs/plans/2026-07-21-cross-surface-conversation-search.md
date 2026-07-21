# Cross-Surface Conversation Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let Web and Mac users search their own historical Xiaoba conversations by title and message content, matching Mobile's existing behavior.

**Architecture:** Reuse the owner-scoped backend `GET /agent/conversations?search=` contract, which already matches a conversation title or any persisted message body. Web wires its existing history rail to a debounced server search; Mac adds the missing history search field and routes it through the existing remote conversation source, keeping offline cache semantics intact.

**Tech Stack:** Next.js 14, React, Vitest, SwiftUI, Swift 6, XCTest, FastAPI existing API.

---

### Task 1: Prove the missing client wiring

**Files:**
- Modify: `frontend/src/app/ai-assistant/__tests__/page-url.test.tsx`
- Modify: `apps/mac/Tests/HealthAgentMacCoreTests/AgentConversationHistoryTests.swift`

1. Add a Web page regression: entering a history query calls
   `agentApi.getConversations` with the trimmed `search` argument and resets to
   the first result page.
2. Add a Mac view-model regression for the user-facing search entry point:
   whitespace is normalized before the remote source is queried, and a search
   subset does not replace the offline full-history cache.
3. Run the focused tests and confirm they fail because the Web page does not
   wire `ConversationHistoryRail.onSearchChange`, and the Mac view model has no
   search entry point.

### Task 2: Wire Web history search

**Files:**
- Modify: `frontend/src/app/ai-assistant/page.tsx`

1. Add controlled search state and pass it to the existing history rail.
2. Fetch `/agent/conversations` with the normalized term after a short debounce.
3. Reset pagination for a new query and ignore stale responses so a slower
   earlier query cannot overwrite later results.
4. Run the focused page test and the history rail component suite.

### Task 3: Wire Mac history search

**Files:**
- Modify: `apps/mac/Sources/HealthAgentMacCore/AgentChatViewModel.swift`
- Modify: `apps/mac/Sources/HealthAgentMac/FeatureViews.swift`

1. Add a view-model search entry point that normalizes whitespace and delegates
   to the existing owner-scoped remote search path.
2. Add a compact search field, clear control, empty result state, and debounced
   request scheduling to the history section.
3. Keep the refresh control scoped to the current query, reset history paging
   when the query changes, cancel pending UI work on disappearance, and retain
   the existing offline-cache fallback behavior.
4. Run the focused XCTest and compile the Mac application.

### Task 4: Verify and deliver

**Files:**
- Modify: `docs/dossiers/` only if release evidence requires it.

1. Run focused Web and Mac tests, Web production build, Mac test/build, and
   `git diff --check`.
2. Deploy the Web frontend using the repository deployment path and verify the
   deployed route returns successfully.
3. Build the Mac app through the repository Mac release path; record any
   distribution constraint rather than claiming an unbuilt binary is available.
4. Commit only the search files and release record, then push `main`.

## Delivery Evidence

- 2026-07-21: Web page regression and the full frontend suite passed (264 tests);
  production build completed.
- 2026-07-21: Mac history regressions passed; `HealthAgentMacCoreTests` passed
  418 tests with 1 existing skip.
- 2026-07-21: Web frontend deployed from `main`; production `/ai-assistant`
  and `/api/v1/health` both returned HTTP 200.
- 2026-07-21: Rebuilt, ad-hoc signed, and installed `/Applications/小巴.app`.
