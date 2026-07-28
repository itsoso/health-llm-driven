# Reva Health OS Assistant App Icon Design

## Goal

Replace the current waveform-led icon with a distinctive mark that communicates
three product ideas at launcher size:

- personal health;
- a trusted personal assistant;
- an operating system that closes the loop from signal to action.

The icon should feel modern and premium without looking like a hospital,
generic chatbot, fitness tracker, or crypto product.

## Approved Direction: Life Core

Use one compact symbol built from three integrated layers:

1. A continuous outer life ring represents the Health OS, longitudinal
   monitoring, and closed-loop execution.
2. Negative space inside the ring forms a minimal head-and-shoulders assistant
   silhouette. It must remain abstract and professional, without cartoon facial
   features.
3. A short pulse notch is integrated into the lower part of the ring. It is a
   secondary health cue, not a separate waveform illustration.

The mark must read as one object. Avoid floating sparkles, grids, scattered data
points, text, medical crosses, shields, robot faces, and detailed anatomy.

## Visual System

- Background: soft mint, approximately `#DDEFE8`.
- Primary mark: deep emerald, approximately `#126B55`.
- Accent: restrained aqua highlight, approximately `#34CDB0`.
- Form: flat, geometric, optically centered, and fully opaque.
- Corners: the source artwork remains square; iOS applies the platform mask.
- Contrast: strong enough for light and dark home-screen surroundings.
- Safe area: keep the complete mark inside roughly 74% of the canvas.

No text, transparency, drop shadow, glossy bevel, photographic texture, or
fine-line ornament is allowed.

## Small-Size Requirements

The assistant silhouette and life ring must remain recognizable at:

- 1024 px App Store source;
- 180 px iOS home-screen asset;
- 60 px compact launcher preview;
- 29 px Settings and notification contexts.

At 29 px, the expected reading order is:

1. emerald life ring;
2. human assistant core;
3. pulse notch as optional secondary detail.

If the pulse notch or highlight creates noise at 29 px, simplify it rather than
making the overall symbol larger.

## Asset Scope

- `mobile/assets/images/icon.png`: 1024 x 1024 primary icon.
- `mobile/assets/images/adaptive-icon.png`: matching Android artwork.
- `mobile/assets/images/splash-icon.png`: 512 x 512 launch artwork.
- `mobile/app.json`: retain a matching soft-mint splash background.

## Validation

- Confirm exact dimensions, PNG format, full opacity, and no alpha channel.
- Compare 1024 px, 180 px, 60 px, and 29 px previews side by side.
- Confirm the mark does not resemble a medical cross, location pin, chat bubble,
  or generic activity-ring clone.
- Verify Expo resolves all icon assets.
- Run focused mobile asset/configuration tests and iOS submission preflight.

## Delivery

This is a native resource change. It requires a new TestFlight/App Store binary;
it cannot replace the installed home-screen icon through OTA.
