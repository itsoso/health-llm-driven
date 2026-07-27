# Reva App Icon Light Palette Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Reva's dark app icon palette with the approved soft-mint palette while preserving the existing ECG and AI-sparkle identity across iOS, Android, and splash assets.

**Architecture:** Keep `mobile/assets/images/icon.png` as the canonical 1024 px artwork. Use the same approved artwork for Android adaptive foreground and derive the 512 px splash image from it, then align the splash background color in Expo configuration. Add an asset contract test so future releases cannot silently reintroduce mismatched dimensions, transparency, or dark backgrounds.

**Tech Stack:** Expo 55, React Native, Jest, PNG assets, Node image inspection.

---

### Task 1: Add the app icon asset contract

**Files:**
- Create: `mobile/__tests__/app-icon-assets.test.ts`
- Modify: `mobile/package.json`

**Step 1: Write the failing test**

Add a focused Jest test that reads the three configured PNG assets and verifies:

- canonical and adaptive icons are 1024 x 1024;
- splash artwork is 512 x 512;
- the files are PNG images;
- `icon.png` and `adaptive-icon.png` are byte-identical;
- `app.json` references these exact paths;
- the splash background is `#DDEFE8`.

**Step 2: Run the test to verify it fails**

Run:

```bash
cd mobile
npx jest __tests__/app-icon-assets.test.ts --runInBand
```

Expected: FAIL because the current splash background is `#0A8F8F`.

**Step 3: Keep implementation scope minimal**

Do not add a new image dependency. Parse the PNG header directly with Node
`Buffer` because the contract only needs format and dimensions.

### Task 2: Generate the approved light artwork

**Files:**
- Modify: `mobile/assets/images/icon.png`
- Modify: `mobile/assets/images/adaptive-icon.png`
- Modify: `mobile/assets/images/splash-icon.png`

**Step 1: Edit the canonical artwork**

Use the existing 1024 px icon as the edit reference and preserve:

- ECG waveform geometry;
- three AI sparkles;
- data points;
- subtle square grid;
- centered composition and safe margins.

Apply:

- soft mint background near `#DDEFE8`;
- calm Reva green waveform near `#167A62`;
- brighter mint sparkles;
- low-contrast grid;
- no gradient, text, transparency, glow, or added symbols.

**Step 2: Synchronize platform assets**

Copy the approved 1024 px artwork to `adaptive-icon.png`. Produce the 512 px
`splash-icon.png` from the same artwork with high-quality downsampling.

**Step 3: Inspect at launcher sizes**

Render previews at 180 px, 60 px, and 29 px. Confirm the waveform remains
recognizable and the grid does not create visual noise.

### Task 3: Align Expo splash configuration

**Files:**
- Modify: `mobile/app.json`

**Step 1: Apply the palette**

Set:

```json
"backgroundColor": "#DDEFE8"
```

Keep all asset paths unchanged.

**Step 2: Run the focused tests**

Run:

```bash
cd mobile
npx jest __tests__/app-icon-assets.test.ts __tests__/app-config.test.ts --runInBand
```

Expected: PASS.

### Task 4: Verify release compatibility and commit

**Files:**
- Verify: `mobile/assets/images/icon.png`
- Verify: `mobile/assets/images/adaptive-icon.png`
- Verify: `mobile/assets/images/splash-icon.png`
- Verify: `mobile/app.json`
- Verify: `mobile/__tests__/app-icon-assets.test.ts`

**Step 1: Run App Store configuration checks**

Run:

```bash
python3 scripts/check_ios_app_store_submission.py
```

Expected: configuration checks pass or only report pre-existing human App Store
submission blockers unrelated to the icon.

**Step 2: Review the final diff**

Confirm no unrelated files are staged and no existing user work is modified.

**Step 3: Commit**

```bash
git add \
  mobile/assets/images/icon.png \
  mobile/assets/images/adaptive-icon.png \
  mobile/assets/images/splash-icon.png \
  mobile/app.json \
  mobile/__tests__/app-icon-assets.test.ts \
  docs/plans/2026-07-27-app-icon-light-palette.md
git commit -m "style(mobile): lighten Reva app icon palette"
```

**Step 4: Push main**

```bash
git push origin main
```

The home-screen icon requires the next native TestFlight/App Store build; do
not publish it as an OTA-only update.
