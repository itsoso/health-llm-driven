# Reva Shared Mac and Mobile App Icon Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship the existing Mac pulse-and-sparkle icon as the App Store-ready Mobile icon.

**Architecture:** Extract the 1024 px artwork from the checked-in Mac `.icns`, flatten only its transparent platform corners onto the icon's warm-clay background for iOS compliance, then derive Android and splash assets from that shared source.

**Tech Stack:** macOS `sips`, `ffmpeg`, Expo app configuration, Jest.

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

### Task 2: Extract and Review the Mac Master

**Files:**
- Create: `/tmp/reva-mac-icon/mac-icon.png`
- Create: `/tmp/reva-mac-icon/mobile-icon.png`
- Create: `/tmp/reva-mac-icon/preview-180.png`
- Create: `/tmp/reva-mac-icon/preview-60.png`
- Create: `/tmp/reva-mac-icon/preview-29.png`

**Step 1: Extract the approved artwork**

Extract the highest-resolution representation from
`apps/mac/Sources/HealthAgentMac/Resources/HealthAgentIcon.icns`.

**Step 2: Normalize the source**

Keep the source at exactly 1024 x 1024. Composite its transparent Mac platform
corners onto the rendered warm-clay background and encode it as opaque RGB.

**Step 3: Build review sizes**

Generate 180 px, 60 px, and 29 px versions with `sips`.

**Step 4: Visually inspect**

Check the four sizes together. Reject the candidate if the pulse disappears,
the sparkles become noise, or the result differs materially from the Mac icon.

### Task 3: Replace Production Icon Assets

**Files:**
- Modify: `mobile/assets/images/icon.png`
- Modify: `mobile/assets/images/adaptive-icon.png`
- Modify: `mobile/assets/images/splash-icon.png`

**Step 1: Copy the approved 1024 px master**

Use the same normalized bytes for `icon.png` and `adaptive-icon.png`.

**Step 2: Derive splash artwork**

Resize the shared master to 512 x 512 and normalize it as opaque RGB PNG. Match
the Expo splash background to the warm-clay canvas.

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
git commit -m "style(mobile): share Mac app icon"
git push origin main
```

**Step 4: Release classification**

Record this as a native binary change. Do not publish it as OTA; create the next
TestFlight build only when requested.
