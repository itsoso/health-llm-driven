# HealthAgentMac

Swift-native macOS client for the Health Agent system.

This app is a first-class desktop execution client: it should support daily operation from the Mac while keeping the backend as the only health reasoning engine and source of truth.

## P0 Status

- Implemented: Today dashboard with plan/action cards/active jobs.
- Implemented: Agent chat with streaming, model selection, web-search intent, file/image attachments, drag-and-drop, and evidence sidebar.
- Implemented: Quick and structured record entry for diet, supplements, water, weight, blood pressure, and symptoms.
- Implemented: Import Center for genome txt, medical PDF/image, Apple Health export, and Dedao folders, including raw-file confirmation and source hashing.
- Implemented: Job Center for reanalysis, knowledge rebuilds, imports, and eval runs, including job detail, retry, and trace handoff.
- Implemented: Trace Viewer for provider/model/timing/tool/evidence diagnostics.
- Implemented: Settings for auth token, API base URL, voice preference, and privacy/file handling notes.

## User message actions

Each text prompt has Copy and Edit buttons below its bubble. Copy preserves the original text. Edit opens a separate editor; Cancel leaves the composer draft unchanged. Resend submits the edited text as a new turn and preserves the original conversation history. Pending composer attachments must be sent or removed first, so they cannot accidentally accompany the edited prompt.

## Current Boundaries

- Raw files are classified and hashed locally. P0 creates desktop import jobs with source metadata; it does not yet upload raw file bytes to object storage.
- Health judgment stays backend-owned. The Mac app only formats input, displays evidence, and routes long-running jobs.
- API base URL changes are stored locally and take effect after restarting the Mac app.
- The Swift Package is the source of truth for now; a checked-in Xcode project can be added when signing/distribution work starts.

## Shopping assistant boundary

The shopping destination is separate from health chat. Its default action hands only the question entered on that page to the official Kuaishou client. A user-started, temporary screen preview can show the verified shopping window locally; it does not save or upload frames, import them into the transcript, or prove that an answer has completed. Leaving the view, clearing the session, or changing the health account stops the preview and rejects late frames.

Native shopping API access is not connected by default. The optional web-login and service configuration are integration tools: cookies stay in an isolated, nonpersistent store and retain their original domain/path scope. The optional loopback bridge requires an independently distributed compatible shopping page and explicit pairing. Mock transport, bridge, and snapshot tests do not demonstrate that either production integration is available. Offline demo content is labeled as synthetic and cannot purchase products.

## Architecture

```text
HealthAgentMac (SwiftUI/AppKit)
  -> URLSession API clients
  -> Keychain token storage
  -> local cache and native file handling
  -> FastAPI backend
  -> orchestrator / specialists / Twin / KB / Postgres
```

The Mac app must not duplicate health judgment logic. It may cache display data and perform local file classification/hash extraction, but health decisions and persisted records remain backend-owned.

## Development

Current scaffold is a Swift Package so it can be built and tested from the repository without requiring checked-in Xcode project metadata.

```bash
cd apps/mac
swift test
swift run HealthAgentMac
```

## Double-Click App Bundle

Build a local double-clickable app:

```bash
cd apps/mac
scripts/package-app.sh
open dist/HealthAgentMac.app
```

The script builds the SwiftPM executable, wraps it in `HealthAgentMac.app`, writes a macOS `Info.plist`, and signs with `HEALTH_MAC_SIGN_IDENTITY` or the sole available Apple signing certificate. It fails if no certificate or multiple certificates are available; set `HEALTH_MAC_SIGN_IDENTITY` explicitly in that case. It verifies the signature before reporting success. The generated bundle lives under `apps/mac/dist/` and is not committed.

Use the same certificate and bundle identifier across local rebuilds so Keychain recognizes app updates. Ad-hoc signatures change the app's designated requirement with every binary change and can cause repeated login-keychain prompts. When moving from an old ad-hoc build to certificate signing, macOS may require a one-time authorization for the existing token: enter the Mac login password in the system dialog and choose Always Allow for the verified app. Subsequent builds must retain the same signing identity. Never move the token into plaintext preferences or grant access to all applications to suppress this prompt. `--no-sign` is for inspecting a bundle, not for running an authenticated app.

The app defaults to Chinese. Switch to English from Settings -> Language.

For formal distribution, use the governed Developer ID signing and notarization workflow; a locally signed Apple Development build is not a notarized release.
