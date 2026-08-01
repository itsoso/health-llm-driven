# 小红书饮食分享卡设计

> Status: approved
> Date: 2026-08-01
> Surface: Mobile
> Related spec: `docs/specs/active/2026-07-11-diet-capture-excellence.md`

## 1. 背景与问题

聊天内已确认的饮食卡目前直接通过 `react-native-view-shot` 截图分享。该卡同时承担记录确认、写入回执、可信度解释、修正提示和分享入口，导致分享图混入“已保存到今日饮食”“来源：对话/图片”“可在记录页继续修正”等仅适合本人操作的系统信息。照片、900 kcal、宏量营养条、状态提示和下一步建议同时争夺注意力，产物更像业务记录截图，而不是适合小红书的生活方式海报。

项目已经存在固定 3:4 的 `DietShareCard`，但聊天内分享没有复用独立分享渲染面，而是截取 `DietDraftCard`。本设计将聊天业务卡与公开分享海报分离，并为分享照片增加非破坏式基础编辑。

## 2. 需求准入

```yaml
RequirementAdmission:
  request: 将已确认饮食记录生成可编辑照片的小红书分享海报
  classification: product_change
  first_user_fit: 使用 Mobile 拍照记录饮食并需要公开分享的用户
  core_loop_step: Capture -> Confirm -> ExecutionEvent -> Review/Export
  first_class_objects: [WriteIntent, ExecutionEvent]
  target_surface: Mobile
  source_of_truth: confirmed DietRecord plus its owner-scoped meal photo
  safety_level: privacy_sensitive
  prescription_or_causal_verdict: none
  autonomy_tier: manual_confirm
  evidence_provenance: confirmed food labels plus explicitly hedged nutrition estimates
  claim_hedging: image-derived nutrition always remains an estimate
  verification_window: immediate preview, save and share terminal result
  success_metric: photo-backed poster generation success and zero blank/private-data-by-default exports
  added_user_burden: one optional edit step before public sharing
  burden_justification: lets the user crop the meal and redact visible private information before export
  non_goals: [social feed, automatic posting, vanity streaks, filters, stickers, automatic barcode detection]
  smallest_end_to_end_slice: confirmed chat meal with photo -> local edit -> 1080x1440 preview -> save or system share
  stale_surface_to_remove_or_archive: direct screenshot sharing of the in-chat DietDraftCard
  spec_required: yes
```

Gate result: accepted. The feature remains an explicit export of an existing confirmed `ExecutionEvent`, not a new engagement feed. Mobile owns editing and rendering; the confirmed diet record remains the source of truth. The safety boundary is privacy-sensitive because the user-provided photograph can contain faces, addresses, barcodes or QR codes.

## 3. Evaluated directions

### 3.1 Cream lifestyle poster — selected

The meal photo leads, a short human headline provides context, and nutrition becomes a compact secondary layer. This is closest to native Xiaohongshu content and avoids presenting the meal as a clinical report.

### 3.2 Professional nutrition report

This direction emphasizes calories, macro ratios and balance. It is useful for self-review but too dense and evaluative for the primary sharing goal.

### 3.3 Streak or achievement poster

This direction can create a stronger social hook, but it depends on reliable history and risks optimizing vanity streaks rather than the Health OS loop. It is out of scope for the first version.

## 4. Product principles

1. The share image is a separate artifact, never a screenshot of the operational chat card.
2. A Xiaohongshu diet poster must contain the user-selected meal photo. No-photo metric posters are not generated in this flow.
3. The original meal photo and confirmed DietRecord are never overwritten by share edits.
4. Public sharing is always manually confirmed through a full preview and the iOS system share sheet.
5. Image-derived nutrition is an estimate even after the user confirms the record.
6. The card avoids shame, diagnosis, unsupported target claims and internal system language.
7. Image editing and poster rendering happen locally; no additional image is uploaded for editing.

## 5. Visual design

The output is a fixed `1080x1440` PNG with a cream lifestyle treatment:

- background: warm cream;
- primary accents: muted healthy green and warm orange only;
- photo: about 55% of the poster and the dominant visual element;
- typography: one lifestyle headline, one compact nutrition row, one restrained next-step line;
- brand: a small `小巴` signature in the lower-right corner;
- no buttons, receipts, correction instructions or sharing instructions inside the image.

```text
┌────────────────────────────┐
│ 小巴 · 今日饮食     早餐    │
│                            │
│       餐食照片约占 55%      │
│                            │
├────────────────────────────┤
│ 今天的早餐，能量很足         │
│ 猪柳蛋麦满分 · 油条 · 豆乳   │
│                            │
│ 约 900 kcal · 蛋白质 36g    │
│ 碳水 103g · 脂肪 42g        │
│                            │
│ 下一餐可以补一份蔬菜         │
│                            │
│ 营养由图片估算        小巴 ✦ │
└────────────────────────────┘
```

Calories no longer use an oversized hero treatment. An unlabeled multicolor macro bar is removed. The food photo and meal story lead; data supports rather than dominates.

## 6. Content and trust rules

The poster may show:

- meal type and date;
- user-confirmed food names;
- estimated calories, protein, carbohydrate and fat;
- at most three deterministic descriptive tags;
- one hedged next-meal suggestion;
- a compact estimate disclosure and brand signature.

The poster must not show:

- write receipts or persistence state;
- confidence percentages;
- internal source labels such as conversation/image;
- record IDs, user IDs or internal URLs;
- body weight, diagnoses, medication, genetics or unrelated health context;
- editing or navigation instructions;
- unsupported labels such as “protein target met”.

Rules:

