# Mobile Chat Visual Hierarchy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rebalance the iOS chat screen so the top navigation is quieter, the in-conversation “小巴” identity is clearer, and the task strip and composer share one comfortable visual rhythm without shrinking message body text.

**Architecture:** Keep all chat state, props, navigation, accessibility labels, and data flow unchanged. Make surgical style and static icon-size changes inside the existing React Native components, using `revaTheme` and `StyleSheet.create`; protect each change with component-level visual-contract tests before implementation.

**Tech Stack:** React Native, Expo, TypeScript, Jest, Testing Library React Native, Expo Vector Icons, existing Reva design tokens.

---

### Task 1: Rebalance the chat header

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatHeader.test.tsx`
- Modify: `mobile/components/chat/ChatHeader.tsx:33-118`
- Modify: `mobile/components/chat/LlmModelPicker.tsx:64-88,204-286`

**Step 1: Write the failing header visual-contract test**

Replace the current display-scale assertions and extend the toolbar assertions:

```tsx
const avatarStyle = StyleSheet.flatten(getByLabelText('小巴形象').props.style);
const titleStyle = StyleSheet.flatten(getByText('小巴').props.style);
expect(avatarStyle).toEqual(expect.objectContaining({ width: 30, height: 30 }));
expect(titleStyle).toEqual(expect.objectContaining({ fontSize: 24, lineHeight: 30 }));

const groupStyle = StyleSheet.flatten(getByTestId('chat-header-action-group').props.style);
expect(groupStyle.minHeight).toBe(44);
expect(groupStyle.padding).toBe(2);
expect(StyleSheet.flatten(getByLabelText('新建对话').props.style)).toEqual(
  expect.objectContaining({ width: 44, height: 44, backgroundColor: 'transparent', borderWidth: 0 }),
);
expect(getByTestId('icon-pencil-outline').props.size).toBe(19);
expect(getByTestId('icon-time-outline').props.size).toBe(19);
expect(getByTestId('icon-settings-outline').props.size).toBe(19);
```

**Step 2: Run the focused test to verify RED**

Run:

```bash
cd mobile
npx jest components/chat/__tests__/ChatHeader.test.tsx --runInBand
```

Expected: FAIL because the current avatar/title are 32/28pt, toolbar padding is 3pt, and action buttons still have individual filled circles and borders.

**Step 3: Implement the minimal header changes**

- Render `XiaoBaAvatar` at 30pt.
- Use 19pt outline icons for the three primary actions.
- Keep each action at 44×44pt, but remove its individual fill and border.
- Use one 44pt-minimum, 2pt-padded outer toolbar with the existing warm paper fill and hairline border.
- Change the header-model title to 24pt / 30pt and its chevron to 15pt.
- Preserve every callback, label, hint, role, and model-picker behavior.

**Step 4: Run the focused test to verify GREEN**

Run the same Jest command. Expected: PASS with no warnings.

**Step 5: Commit the header slice**

```bash
git add mobile/components/chat/__tests__/ChatHeader.test.tsx \
  mobile/components/chat/ChatHeader.tsx \
  mobile/components/chat/LlmModelPicker.tsx
git commit -m "style(mobile): rebalance chat header"
```

### Task 2: Normalize the pending-task strip

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx`
- Modify: `mobile/components/chat/ChatTodayFocusCard.tsx:42-251`

**Step 1: Write the failing strip visual-contract test**

Add assertions to the caution-context case:

```tsx
const stripStyle = StyleSheet.flatten(getByTestId('chat-today-focus-card').props.style);
expect(stripStyle.minHeight).toBe(44);
expect(StyleSheet.flatten(getByText('待处理').props.style)).toEqual(
  expect.objectContaining({ fontSize: 14, lineHeight: 19 }),
);
expect(StyleSheet.flatten(getByText('复查血脂四项').props.style)).toEqual(
  expect.objectContaining({ fontSize: 15, lineHeight: 20 }),
);
```

