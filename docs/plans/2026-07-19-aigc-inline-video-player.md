# AIGC Inline Video Player Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Play completed private AIGC short videos directly in the Xiaoba mobile
Agent conversation, without leaving the current chat.

**Architecture:** The existing owner-scoped job endpoint continues to mint a
short-lived private URL. The AIGC job card resolves that URL to the API origin
and binds it to Expo's native `VideoView`; the player remains in the card and
uses native controls for play, scrub, mute, and fullscreen. Because the player
is a new native module, the iOS app version and Expo runtime are bumped so an
old binary can never download incompatible JavaScript.

**Tech Stack:** Expo SDK 55, `expo-video`, React Native, TypeScript, Jest,
local iOS QR release.

---

### Task 1: Add a failing inline-playback regression

**Files:**
- Modify: `mobile/components/chat/cards/__tests__/registry.test.tsx`

1. Mock `expo-video` as a virtual Jest module.
2. Render a succeeded `image_to_video` card whose result is a relative signed
   private URL.
3. Assert that the rendered card contains a native `VideoView` with the fully
   qualified signed URL and native controls; assert that it no longer calls the
   browser opener.
4. Run the focused Jest test and confirm it fails because no inline player is
   rendered.

### Task 2: Implement the card-local player

**Files:**
- Modify: `mobile/components/chat/cards/AIGCMediaJobCard.tsx`

1. Replace the browser opener with `useVideoPlayer` and `VideoView`.
2. Keep playback paused by default, disable looping, and retain native controls
   and fullscreen support.
3. Preserve the current private URL normalizer and render the player only for
   a succeeded video URL.
4. Run the focused Jest test and confirm it passes.

### Task 3: Add the native module and isolate the runtime

**Files:**
- Modify: `mobile/package.json`
- Modify: `mobile/package-lock.json`
- Modify: `mobile/app.json`

1. Install the Expo SDK-compatible `expo-video` package.
2. Bump the iOS app version from `1.3.1` to `1.3.2`; the existing
   `runtimeVersion.appVersion` policy then prevents `1.3.1` binaries from
   loading the new native-module JavaScript.
3. Verify Expo configuration and package health.

### Task 4: Validate and release the native build

**Files:**
- Modify: `docs/dossiers/2026-07-17-xiaoba-aigc-media.md`

1. Run the focused card suite, full mobile Jest suite, lint, and TypeScript
   checks.
2. Build a production-bundle iOS QR-install artifact, preserving the existing
   app and user session on the device.
3. Verify the build is runtime `1.3.2`; install it before validating an
   inline AIGC video from the active Agent chat.
4. Update the existing AIGC dossier with the release evidence and retain the
   manual owner playback verification as the final production check.