- Vision-derived values use approximate language such as `约 900 kcal`.
- User-facing numbers follow `format_display_number` semantics: at most two decimal places with trailing zeros removed; poster macros prefer integers where the underlying precision does not justify decimals.
- Low-confidence records hide exact calories and macros and show `营养待核对`; the user must correct the record before an exact-data poster becomes available.
- Tags are deterministic and limited to three. A target-relative claim requires a real user target; otherwise the card uses factual wording.
- Advice uses `可以考虑` or `下一餐可以` and never diagnoses, prescribes or shames.

## 7. Image editor

Tapping `编辑分享图` opens a full-screen local editor with a fixed 3:4 safe-area preview.

First-version controls:

- pinch zoom and drag to crop;
- 90-degree rotation;
- undo and redo;
- reset to original;
- a manual privacy-redaction brush;
- cancel and complete.

The editor shows: `公开分享前，请检查人脸、地址、条码和二维码。`

Automatic barcode or QR detection is not part of the first version. The current app has no local detector dependency, and adding one would broaden native release scope. Manual redaction is explicit, local and predictable. The redaction layer must be opaque in the final bitmap; it cannot merely blur the preview while leaving original pixels recoverable in the exported file.

Edit state is non-destructive and local:

```ts
type DietShareImageEdit = {
  crop: { x: number; y: number; width: number; height: number };
  rotation: 0 | 90 | 180 | 270;
  redactions: Array<{ points: Array<{ x: number; y: number }>; width: number }>;
};
```

Crop and redaction coordinates are normalized to the displayed image so the same edit renders consistently in preview and the `1080x1440` export. The first version keeps edits for the current composer session only. Closing without completing discards them after confirmation.

## 8. Interaction flow

```text
confirmed chat diet card
  -> 编辑分享图
  -> authenticated local meal photo is ready
  -> crop / zoom / rotate / redact
  -> generate 1080x1440 poster
  -> full preview
  -> 保存到相册 | 分享
  -> terminal success, cancellation or actionable failure
```

The chat card exposes two actions:

- primary: `编辑分享图`;
- secondary: `分享正文`.

`保存图片` moves into the poster preview so three similar actions do not compete under the chat card. Saving and sharing use the exact same rendered PNG. The system share sheet remains the only publishing surface; the app does not bind a Xiaohongshu private SDK or post automatically.

If the record has no accessible photo, `编辑分享图` is disabled with an explanation and `分享正文` remains available. This intentionally replaces the prior no-photo metric fallback for this Xiaohongshu flow.

## 9. Architecture and data flow

The chat surface must stop capturing its rendered `DietDraftCard`. Instead it adapts a verified diet card and its write receipt into a share-composer input:

```text
DietDraftCard data + verified DietRecord identity
  -> owner-scoped image source
  -> DietShareComposer
  -> local ImageEdit state
  -> dedicated DietShareCard render
  -> react-native-view-shot PNG
  -> photo library or system share sheet
```

Implementation should reuse and narrow the existing `DietShareCard` rather than build a second poster renderer. `expo-image-manipulator` handles physical crop/rotation where available. Gesture Handler and Reanimated provide editor interaction. A captured SVG/React Native redaction overlay makes privacy strokes part of the exported bitmap. Existing old-binary fallback must fail explicitly to original-photo preview or disable unsupported edit controls; it must not pretend an edit was applied.

No backend schema or write path changes are required. Share events may record only bounded action metadata such as `opened`, `edited`, `saved`, `shared`, `cancelled` or `failed`, plus a coarse error code. Logs and telemetry must not contain image URIs, food names, nutrition values, record IDs or free text.

## 10. Error and cancellation behavior

- Photo authentication or download failure: keep the composer closed or in a retryable photo-loading state; do not render a blank poster.
- Edit operation failure: preserve the previous successful preview and report which action failed.
- Render failure: show `分享图生成失败` with `重试` and `取消`.
- Photo-library denial: explain how to enable add-photo permission without claiming the image was saved.
- System share cancellation: treat as normal cancellation and show no error toast.
- Share-sheet failure: preserve the generated PNG so the user can retry or save it.
- Temporary files: delete after terminal completion or composer cleanup; cleanup failure may be logged without sensitive paths and must not change the user-visible share result.

## 11. Verification

Unit and component coverage must prove:

- only verified diet cards with an accessible photo enter the image composer;
- chat sharing no longer captures the operational `DietDraftCard`;
- crop, rotation, normalized redaction and reset state are deterministic;
- redaction pixels are present in the exported bitmap, not only the preview;
- preview and saved/shared image use the same output URI;
- low-confidence records do not expose exact macros;
- user corrections are reflected in the poster;
- no-photo and failed-photo states never generate blank metric posters;
- cancel is distinct from failure;
- temporary artifacts are cleaned up;
- no sensitive values enter telemetry;
- `390x844` and `430x932` devices can complete editing without obscured controls;
- the output is exactly `1080x1440`.

Focused verification should include the relevant ChatBubble, DietShareCard, share utility and editor tests, Mobile TypeScript, Expo lint and a simulator screenshot comparison. Because the first slice uses existing native dependencies and changes only JS/TS/UI, it remains eligible for the production OTA path after CI and device verification.

## 12. Non-goals

- Automatic QR, barcode, face or address detection.
- Filters, stickers, arbitrary text overlays or templates.
- Direct Xiaohongshu publishing SDK integration.
- Automatic posting or background sharing.
- Server-side image editing or storage of edited share copies.
- New nutrition inference, medical advice or diet scoring.
- Social feeds, follower graphs or vanity streak mechanics.

## 13. Rollout and rollback

The smallest release replaces direct chat-card image capture with the photo-required composer for verified diet records. The existing `分享正文` path remains the fallback. Rollback restores the prior chat share action without changing DietRecord data or server contracts. Release requires Mobile tests, TypeScript, lint, CI, production OTA publication and a real-device check that crop, redaction, save and system share all use the same image.
