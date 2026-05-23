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

## Current Boundaries

- Raw files are classified and hashed locally. P0 creates desktop import jobs with source metadata; it does not yet upload raw file bytes to object storage.
- Health judgment stays backend-owned. The Mac app only formats input, displays evidence, and routes long-running jobs.
- API base URL changes are stored locally and take effect after restarting the Mac app.
- The Swift Package is the source of truth for now; a checked-in Xcode project can be added when signing/distribution work starts.

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

The script builds the SwiftPM executable, wraps it in `HealthAgentMac.app`, writes a macOS `Info.plist`, and applies local ad-hoc signing. The generated bundle lives under `apps/mac/dist/` and is not committed.

The app defaults to Chinese. Switch to English from Settings -> Language.

When formal distribution starts, create an Xcode macOS App project or workspace target that points at the same `Sources/` tree and replace ad-hoc signing with Developer ID/TestFlight signing.
