# Mobile Empty Chat Hierarchy Design

**Date:** 2026-07-24  
**Status:** Approved  
**Surface:** Mobile Agent conversation  
**Product object:** Capture and conversational execution entry points

## Problem

The empty Agent conversation currently exposes three independent action systems:

1. opener quick replies;
2. starter suggestions above the composer;
3. focused composer quick actions.

They do not coordinate. This creates duplicate labels such as two `完成了`,
duplicate capture actions such as `拍照记一餐` and `拍照记餐`, and excessive
vertical movement when the keyboard opens. The memory footnote also competes
with the opener body, while the composer expands before the user has entered
enough text to require more space.

The result is a command dashboard inside a conversation rather than an
Agent-native opening turn.

## Direction

Use a conversation-first, progressively disclosed layout.

- The Agent opener is the only primary object in the empty conversation.
- Show at most three unique contextual replies beneath the opener.
- While opener replies are visible, hide generic starter suggestions.
- When the keyboard opens, hide all quick actions and let the conversation and
  composer own the viewport.
- Keep the composer single-line until content actually wraps.
- Move generic capture actions behind the existing attachment menu. They may
  appear inline only when there is no opener and the keyboard is closed.
- Reduce memory provenance to one quiet expandable source row.

## State Contract

### 1. Empty conversation with opener

- Render the opener as a quiet message block with XiaoBa identity.
- Render up to three deduplicated reply actions.
- Do not render `ComposerSuggestionsRow`.
- Do not render focused composer quick actions.
- Normalize reply labels first, then deduplicate by normalized label and action.
- Add `换个话题` only when fewer than three actions remain.

### 2. Empty conversation without opener

- Render one concise greeting.
- Render one horizontal row with at most three starter actions.
- Do not duplicate any action already available in the attachment menu unless
  it is the highest-value first action for a new user.

### 3. Keyboard open or composer focused

- Hide opener reply chips, starter suggestions, and composer quick actions.
- Keep the opener text visible as conversation context.
- Keep the composer at its compact height while the text remains one line.
- Grow only from measured content height, capped at three text lines.

### 4. Draft or active dictation

- Hide all suggestion surfaces.
- Preserve draft and cloud ASR behavior.
- Show only the send action or active microphone state.

## Visual Hierarchy

1. Header and current system status.
2. Agent opener text.
3. One contextual action row, only when the keyboard is closed.
4. Compact composer.

The opener should not look like a nested card. Remove the heavy shadow and use
paper/surface contrast, a hairline only when needed, and restrained spacing.
The memory source becomes a single line such as `依据 1 条医嘱`, with a chevron
to the existing memory screen. Full memory text is not rendered inside the
opener.

## Accessibility

- Each normalized action keeps a unique accessibility label.
- Hidden actions are removed from the accessibility tree.
- Touch targets remain at least 44 points.
- Composer mode and microphone labels remain unchanged.

## Compatibility

- No backend or API contract changes.
- No native dependency changes.
- Existing Alibaba Cloud ASR, image staging, send, attachment, and keyboard
  submit paths remain intact.
- This is eligible for a production OTA after simulator verification.

## Acceptance Criteria

- No duplicate `完成了` or duplicate capture action is visible.
- Opening the keyboard leaves no suggestion rows above the composer.
- Focusing an empty input does not increase composer height.
- The composer grows only after text wraps and is capped at three lines.
- The opener remains readable with the keyboard visible.
- Opener quick replies still send or navigate through their existing handlers.
- Empty state, onboarding, memory-only, text input, dictation, and attachment
  flows have focused tests.

