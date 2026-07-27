# Reva App Icon Light Palette Design

## Goal

Make the Reva app icon feel lighter and more consistent with the current
mobile interface without changing its established recognition shape.

## Visual Direction

- Keep the existing ECG waveform, AI sparkles, data points, and subtle grid.
- Replace the near-black navy background with a soft mint background around
  `#DDEFE8`.
- Render the primary waveform in a calm Reva green around `#167A62`.
- Keep sparkles slightly brighter than the waveform, without neon glow.
- Reduce the grid contrast so it remains texture rather than foreground detail.
- Preserve sufficient contrast and edge clarity at 60 px and 29 px.
- Do not add text, gradients, transparency, or extra decorative elements.

## Asset Scope

- `mobile/assets/images/icon.png`: 1024 x 1024 primary app icon.
- `mobile/assets/images/adaptive-icon.png`: same artwork for Android adaptive
  foreground compatibility.
- `mobile/assets/images/splash-icon.png`: 512 x 512 matching launch artwork.
- `mobile/app.json`: align the splash background with the light icon palette.

## Validation

- Confirm exact dimensions and PNG format.
- Confirm the primary icon is fully opaque.
- Review at original size and downscaled launcher sizes.
- Verify the Expo config resolves all three assets.
- Run the focused mobile configuration tests.

## Delivery

This changes native app resources. Existing installed iOS builds cannot receive
the home-screen icon through OTA; the icon ships in the next TestFlight/App
Store binary.
