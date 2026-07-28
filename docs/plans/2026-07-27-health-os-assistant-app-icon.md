# Reva Health OS Assistant App Icon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship an App Store-ready “Life Core” icon that combines personal health, a trusted assistant, and the Reva Health OS.

**Architecture:** Generate one flat, opaque 1024 px master artwork from the approved design, validate it visually at launcher sizes, then derive the Android and splash assets from that single source. Keep Expo configuration unchanged except where tests prove an asset mismatch.

**Tech Stack:** Built-in image generation, macOS `sips`, Xcode `pngcrush`, Expo app configuration, Jest.

---

### Task 1: Strengthen Asset Contract Tests

**Files:**
- Modify: `mobile/__tests__/app-icon-assets.test.ts`

**Step 1: Write the failing test**

Extend PNG metadata inspection to expose the IHDR color type and assert all
launcher assets use RGB rather than RGBA. This prevents accidental alpha from
causing App Store icon rejection.

**Step 2: Run the focused test**

Run:

```bash
cd mobile
npx jest __tests__/app-icon-assets.test.ts --runInBand
```

Expected: the new assertion fails if any source still uses alpha; otherwise the
asset contract remains green before visual replacement.

**Step 3: Commit the test**

```bash
git add mobile/__tests__/app-icon-assets.test.ts
git commit -m "test(mobile): enforce opaque app icon assets"
```

### Task 2: Generate and Review the Life Core Master

**Files:**
- Create: `/tmp/reva-icon-review/life-core-master.png`
- Create: `/tmp/reva-icon-review/life-core-180.png`
- Create: `/tmp/reva-icon-review/life-core-60.png`
- Create: `/tmp/reva-icon-review/life-core-29.png`

**Step 1: Generate the approved artwork**

Use the built-in image generation path with the design in
`docs/plans/2026-07-27-health-os-assistant-app-icon-design.md`. Require a flat,
centered, text-free, square icon with no platform corner mask.

**Step 2: Normalize the source**

Resize to exactly 1024 x 1024 with `sips`, then use Xcode `pngcrush` to remove
alpha while preserving the visual output.

**Step 3: Build review sizes**

Generate 180 px, 60 px, and 29 px versions with `sips`.

**Step 4: Visually inspect**

Check the four sizes together. Reject the candidate if the assistant silhouette
disappears, the pulse notch becomes noise, or the mark resembles a medical
cross, location pin, chat bubble, or generic activity ring.

### Task 3: Replace Production Icon Assets

**Files:**
- Modify: `mobile/assets/images/icon.png`
- Modify: `mobile/assets/images/adaptive-icon.png`
- Modify: `mobile/assets/images/splash-icon.png`

**Step 1: Copy the approved 1024 px master**

Use the same normalized bytes for `icon.png` and `adaptive-icon.png`.

**Step 2: Derive splash artwork**

Resize the approved master to 512 x 512 and normalize it as opaque RGB PNG.

**Step 3: Verify file metadata**

Run:

```bash
file mobile/assets/images/icon.png \
  mobile/assets/images/adaptive-icon.png \
  mobile/assets/images/splash-icon.png
shasum mobile/assets/images/icon.png \
  mobile/assets/images/adaptive-icon.png
```

Expected: 1024 x 1024 RGB master/adaptive files with identical hashes and a
512 x 512 RGB splash file.

### Task 4: Verify and Deliver

**Files:**
- Test: `mobile/__tests__/app-icon-assets.test.ts`
- Test: `mobile/__tests__/app-config.test.ts`

**Step 1: Run focused tests**

```bash
cd mobile
npx jest __tests__/app-icon-assets.test.ts __tests__/app-config.test.ts --runInBand
```

Expected: all focused suites pass.

**Step 2: Run iOS submission preflight**

```bash
python3 scripts/check_ios_app_store_submission.py
git diff --check
```

Expected: preflight passes and no whitespace errors are reported.

**Step 3: Commit and push**

```bash
git add mobile/__tests__/app-icon-assets.test.ts \
  mobile/assets/images/icon.png \
  mobile/assets/images/adaptive-icon.png \
  mobile/assets/images/splash-icon.png
git commit -m "style(mobile): redesign Reva Health OS app icon"
git push origin main
```

**Step 4: Release classification**

Record this as a native binary change. Do not publish it as OTA; create the next
TestFlight build only after the user approves the final small-size preview.
