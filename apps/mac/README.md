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
- The Swift Package remains the source of truth for both local and formal Developer ID builds.

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

Local feedback is compile/test only. The historical `package-app.sh` path wraps and signs an app,
so it is frozen together with package/install/signing/notarization and is intentionally omitted as
a copyable command. Do not substitute an identity override or direct `codesign`.

The app defaults to Chinese. Switch to English from Settings -> Language.

## Formal Developer ID distribution

The notarized Developer ID DMG protocol is implemented for verification, but **all automated
production Mac writers are currently frozen**. `deploy.sh` rejects route/publish/recover/rollback
before release locks or network mutation; the direct route wrapper and formal driver fail closed as
well. The protocol is not live distribution authority and no Mac production release is implied.

When a later dossier re-enables it after source/artifact authority, recovery testing and independent
G4 review, formal distribution will deliberately remain
outside the Mac App Store/TestFlight and still builds the exact SwiftPM source from a clean,
fresh `origin/main` snapshot.

The entire `apps/mac/scripts/release-dmg.sh` entrypoint is frozen, including historical
preflight/proof modes. A writer-bearing shell cannot double as a read-only checker: `BASH_ENV` and
caller-defined `exit`/`builtin` functions make its top-level status code an ordinary-invocation
tombstone, not a hostile-source trust boundary. Any future read-only checker must be a separately
reviewed file containing no writer code. Direct Python production commands, the nginx wrapper and
raw SSH alternatives are frozen too. Test-only protocol fixtures are
allowed only when the process is non-root, explicit test mode is enabled, and every path is beneath
fixed non-production roots (macOS `/private/tmp` or `/private/var/folders`; `/tmp` elsewhere,
ignoring caller `TMPDIR`). Local `create-candidate` requires the same isolation and may generate
candidate metadata only; it does not sign, upload, switch a route or grant production authority.

`scripts/package-app.sh`, ad-hoc signing and `HEALTH_MAC_SIGN_IDENTITY` overrides are frozen; they do
not become allowed by being called “local”.
The guarded formal path defaults to the configured Developer ID identity and requires it to match
the configured team. Notarization reads `APP_STORE_CONNECT_API_KEY` and
`APP_STORE_CONNECT_ISSUER_ID` from the local production environment and
`~/.appstoreconnect/private_keys/AuthKey_<KEY_ID>.p8` from the operator's
protected App Store Connect key directory; credentials are never copied into Git or remote release
state.

Every release is tied to the exact source SHA/tree, bundle ID, explicit version/build, architecture,
minimum OS, Developer ID signature, accepted notarization result and artifact SHA-256/size. The
server stores immutable bytes and root-owned current/previous receipts. Public verification checks:

- `https://health.executor.life/mac/current.json`;
- the content-addressed URL named by that manifest;
- `https://health.executor.life/xiaoba-mac.dmg`.

After a future re-enable, if SSH, interruption or terminal proof is ambiguous, do not rerun publish.
The independently reviewed recovery path must reuse the retained exact transaction rather than a
newer checkout. The route-bootstrap
rollback is only a pre-first-release escape hatch and is rejected after any formal Mac release state
exists.

The current freeze also covers server/Mobile/ASC writers. Same-UID Git replace, info
attributes+filter, hidden import shadow, `BASH_ENV` and `PYTHONPATH`/`sitecustomize` make repo-local
source proof insufficient. Re-enable only via a new dossier and a repo-external root-owned launcher
with fixed interpreters, `env -i` and canonical archive/tree materialization outside the repo. Until
then Mac G5/G6 are BLOCKED and no release may be marked shipped/complete.
