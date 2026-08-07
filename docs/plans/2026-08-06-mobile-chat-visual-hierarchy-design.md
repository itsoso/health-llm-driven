# Mobile Chat Visual Hierarchy Design

**Date:** 2026-08-06  
**Status:** Approved (方案 B：舒展易读)  
**Release target:** iOS 1.3.3

## Problem

The current chat screen gives the top chrome too much visual weight: the 28pt “小巴” title and three individually filled 44pt action circles dominate the first row. At the same time, the assistant identity inside the conversation is too quiet, so the hierarchy reverses where it matters. The task strip, utility rail, and composer also use slightly different visual densities.

The user explicitly chose to preserve the current conversation body size. This change therefore improves hierarchy without reducing health-content readability or altering any chat behavior.

## Chosen direction

Use a restrained, comfortable hierarchy:

- Keep the existing warm paper palette, green brand color, message body typography, cards, and navigation behavior.
- Reduce the top title from display-like scale to a compact page-title scale.
- Keep Apple-sized touch targets while making the visible action controls lighter and smaller.
- Promote the assistant identity inside each assistant turn.
- Normalize spacing, icon weight, borders, and corner radii across the header, focus strip, assistant utility rail, and composer.

## Component design

### Header

- `XiaoBaAvatar`: 30pt visual size.
- “小巴”: 24pt / 30pt, weight 800. The model chevron becomes 15pt and stays vertically centered.
- The row remains a single line with 16pt horizontal page padding.
- New chat, history, and settings retain at least a 44×44pt effective hit target. Their visible controls become a lighter segmented toolbar instead of three heavy nested circles.
- Use one outer paper-toned container, hairline border, 2pt internal padding, and consistent 18–19pt outline icons.
- No labels are added to the visual row; existing accessibility labels and hints remain authoritative.

### Today focus / pending-task strip

- Preserve its one-line information model and current tap/dismiss behavior.
- Use a 44pt minimum row height, a 28pt icon slot, 14pt emphasized state label, and 15pt task title.
- Keep the left semantic accent and caution/risk colors, but reduce competing decoration.
- Chevron and close actions retain effective touch targets even when their visible glyphs stay compact.

### Conversation turns

- Preserve the current body font size and Markdown spacing.
- Raise the assistant signature “小巴” to 16pt / 22pt, weight 700, with a 6pt brand dot.
- Keep the signature visually close to the assistant response with an 8pt identity-to-content gap.
- Do not add avatars to every message; that would reduce horizontal reading width and make long health answers busier.
- User bubbles, inline cards, data precision, write confirmations, and safety messaging remain unchanged.

### Utility rail and composer

- Keep all existing actions and interaction states.
- Align hairline borders, warm neutral backgrounds, and corner-radius vocabulary with the header toolbar.
- Preserve readable composer text and 44pt touch targets for audio, microphone, send, and attachment actions.
- Tighten only redundant outer padding so the composer feels integrated with the screen without reducing control accessibility.

## Architecture and data flow

This is a presentation-only change. Existing props, hooks, navigation, message data, write receipts, accessibility labels, and error paths stay unchanged. Styling remains colocated with the existing React Native components and continues to use `revaTheme` tokens and `StyleSheet.create`; no new design-system abstraction is introduced.

Primary implementation surfaces:

- `mobile/components/chat/ChatHeader.tsx`
- `mobile/components/chat/LlmModelPicker.tsx`
- `mobile/components/chat/ChatTodayFocusCard.tsx`
- `mobile/components/chat/ChatBubble.tsx`
- `mobile/components/chat/ChatInputBar.tsx`

## Accessibility and performance

- Effective interactive targets remain at least 44×44pt through layout size or `hitSlop`.
- Existing VoiceOver labels, roles, and hints remain stable.
- Header and task text keep bounded Dynamic Type multipliers so the single-line layout does not collide.
- No new state, animation, image, list subscription, or render-time object allocation is introduced.
- All new styles use `StyleSheet.create` and existing static tokens.

## Verification

Follow test-first changes for each visual contract:

- Header title/avatar/action-toolbar proportions.
- Focus-strip type scale and effective controls.
- Assistant signature type scale and spacing while body typography stays unchanged.
- Composer surface spacing and touch targets.

Then run the focused Jest suites, mobile typecheck/lint, and the project mobile integration gate. Validate on the connected iPhone for safe area, Dynamic Type at default and one larger step, long assistant replies, inline cards, keyboard transitions, and scroll-to-latest behavior. The App Store candidate must not proceed until the full release CI is green.

## Non-goals

- No chat workflow or navigation changes.
- No reduced body typography.
- No new animations, custom fonts, icons, cards, or business logic.
- No App Store submission or deployment as part of the styling commit.
