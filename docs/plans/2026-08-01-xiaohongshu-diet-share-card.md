# Xiaohongshu Diet Share Card Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace direct screenshots of the operational chat diet card with a photo-required, locally editable, privacy-safe `1080x1440` Xiaohongshu poster.

**Architecture:** Keep the confirmed `DietRecord` and its owner-scoped photo as the source of truth. Adapt verified chat cards into that contract, materialize the protected photo locally, apply non-destructive crop/rotation metadata, render opaque privacy strokes into the dedicated poster, capture the poster once, and reuse that exact PNG for preview, save and system sharing.

**Tech Stack:** React Native, Expo 55, TypeScript, `expo-image-manipulator`, `react-native-gesture-handler`, Reanimated, `react-native-svg`, `react-native-view-shot`, Expo Media Library/Sharing, Jest and React Native Testing Library.

---

## Execution preflight

- Execute from a clean branch/worktree based on the current `origin/main`; the present primary workspace contains unrelated unstaged files and must not be swept into any commit.
- Preserve the approved design in `docs/plans/2026-08-01-xiaohongshu-diet-share-card-design.md`.
- Before editing `docs/dossiers/2026-07-11-diet-capture-excellence.md`, resolve ownership of its existing unstaged change. Never stage another session's hunk.
- Use TDD for every behavioral change. Run the named RED command and observe the expected failure before implementation.
- Stage exact files only; never use `git add -A`.

### Task 1: Align the active product contract

**Files:**

- Modify: `docs/specs/active/2026-07-11-diet-capture-excellence.md`
- Modify: `docs/dossiers/2026-07-11-diet-capture-excellence.md`
- Reference: `docs/plans/2026-08-01-xiaohongshu-diet-share-card-design.md`

**Step 1: Update the feature contract**

Replace the acceptance criterion that permits a photo timeout to produce a metric-only sharing image with:

```gherkin
Given a confirmed meal has an owner-accessible photo
When the user opens the Xiaohongshu share composer
Then the original meal photo is loaded into a local 3:4 editor before poster preview

Given the meal photo is absent or cannot be loaded
When the user requests an image share
Then no image poster is generated and the UI offers retry or share text

Given the user adds a privacy-redaction stroke
When the 1080x1440 PNG is generated
Then the exported pixels contain the opaque redaction and the original DietRecord photo is unchanged
```

Add crop, rotation, full preview, one-rendered-URI reuse and no automatic QR/barcode detection to the Mobile surface contract and non-goals.

**Step 2: Update the dossier before code**

Add a dated correction block that links the approved design, records the privacy-sensitive gate, and states that the prior metric-only fallback is superseded for the Xiaohongshu flow.

**Step 3: Verify documentation consistency**

Run:

```bash
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
git diff --check
```

Expected: all commands exit `0`.

**Step 4: Commit only the contract files**

```bash
git add docs/specs/active/2026-07-11-diet-capture-excellence.md docs/dossiers/2026-07-11-diet-capture-excellence.md
git commit -m "docs(diet): specify editable Xiaohongshu share poster"
```

### Task 2: Add deterministic share presentation and chat-card adaptation

**Files:**

- Create: `mobile/components/diet/dietSharePresentation.ts`
- Create: `mobile/components/diet/__tests__/dietSharePresentation.test.ts`
- Modify: `mobile/components/chat/cards/DietDraftCard.tsx`

**Step 1: Write failing presentation tests**

Cover these cases:

```ts
it('builds approximate nutrition copy without confidence percentages', () => {
  const view = buildDietSharePresentation(photoRecord({
    calories: 900, protein: 36, carbs: 103, fat: 42, ai_confidence: 0.88,
  }));
  expect(view.macroLines).toEqual([
    '约 900 kcal · 蛋白质 36g',
    '碳水 103g · 脂肪 42g',
  ]);
  expect(JSON.stringify(view)).not.toContain('88%');
});

it('hides exact nutrition for a low-confidence photo record', () => {
  const view = buildDietSharePresentation(photoRecord({ ai_confidence: 0.42 }));
  expect(view.macroLines).toEqual(['营养待核对']);
});

it('adapts only a verified recorded chat card with a photo', () => {
  expect(buildChatDietShareInput(cardData, verifiedReceipt)).toMatchObject({
    available: true,
    record: { id: 705, meal_type: 'breakfast' },
  });
});
```

The adapter must accept a typed plain-object boundary rather than importing the whole ChatBubble.

**Step 2: Run the tests to verify RED**

Run:

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/dietSharePresentation.test.ts --runInBand
```

Expected: FAIL because the presentation module does not exist.

**Step 3: Implement the minimal pure contract**

Create these public types/functions:

```ts
export type DietSharePresentation = {
  mealLabel: string;
  headline: string;
  foodLine: string;
  macroLines: string[];
  tags: string[];
  nextAction?: string;
  disclosure: string;
};