Extend the dismiss test:

```tsx
expect(StyleSheet.flatten(dismissButton.props.style)).toEqual(
  expect.objectContaining({ width: 44, height: 44 }),
);
```

**Step 2: Run the focused test to verify RED**

```bash
cd mobile
npx jest components/chat/__tests__/ChatTodayFocusCard.test.tsx --runInBand
```

Expected: FAIL because the current context strip is 40pt high, the label/title scale is smaller, and the close control is 36×36pt.

**Step 3: Implement the minimal strip changes**

- Set context-strip minimum height to 44pt.
- Keep the 28pt semantic icon slot and existing 16pt icon.
- Set state label to 14pt / 19pt and task title to 15pt / 20pt.
- Make the dismiss control 44×44pt while leaving the close glyph compact.
- Preserve semantic colors, risk precedence, retry behavior, one-line truncation, and navigation.

**Step 4: Run the focused test to verify GREEN**

Run the same Jest command. Expected: PASS.

**Step 5: Commit the strip slice**

```bash
git add mobile/components/chat/__tests__/ChatTodayFocusCard.test.tsx \
  mobile/components/chat/ChatTodayFocusCard.tsx
git commit -m "style(mobile): clarify chat focus strip"
```

### Task 3: Promote the assistant identity without changing body text

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx:1888-1910,2011-2045`

**Step 1: Write the failing identity visual-contract test**

Extend the existing assistant-conclusion label test:

```tsx
const labelStyle = StyleSheet.flatten(getByText('小巴').props.style);
const dotStyle = StyleSheet.flatten(getByTestId('assistant-conclusion-dot').props.style);
const bodyStyle = StyleSheet.flatten(getByText('早餐已记录成功').props.style);

expect(labelStyle).toEqual(expect.objectContaining({
  fontSize: 16,
  lineHeight: 22,
  fontWeight: '700',
}));
expect(dotStyle).toEqual(expect.objectContaining({ width: 6, height: 6, borderRadius: 3 }));
expect(bodyStyle).toEqual(expect.objectContaining({ fontSize: 15, lineHeight: 23 }));
```

Use the fixture's actual conclusion text if it differs; the contract must assert both the promoted identity and the unchanged body scale.

**Step 2: Run the focused test to verify RED**

```bash
cd mobile
npx jest components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx --runInBand
```

Expected: FAIL because the current assistant label is 13pt / 18pt with a 4pt dot.

**Step 3: Implement the minimal identity changes**

- Set the assistant label to 16pt / 22pt, weight 700.
- Set the brand dot to 6×6pt with a 3pt radius.
- Set the conclusion container gap to 8pt.
- Leave conclusion/body text at 15pt / 23pt and do not add repeated avatars or identity rows elsewhere.

**Step 4: Run the focused test to verify GREEN**

Run the same Jest command. Expected: PASS.

**Step 5: Commit the identity slice**

```bash
git add mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  mobile/components/chat/ChatBubble.tsx
git commit -m "style(mobile): strengthen assistant identity"
```

### Task 4: Align the composer chrome

**Files:**
- Modify: `mobile/components/chat/__tests__/ChatInputBar.test.tsx`
- Modify: `mobile/components/chat/ChatInputBar.tsx:1175-1305,1402-1490`

**Step 1: Write the failing composer visual-contract test**

Extend the existing “visible composer chrome” test:

```tsx
const surface = StyleSheet.flatten(getByTestId('chat-composer-surface').props.style);
const input = StyleSheet.flatten(getByTestId('wechat-composer-input').props.style);
expect(surface.borderTopWidth).toBe(StyleSheet.hairlineWidth);
expect(input.borderRadius).toBe(14);
expect(input.minHeight).toBeGreaterThanOrEqual(48);

