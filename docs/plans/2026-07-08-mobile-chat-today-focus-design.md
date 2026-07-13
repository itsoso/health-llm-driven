# Mobile Chat Today Focus Design

## Goal

When the user opens 小巴 on mobile, the first screen should make today’s most important action obvious within three seconds: what to do, why now, and where to tap.

## Problem

The mobile Agent conversation page has become the main shell for 小巴. It currently mixes the header, today briefing, opener message, message stream, confirmations, suggestions, attachments, and voice input. This gives the page broad capability, but the first screen can feel like a stack of competing widgets rather than a clear daily command surface.

Recent UI feedback points to the same root issue:

- 今日简报 needs weather, air quality, today plan, advice, and yesterday summary when real data exists.
- 今日行动 card should feel more professional and less like a generic card.
- 待你确认 should not keep resurfacing after confirmation.
- Plan, supplements, and medications should not duplicate the same item in multiple places.
- Input and voice controls should follow familiar WeChat interaction while staying consistent with Reva visual language.

## Recommended Direction

Use a Chat-specific `Today Focus` region above the message list. It replaces the weak briefing strip with a compact decision summary, not a full dashboard.

The first screen should answer:

1. **What is the most important action now?**
2. **Why is this the right action now?**
3. **What is the next tap?**

Everything else becomes a secondary status entry.

## Alternatives Considered

### Option 1: Today Command Surface

Place one focused daily action under the Chat header, with a short reason and clear actions. This is the recommended path because it preserves 小巴 as the agent-native home while making the page immediately useful.

Tradeoff: The client needs a small resolver layer to choose one focus action and dedupe secondary items.

### Option 2: Message Stream First

Render today action, briefing, and confirmations as assistant messages in the chat stream.

Tradeoff: It feels conversational, but important daily actions can be buried by history or long model responses.

### Option 3: Today Dashboard First

Turn the chat landing into a Today-style dashboard and push conversation lower.

Tradeoff: It makes information dense and clear, but conflicts with the current product direction that 小巴 chat is the agent-native main shell.

## Proposed UX

### Default State

Show one compact focus card:

- Eyebrow: `现在最重要`
- Title: the selected action, for example `恢复/休息：暂停高强度`
- Reason: one sentence, for example `昨晚恢复不足，今天优先降低训练负荷`
- Actions:
  - `去执行`: primary, follows the selected action deep link.
  - `为什么`: expands local evidence and verification.
  - `问小巴`: sends or pre-fills a focused prompt with the action context.

### Expanded State

Tapping `为什么` expands two sections:

- `依据`: real signals such as sleep, HRV, training load, weather, air quality, overdue state, or dynamic Today evidence. Only show signals that exist in real data.
- `验证`: what the user should watch today, such as energy, steps, blood pressure, weight/waist, symptoms, or sleep outcome.

### Queue State

Secondary items collapse into one status strip:

`待确认 3 · 接下来 2 · 用药 0/6 · 补剂 0/3`

Tapping an item opens the relevant Today detail or list. The first screen does not render multiple large cards for these secondary queues.

## Dedupe Rule

The same work item should appear only once on the first screen.

Client-side dedupe should use, in order:

1. `actionKey` or stable backend id.
2. Normalized title.
3. Domain plus scheduled time.

If an item is already promoted as the main action, secondary areas should show only counts, not another full card for the same item.

## Data Sources

The component should not fabricate health signals.

Primary action priority:

1. Dynamic Today view `daily_artifact` or `next_action`.
2. Daily operating plan first actionable item.
3. Timeline current/next item.
4. Empty state: `今日暂无重点行动`.

Reason and evidence:

1. Dynamic Today card reason/evidence.
2. Daily artifact reason/evidence.
3. Timeline overdue/current state.
4. Weather and air quality only when present in existing backend data.

Status strip:

- `useTodayTimeline` for actionable/completed counts.
- Medication and supplement summaries from existing Today/home data when available.
- WriteIntent count when available.

## Component Boundary

Create a chat-specific component, tentatively `ChatTodayFocusCard`.

Responsibilities:

- Select one focus action.
- Render title, reason, actions, expanded evidence, and status strip.
- Emit route/prompt callbacks to `ChatScreen`.
- Avoid duplicate first-screen display.

Non-responsibilities:

- It should not render full Today dashboard lists.
- It should not duplicate chat message cards.
- It should not make up weather, air quality, summary, or plan data.

## Testing Requirements

Cover these behaviors:

- Selects dynamic Today action before daily plan fallback.
- Shows honest empty state when no real action exists.
- Does not duplicate promoted action in secondary status.
- Expands `为什么` with evidence only when data exists.
- `去执行` routes to deep link or Today fallback.
- `问小巴` creates a focused prompt/context.
- Maintains compact first-screen height on mobile.

## Rollout

Implement in three small steps:

1. Replace `BriefingStrip` with the focus card default state.
2. Add the deduped status strip.
3. Add expanded evidence from richer Today data, including weather and air quality only when real fields exist.

This keeps the first release useful while avoiding a broad dashboard rewrite.
