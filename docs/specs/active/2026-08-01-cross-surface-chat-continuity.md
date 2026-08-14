# Feature Spec: Cross-Surface Chat Continuity

> Status: approved
> Owner: Codex
> Updated: 2026-08-01
> Related PRD/PDD: `docs/prd/2026-08-01-cross-surface-chat-continuity.md`
> Related code: `backend/app/api/agent.py`, `frontend/src/app/ai-assistant/page.tsx`, `mobile/hooks/useChatEngine.ts`, `mobile/app/(tabs)/chat.tsx`
>
> **Current release override (2026-08-12):** all repo-contained automatic remote/vendor release
> entrypoints, local signing/install/automatic-provisioning entrypoints and every OTA/rollback
> channel are frozen. EAS channel→branch mapping can drift or be shared, so preview/development is not an
> exception. Production network observation and release plan/validate are also frozen. Only local
> validation, offline evidence and public unauthenticated HTTPS are allowed, and none forms G5/G6;
> release is BLOCKED pending a new
> repo-external trust-root dossier and independent G4.

## 1. Decision

Make the backend conversation store and its `updated_at` order the canonical
continuity rule for Web and Mobile, while making the Mobile chat shell truly
edge-to-edge and restoring a clear “小巴” brand hierarchy.

## 2. Problem

The two clients already read owner-scoped conversations from the same backend,
but they choose the initial conversation differently. Mobile prefers a
device-local conversation id and may prefer a daily briefing; Web remains on a
blank draft unless the URL contains `?c=`. The mismatch creates unnecessary
new threads and makes one durable history look like two unrelated histories.

On iPhone, the chat surface also begins below a grey status-bar region with a
large rounded-card silhouette. The 23pt “小巴” label is visually weaker than
the dense answer content below it.

## 3. Requirement Admission

```yaml
RequirementAdmission:
  request: unify Web and Mobile conversation continuity; make Mobile chat full-screen; improve the 小巴 title scale
  classification: cross-surface conversation contract and Mobile presentation
  first_user_fit: people who alternate between phone and Web for the same health conversation
  core_loop_step: observe/review -> converse -> act -> verify
  first_class_objects: [ExecutionEvent]
  target_surface: [Mobile, Web, Backend]
  source_of_truth: owner-scoped backend AgentConversation rows ordered by updated_at
  safety_level: medium
  prescription_or_causal_verdict: none
  autonomy_tier: none
  evidence_provenance: persisted conversation and message timestamps
  claim_hedging: no new health claim generation
  verification_window: immediate after opening either client
  success_metric: both clients resume the same latest durable conversation unless the user explicitly chooses another/new thread
  added_user_burden: none
  burden_justification: not applicable
  non_goals: [physical message merging, one forever-thread, cross-account history, backend schema changes]
  smallest_end_to_end_slice: aligned resume selection plus matching history order and edge-to-edge Mobile shell
  stale_surface_to_remove_or_archive: [Mobile briefing-first boot, Web blank-by-default boot, rounded card-like Mobile root]
  spec_required: yes
```

## 4. Non-Goals

- Do not concatenate messages from distinct conversations.
- Do not add a server-side mutable “last active device” pointer in this slice.
- Do not change Agent generation, health-write, medical-safety, or model-routing behavior.
- Do not expose another user's conversation or relax existing authorization.
- Do not redesign the composer, conversation bubbles, or Web layout.

## 5. Product Object Mapping

| Object | Change |
|---|---|
| `ExecutionEvent` | The same durable conversation execution trail is resumed across Web and Mobile. |

## 6. User Flow

```text
open Web or Mobile chat
  -> preserve an explicit deep link / selected conversation / active local turn
  -> otherwise read owner-scoped conversations ordered by updated_at
  -> load the newest durable conversation and messages
  -> continue the same thread
  -> explicit “new conversation” creates a blank draft until first send
```

## 7. Surface Contract