export type ChatDietShareInput =
  | { available: true; record: DietRecord; photoUri: string }
  | { available: false; reason: 'unverified' | 'photo_missing' | 'record_missing' };

export function buildDietSharePresentation(record: DietRecord): DietSharePresentation;
export function buildChatDietShareInput(
  cardData: Record<string, unknown>,
  receipt?: { status?: string; resourceType?: string; resourceId?: string } | null,
): ChatDietShareInput;
```

Export the existing private photo-URI normalization from `DietDraftCard.tsx` or move it into the new module so the rendered card and share adapter use one rule. Do not duplicate URL trust logic.

**Step 4: Run focused tests to verify GREEN**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/dietSharePresentation.test.ts components/chat/cards/__tests__/DietDraftCard.test.tsx --runInBand
```

Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/components/diet/dietSharePresentation.ts mobile/components/diet/__tests__/dietSharePresentation.test.ts mobile/components/chat/cards/DietDraftCard.tsx
git commit -m "feat(diet): define share poster presentation contract"
```

### Task 3: Add non-destructive image edit state and local photo preparation

**Files:**

- Create: `mobile/components/diet/dietShareImageEdit.ts`
- Create: `mobile/components/diet/__tests__/dietShareImageEdit.test.ts`
- Modify: `mobile/utils/share.ts`
- Modify: `mobile/utils/__tests__/share.test.ts`

**Step 1: Write failing pure-state tests**

```ts
it('keeps crop and privacy points normalized', () => {
  const state = addDietShareRedaction(initialDietShareImageEdit(), {
    points: [{ x: -0.1, y: 0.4 }, { x: 1.2, y: 0.8 }],
    width: 0.06,
  });
  expect(state.redactions[0].points).toEqual([
    { x: 0, y: 0.4 }, { x: 1, y: 0.8 },
  ]);
});

it('rotates in 90 degree increments and reset restores identity', () => {
  expect(rotateDietShareImage(initialDietShareImageEdit()).rotation).toBe(90);
  expect(resetDietShareImageEdit()).toEqual(initialDietShareImageEdit());
});
```

Add share utility tests proving a protected HTTPS photo is downloaded with auth headers and its temporary file is deleted by the returned cleanup callback. Never log the URI.

**Step 2: Run tests to verify RED**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/dietShareImageEdit.test.ts utils/__tests__/share.test.ts --runInBand
```

Expected: FAIL on missing edit functions/local-materialization helper.

**Step 3: Implement the state and materialization API**

```ts
export type NormalizedPoint = { x: number; y: number };
export type DietShareRedaction = { points: NormalizedPoint[]; width: number };
export type DietShareImageEdit = {
  crop: { x: number; y: number; width: number; height: number };
  rotation: 0 | 90 | 180 | 270;
  redactions: DietShareRedaction[];
};

export async function materializeImageForLocalUse(
  uri: string,
  options?: { headers?: Record<string, string>; cacheKey?: string },
): Promise<{ uri: string; cleanup: () => Promise<void> }>;
```

Use `FileSystem.downloadAsync` for protected HTTPS sources and return the original URI with a no-op cleanup for local files. Clamp every normalized coordinate to `[0, 1]` and reject empty strokes. Do not persist the edit state.

**Step 4: Verify GREEN**

Run the same command from Step 2. Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/components/diet/dietShareImageEdit.ts mobile/components/diet/__tests__/dietShareImageEdit.test.ts mobile/utils/share.ts mobile/utils/__tests__/share.test.ts
git commit -m "feat(diet): add local share image edit state"
```

### Task 4: Build the local crop, rotation and privacy editor

**Files:**

- Create: `mobile/components/diet/DietShareImageEditor.tsx`
- Create: `mobile/components/diet/__tests__/DietShareImageEditor.test.tsx`

**Step 1: Write failing component tests**

Test the required controls and contract:

```ts
it('shows the public-sharing privacy reminder and completes with edit metadata', () => {
  const onComplete = jest.fn();
  const screen = render(<DietShareImageEditor source={{ uri }} onCancel={jest.fn()} onComplete={onComplete} />);
  expect(screen.getByText('公开分享前，请检查人脸、地址、条码和二维码。')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('顺时针旋转照片'));
  fireEvent.press(screen.getByLabelText('完成图片编辑'));
  expect(onComplete).toHaveBeenCalledWith(expect.objectContaining({ rotation: 90 }));
});

it('reset removes crop, rotation and privacy strokes', () => { /* assert identity state */ });
it('cancel asks before discarding a changed edit', () => { /* assert Alert contract */ });
```

**Step 2: Run the tests to verify RED**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/DietShareImageEditor.test.tsx --runInBand
```

Expected: FAIL because the editor component does not exist.

**Step 3: Implement the editor**

