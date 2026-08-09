# Compact Chat Header Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce the chat header avatar and “小巴” title to the approved compact visual scale without changing interaction or accessibility behavior.

**Architecture:** Keep the existing `ChatHeader` and header-mode `LlmModelPicker` composition. Change only static React Native presentation values and lock the approved proportions with the existing component tests; retain every 44pt interactive target and all existing callbacks and labels.

**Tech Stack:** React Native, Expo, TypeScript, Jest, Testing Library React Native.

---

### Task 1: Lock and implement the compact header proportions

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatHeader.test.tsx:8-27`
- Modify: `mobile/components/chat/__tests__/LlmModelPicker.test.tsx:51-68`
- Modify: `mobile/components/chat/ChatHeader.tsx:51-59`
- Modify: `mobile/components/chat/LlmModelPicker.tsx:82-92,274-280`

**Step 1: Write the failing tests**

Change the header contract to require a 24×24pt avatar and a 21pt / 26pt title. Change the header picker contract to require the exact 21pt / 26pt title and a 13pt chevron while retaining a minimum 44pt trigger target.

```tsx
expect(avatarStyle).toEqual(expect.objectContaining({ width: 24, height: 24 }));
expect(titleStyle).toEqual(expect.objectContaining({ fontSize: 21, lineHeight: 26 }));
expect(getByTestId('icon-chevron-down').props.size).toBe(13);
expect(triggerStyle.minHeight).toBeGreaterThanOrEqual(44);
```

**Step 2: Run the focused tests to verify RED**

Run:

```bash
cd mobile
npx jest components/chat/__tests__/ChatHeader.test.tsx components/chat/__tests__/LlmModelPicker.test.tsx --runInBand
```

Expected: FAIL because the current avatar is 30pt, title is 24pt / 30pt, and chevron is 15pt.

**Step 3: Implement the minimal presentation change**

Use `<XiaoBaAvatar size={24} />`, set the header title to `fontSize: 21` and `lineHeight: 26`, and set only the header chevron to `size={13}`. Do not change the header action group, 44pt button sizes, callbacks, model picker behavior, accessibility labels, colors, or data flow.

**Step 4: Run the focused tests to verify GREEN**

Run the same focused Jest command.

Expected: both suites PASS with no new warnings or errors.

**Step 5: Run proportional verification**

Run:

```bash
cd mobile
npx tsc --noEmit
npx eslint components/chat/ChatHeader.tsx components/chat/LlmModelPicker.tsx components/chat/__tests__/ChatHeader.test.tsx components/chat/__tests__/LlmModelPicker.test.tsx
```

Then run the project mobile integration gate and document-drift checks required by the active iOS 1.3.3 release dossier. Expected: all commands exit 0; baseline repository warnings may remain but no new warning or error is introduced.

**Step 6: Verify on device and update release evidence**

Build/install the superseding App Store candidate, visually confirm the compact header on the connected iPhone, rerun the safe real-device acceptance subset, and record only non-sensitive counts and candidate identifiers in `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`. Do not upload raw result bundles or use production OTA.

**Step 7: Commit and push exact files**

Stage only the files changed for this task plus the separately verified acceptance-harness correction already in progress. Use project commit conventions, push to `origin/main`, and require the exact pushed commit CI to be green before continuing App Store submission.