| Surface | Responsibility | Contract |
|---|---|---|
| Mobile | Primary daily chat; edge-to-edge presentation | Resume latest durable server conversation unless an explicit route or active local turn owns state. Show history in server order. |
| Web | Secondary chat and history | Explicit `?c=` wins; without it, resume the latest durable server conversation. Explicit new-chat remains blank in the mounted session. |
| Backend | Canonical owner-scoped durable store | Existing list/detail endpoints remain the source of truth; no schema or response-shape change. |

## 8. Data Contract

```yaml
apis:
  - GET /agent/conversations (unchanged; canonical latest order)
  - GET /agent/conversations/{id} (unchanged; owner scoped)
events: []
models: []
fields: []
enums: []
backward_compatibility: additive client behavior only
migration: none
```

## 9. Safety, Privacy, And Medical Boundary

Conversation content remains L3 health data. Both surfaces must continue using
their authenticated owner-scoped endpoints; no client may merge by title,
message content, or an untrusted local id. An invalid, deleted, or unauthorized
conversation must fail closed and fall back to another owner-scoped list item
or an explicit empty/error state. No medical recommendation or write-autonomy
boundary changes.

## 10. AI Behavior

No LLM behavior changes. Qwen3.7-max may evaluate UI/contract acceptance, but
its judgment cannot override deterministic ownership, ordering, or tests.

## 11. Acceptance Criteria

```gherkin
Given the same account has a newer durable conversation created on Mobile
When Web opens /ai-assistant without a conversation query
Then Web loads that latest conversation instead of silently starting blank

Given the same account has a newer durable conversation created on Web
When Mobile opens chat without an explicit new-chat route and no active local stream owns state
Then Mobile loads that latest conversation even if an older device-local id exists

Given Web has an explicit valid ?c=<id> or the user selects a history item
When the page resolves its initial state
Then the explicit conversation wins over the latest-conversation default

Given the user explicitly taps New conversation
When the mounted client renders
Then it stays blank until the first send and is not immediately replaced by history

Given an authenticated user lists or loads conversations
When either client makes the request
Then only that user's records are returned and no content-based merge occurs

Given Mobile chat renders on an iPhone
When the app is at the chat root
Then the background extends behind the status bar, controls respect safe-area insets, and no rounded sheet silhouette remains

Given the Mobile header renders
When “小巴” appears beside its avatar
Then the title has a stronger, body-coordinated brand scale, does not collide with action controls, and every interactive header target is at least 44pt
```

## 12. Verification Plan

```bash
# Mobile
cd mobile && npm test -- --runInBand hooks/__tests__/useChatEngine.test.ts components/chat/__tests__/ConversationSheet.test.tsx app/'(tabs)'/__tests__/chat.test.tsx components/chat/__tests__/ChatHeader.test.tsx
cd mobile && npx tsc --noEmit

# Web
cd frontend && npm test -- --runInBand src/app/ai-assistant/__tests__/page-url.test.tsx
cd frontend && npx tsc --noEmit

# Contract/docs
python backend/scripts/check_dossier_consistency.py
python scripts/check_doc_drift.py
git diff --check
```

Manual verification uses the same test account on Web and iPhone: create a
thread on each surface, open the other surface, verify the latest thread and
history order, then verify new-chat isolation. Capture an iPhone screenshot for
the status-bar/full-screen and title hierarchy checks.

## 13. Rollout And Rollback

No migration or feature flag is required. Validate Web and Mobile locally; do not deploy frontend
or call any OTA/rollback channel. The manual release Gate remains BLOCKED, and an existing candidate
is read-only. There is no active production rollback writer; additive backend compatibility remains
and durable conversation data is untouched.

## 14. Open Questions

None blocking. A future server-owned active-conversation pointer is intentionally
deferred until evidence shows “latest updated” is insufficient.

## 15. Changelog

| Date | Change | Reason |
|---|---|---|
| 2026-08-01 | Approved latest-durable continuity and edge-to-edge Mobile shell | User confirmed the full-screen target is the entire chat page. |
| 2026-08-01 | Raised Mobile header interaction targets to 44pt | qwen3.7-max accessibility concern was valid after deterministic style inspection. |