Use a full-screen `Modal`/safe area and an explicit state machine:

```ts
type EditorPhase = 'loading' | 'ready' | 'applying' | 'failed';
```

- Gesture Handler/Reanimated: pinch zoom and drag constrained to the 3:4 crop viewport.
- Toolbar: rotate, privacy brush, undo, redo and reset.
- Privacy strokes: normalized points rendered with a fully opaque round stroke; the UI label is `隐私涂抹`, not automatic detection.
- Complete: translate the viewport into a crop rect, run `expo-image-manipulator` for crop/rotation, and return `{ editedUri, redactions, cleanup }`.
- If the native manipulator is unavailable, show an explicit `当前版本暂不支持图片编辑` state and preserve the original photo; do not claim completion.

**Step 4: Verify GREEN and type safety**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/DietShareImageEditor.test.tsx components/diet/__tests__/dietShareImageEdit.test.ts --runInBand
npx tsc --noEmit
```

Expected: PASS and TypeScript exit `0`.

**Step 5: Commit**

```bash
git add mobile/components/diet/DietShareImageEditor.tsx mobile/components/diet/__tests__/DietShareImageEditor.test.tsx
git commit -m "feat(diet): add private local share image editor"
```

### Task 5: Redesign the dedicated poster renderer

**Files:**

- Modify: `mobile/components/diet/DietShareCard.tsx`
- Modify: `mobile/components/diet/__tests__/DietShareCard.test.tsx`
- Create: `mobile/components/diet/DietPrivacyRedactionOverlay.tsx`
- Create: `mobile/components/diet/__tests__/DietPrivacyRedactionOverlay.test.tsx`

**Step 1: Replace old visual assertions with failing approved-design tests**

Assert that a normal photo-backed poster contains the photo, meal headline, compact approximate macro rows, one next action and estimate disclosure. Assert it does not contain:

```ts
['数据库已保存', '来源：', '识别置信度', '均衡度', '可直接分享至微信 / 小红书', '小巴生成']
```

Add a test that low-confidence content renders `营养待核对` and no exact calories/macros. Add an overlay test where a normalized stroke becomes an SVG path with `strokeOpacity={1}`.

**Step 2: Run tests to verify RED**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/DietShareCard.test.tsx components/diet/__tests__/DietPrivacyRedactionOverlay.test.tsx --runInBand
```

Expected: FAIL because the old report-style sections remain and no redaction overlay exists.

**Step 3: Implement the cream lifestyle poster**

- Consume `buildDietSharePresentation(record)` as the only copy builder.
- Require `imageSource`; remove `forceImageFallback` from the Xiaohongshu poster path.
- Make the photo approximately 55% of the card.
- Render two compact macro lines, up to three tags and one next action.
- Render `DietPrivacyRedactionOverlay` immediately above the photo so `react-native-view-shot` bakes it into the PNG.
- Retain exact capture sizing through `dietShareCaptureDimensions()`.
- Remove the oversized calorie hero, balance score, confidence panel, source panel, lifestyle disclaimer panel and unlabeled macro bar from this poster variant.

**Step 4: Verify GREEN**

Run the same focused tests. Expected: PASS.

**Step 5: Commit**

```bash
git add mobile/components/diet/DietShareCard.tsx mobile/components/diet/__tests__/DietShareCard.test.tsx mobile/components/diet/DietPrivacyRedactionOverlay.tsx mobile/components/diet/__tests__/DietPrivacyRedactionOverlay.test.tsx
git commit -m "feat(diet): redesign Xiaohongshu meal poster"
```

### Task 6: Add the one-render composer and integrate chat

**Files:**

- Create: `mobile/components/diet/DietShareComposer.tsx`
- Create: `mobile/components/diet/__tests__/DietShareComposer.test.tsx`
- Modify: `mobile/components/chat/ChatBubble.tsx`
- Modify: `mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx`
- Modify: `mobile/app/diet.tsx`

**Step 1: Write failing composer and chat tests**

Cover:

```ts
it('captures once and reuses the same PNG for preview, save and share', async () => {
  // Complete editing, expect one captureRef call.
  // Save and share, expect both to receive the same captured URI.
});

it('treats a dismissed system share as cancellation without an error toast', async () => { /* no failure */ });
it('never renders a poster when the protected photo cannot load', async () => { /* retry/text only */ });
it('opens the composer instead of capturing the operational chat card', async () => { /* no ChatBubble captureRef */ });
```

Change the chat expectation from three buttons to `编辑分享图` and `分享正文`. Keep unverified drafts non-shareable.

**Step 2: Run tests to verify RED**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/DietShareComposer.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx --runInBand
```

Expected: FAIL because the composer is missing and ChatBubble still captures its operational frame.

**Step 3: Implement the composer state machine**

```ts
type ComposerPhase =
  | 'loading_photo'
  | 'editing'
  | 'rendering'
  | 'preview'
  | 'failed';