const textInput = getByPlaceholderText('问小巴，或点麦克风说话');
expect(StyleSheet.flatten(textInput.props.style)).toEqual(
  expect.objectContaining({ fontSize: 16 }),
);
```

Also retain the existing 40pt-visible-control plus hit-slop assertions so the lighter chrome does not reduce effective 44pt touch targets.

**Step 2: Run the focused test to verify RED**

```bash
cd mobile
npx jest components/chat/__tests__/ChatInputBar.test.tsx --runInBand
```

Expected: FAIL because the input currently uses an 8pt radius.

**Step 3: Implement the minimal composer changes**

- Change only the input surface radius to `revaRadii.md` (14pt).
- Normalize the bar's horizontal/vertical padding to existing 4pt-grid values if the focused screenshot comparison still shows uneven spacing.
- Preserve the 16pt input text, 48pt input surface, 40pt visible buttons plus hit slop, keyboard behavior, dictation states, send rules, and attachment flow.

**Step 4: Run the focused test to verify GREEN**

Run the same Jest command. Expected: PASS.

**Step 5: Commit the composer slice**

```bash
git add mobile/components/chat/__tests__/ChatInputBar.test.tsx \
  mobile/components/chat/ChatInputBar.tsx
git commit -m "style(mobile): align chat composer surface"
```

### Task 5: Run mobile regression and visual verification

**Files:**
- Modify only if evidence requires it: the files already listed above.

**Step 1: Run all related tests together**

```bash
cd mobile
npx jest \
  components/chat/__tests__/ChatHeader.test.tsx \
  components/chat/__tests__/ChatTodayFocusCard.test.tsx \
  components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx \
  components/chat/__tests__/ChatInputBar.test.tsx \
  app/\(tabs\)/__tests__/chat.test.tsx \
  --runInBand
```

Expected: all suites PASS, no new warnings.

**Step 2: Run the complete local mobile gate**

```bash
bash scripts/mobile-fast-test.sh --all
cd mobile
npm run design:check
```

Expected: Jest, ESLint, TypeScript, diff check, and design-token gate all exit 0. Do not pipe output through `tail`.

**Step 3: Verify on the connected iPhone**

- Install/run the candidate through the existing local iOS development workflow.
- Compare the real screen at default Dynamic Type and one larger setting.
- Exercise: new chat, history, settings, pending-task open/dismiss, long assistant reply, structured conclusion, inline card, keyboard open/close, voice/text toggle, attachment menu, and scroll-to-latest.
- Capture a new screenshot proving that the top title is quieter, toolbar icons remain legible, conversation “小巴” is prominent, body text is unchanged, and the composer does not cover content.

Expected: no overlap, clipping, missed tap target, keyboard regression, or scroll jump.

### Task 6: Record release evidence and resume the App Store gate

**Files:**
- Modify: `docs/dossiers/2026-08-05-ios-1-3-3-app-store-release.md`
- Modify if required by existing release tooling: `docs/release/app-store/submission-pack.md`

**Step 1: Update the release dossier**

Record the approved design document, UI commits, focused/full mobile verification evidence, connected-device screenshot path, and G3 result. Do not mark G5/G6 complete before deployment and live verification.

**Step 2: Validate release documentation**

```bash
PATH="$PWD/backend/venv/bin:$PATH" pre-commit run --all-files
python3 scripts/check_app_store_release_pack.py
python3 scripts/check_ios_app_store_submission.py
```

Expected: all checks exit 0.

**Step 3: Push and wait for authoritative CI**

Push only after the worktree is clean and local gates are green. Inspect every failing GitHub Actions job directly; do not deploy or attach an App Store build while any required job is red.

**Step 4: Continue the existing release sequence**

After CI is green, continue the repository's iOS 1.3.3 release dossier at G5/G6: deploy required backend/web changes, verify production SHA and health, build the next native iOS candidate, install and smoke-test it, then attach it in App Store Connect. Keep App Store release control manual and do not submit for review until all metadata, privacy, review-account access, and device smoke checks are green.
