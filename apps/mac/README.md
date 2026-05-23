# HealthAgentMac

Swift-native macOS client for the Health Agent system.

This app is a first-class desktop execution client: it should support daily operation from the Mac while keeping the backend as the only health reasoning engine and source of truth.

## P0 Scope

- Today dashboard with plan, action cards, memory, and active jobs.
- Agent chat with model switching, streaming, files/images, and evidence sidebar.
- Quick record for diet, supplements, water, weight, blood pressure, and symptoms.
- Import Center for genome txt, medical PDF/image, Apple Health export, and Dedao folder manifests.
- Job Center for reanalysis, knowledge rebuilds, imports, and eval runs.
- Trace Viewer for provider/model/tool/evidence/memory diagnostics.

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

When the UI stabilizes, create an Xcode macOS App project or workspace target that points at the same `Sources/` tree.