```

- Materialize the authenticated photo locally.
- Open `DietShareImageEditor` first.
- After completion, render the fixed poster once with `captureRef` and retain the resulting URI until composer close.
- Preview the captured PNG itself, not a second live render.
- `保存到相册` and `分享` both consume the retained URI.
- Move saving out of ChatBubble.
- On close, release the capture and materialized photo exactly once.
- Preserve `分享正文` as a separate text path.

In `ChatBubble.tsx`, remove `captureRef`, `cardFrameRef`, `handleSaveCardScreenshot` and `handleShareCardImage`. Build `ChatDietShareInput` only for verified `diet_draft` cards. Use `buildChatImageSource`/auth headers at the boundary and open `DietShareComposer` from `编辑分享图`. Other card types keep their existing text-share behavior.

In `mobile/app/diet.tsx`, replace the current `DietShareSheet` use with the same composer so diet history and chat do not drift.

**Step 4: Verify GREEN**

```bash
cd mobile
npx jest --runTestsByPath components/diet/__tests__/DietShareComposer.test.tsx components/diet/__tests__/DietShareCard.test.tsx components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx app/__tests__/dietCapture.test.tsx --runInBand
npx tsc --noEmit
```

Expected: PASS and no ChatBubble card-frame capture call.

**Step 5: Commit**

```bash
git add mobile/components/diet/DietShareComposer.tsx mobile/components/diet/__tests__/DietShareComposer.test.tsx mobile/components/chat/ChatBubble.tsx mobile/components/chat/__tests__/ChatBubbleStructuredSummary.test.tsx mobile/app/diet.tsx
git commit -m "feat(chat): use editable diet share composer"
```

### Task 7: Lock telemetry privacy, run release gates and document evidence

**Files:**

- Modify: `mobile/services/clientEvents.ts`
- Modify: `mobile/services/__tests__/clientEvents.test.ts`
- Modify if the event schema changes: `backend/app/api/client_events.py`
- Modify if the event schema changes: `backend/tests/test_client_events.py`
- Modify: `docs/dossiers/2026-07-11-diet-capture-excellence.md`

**Step 1: Write failing telemetry tests**

Ensure only bounded metadata survives:

```ts
expect(sanitizeClientEventMeta('diet_share_terminal', {
  phase: 'completed',
  duration_ms: 1200,
  has_photo: true,
  share_target: 'xiaohongshu',
  image_uri: 'file:///private/photo.png',
  food_items: 'private meal',
})).toEqual({
  phase: 'completed',
  duration_ms: 1200,
  has_photo: true,
  share_target: 'xiaohongshu',
});
```

Keep the existing backend allowlist unchanged unless a genuinely necessary bounded phase/error field is missing.

**Step 2: Run RED/GREEN focused telemetry verification**

```bash
cd mobile
npx jest --runTestsByPath services/__tests__/clientEvents.test.ts --runInBand
cd ..
DATABASE_URL=sqlite:///:memory: PYTHONPATH=backend backend/venv/bin/pytest backend/tests/test_client_events.py backend/tests/test_observability_client_events.py -q
```

Expected: Mobile and backend tests PASS; no image URI, record ID, food name or nutrition value is accepted.

**Step 3: Run the complete Mobile gate**

```bash
cd mobile
npm test -- --runInBand
npx tsc --noEmit
npx expo lint --quiet
npm run design:check
cd ..
git diff --check
python3 scripts/check_doc_drift.py
python3 backend/scripts/check_dossier_consistency.py
```

Expected: every command exits `0`. Do not pipe test output through `tail`.

**Step 4: Perform device-level visual verification**

Verify on `390x844` and `430x932` layouts:

- the photo remains the dominant element;
- crop/zoom/rotation are usable;
- the privacy stroke is visible in the final saved PNG;
- the final file is exactly `1080x1440`;
- preview, saved photo and shared photo are byte-identical or use the same retained file URI;
- photo failure never produces a metric-only image;
- screen-reader labels and touch targets remain usable.

Record screenshots and results in the dossier without committing private meal photos.

**Step 5: Commit verification evidence**

```bash
git add mobile/services/clientEvents.ts mobile/services/__tests__/clientEvents.test.ts docs/dossiers/2026-07-11-diet-capture-excellence.md
git commit -m "test(diet): verify private share composer delivery"
```

If the backend schema did not change, do not stage backend files.

## Delivery gate

After all local gates pass, follow `requesting-code-review`, `verification-before-completion`, `finishing-a-development-branch` and the project's Mobile OTA binding. Do not publish an OTA until main CI is green. Because this plan intentionally uses only already-bundled native modules, it should be OTA-compatible; if implementation introduces any new native dependency or app configuration, stop and reclassify the release as a native build.
