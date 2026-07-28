# Reva Shared Mac and Mobile App Icon Design

## Goal

Use the established Mac application icon as the single visual direction for the
Mobile launcher and launch screen. The shared mark communicates:

- personal health;
- a trusted personal assistant;
- a calm, modern Health OS.

This decision replaces the experimental “Life Core” direction. Mobile must not
develop a separate symbol while Mac continues to use the warm pulse-and-sparkle
mark.

## Approved Direction: Mac Brand Mark

The visual source of truth is the artwork embedded in:

`apps/mac/Sources/HealthAgentMac/Resources/HealthAgentIcon.icns`

Its deterministic construction is documented in:

`apps/mac/scripts/generate-icons.swift`

The mark combines a white pulse, three warm-cream sparkles, and a translucent
inner tile on a warm clay background. No screenshot chrome, macOS selection
outline, app label, text, or platform corner mask belongs in the Mobile source.

## Visual System

- Background: warm clay, rendered from the Mac source as `#D57953`.
- Primary mark: white ECG pulse.
- Accent: warm-cream sparkles with restrained translucent glow.
- Form: flat, compact, optically centered, and fully opaque on Mobile.
- Corners: Mobile artwork remains square; iOS applies the platform mask.
- Launch screen: use the same warm-clay background so the contained image has
  no visible square seam.

## Small-Size Requirements

The pulse and primary sparkle must remain recognizable at:

- 1024 px App Store source;
- 180 px iOS home-screen asset;
- 60 px compact launcher preview;
- 29 px Settings and notification contexts.

At 29 px, the expected reading order is:

1. warm clay tile;
2. white pulse;
3. sparkle as an assistant cue.

## Asset Scope

- `mobile/assets/images/icon.png`: 1024 x 1024 primary icon.
- `mobile/assets/images/adaptive-icon.png`: matching Android artwork.
- `mobile/assets/images/splash-icon.png`: 512 x 512 launch artwork.
- `mobile/app.json`: use the matching warm-clay splash background.

## Validation

- Confirm exact dimensions, PNG format, full opacity, and no alpha channel.
- Compare 1024 px, 180 px, 60 px, and 29 px previews side by side.
- Compare the Mobile master with the current Mac source.
- Verify Expo resolves all icon assets.
- Run focused mobile asset/configuration tests and iOS submission preflight.

## Delivery

This is a native resource change. It requires a new TestFlight/App Store binary;
it cannot replace the installed home-screen icon through OTA.
