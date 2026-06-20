# Rokid CXR-L iOS Support Package — CustomView / installApp silent after auth

Date: 2026-06-20
Status: draft, ready to send to Rokid once Phase 0 device retest confirms the symptom persists
Owner: Reva (health.executor.life)
Related: `docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md` §6 (this package implements §6 for the *post-auth* boundary)

> How to use this file: it is pre-filled with everything we can know from the repo.
> Fill the `[FILL IN]` device/runtime fields from the failing device, attach the
> listed screenshots/logs, then send the "Message to Rokid" section (§9) plus the
> facts table. Do **not** send before re-testing on EAS build #167 — if that build
> makes `rawNotify` non-`none`, the bug is ours and this package is not needed.

## 1. One-paragraph summary

Reva's iOS app links `RGCxrClient 1.0.1`, completes authorization, and reports BLE
connected to the glasses (`RGCxrClientBLE.shared.isConnected == true`, device
`Glasses_0077`). But **`openCustomView(...)` and `installApp(...)` get no response
at all** — the SDK completion callback never fires, no `customViewRunningEvent` is
published, and `notifyPublisher` delivers nothing (`rawNotify=none`). The glasses
render nothing and no app installs. We need to know what construction/handshake step
between "BLE connected + authenticated" and "openCustomView returns" we are missing,
or whether this is a companion-app / firmware / SDK-version limitation on the iOS
CXR-L surface.

This is the boundary `docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md`
§4.3 calls **"Auth succeeds but CustomView fails → CXR-L session construction."**

## 2. Exact symptom (from a real device, 2026-06-20)

Two consecutive captures on the same device, ~10 min apart:

| Time | BLE state | CustomView open result (verbatim) | installApp result |
|---|---|---|---|
| 10:29 | connected | `rokid_custom_view_open_callback_missing; running=false; rawNotify=none; iosBleConnected=true; device=Glasses_0077` | `rokid_pushup_app_install_failed` |
| 10:39 | not connected | `rokid_glasses_ble_not_connected` | `rokid_pushup_app_install_failed` |

What each field means in our bridge:

- `callback_missing` is set **only** when the SDK's `openCustomView(view) { success, errorCode }`
  completion closure was **never invoked** (our flag `lastCustomViewOpenCommandAccepted`
  stayed `nil` after a 2.0 s settle window).
- `rawNotify=none` means our `RGCxrClientBLE.shared.notifyPublisher` sink received
  **zero** notify events after the open call.
- `running=false` means `customViewRunningEventPublisher` never published `isRunning=true`.
- BLE is **intermittent**: connected at 10:29, dropped by 10:39 — but the silence
  happens even while connected.

So: with auth OK and BLE connected, the open command appears to go into the void.

## 3. What we call, in order

```text
ensureCustomViewInitialized()
  -> CxrClient.initialize(mode: .customView,
       options: RGCxrClientInitializationOptions(appDisplayName: nil, pageName: nil))   // on main thread
  -> CxrClient.shared.auth.config = RGCxrClientAuthConfig(...)                            // see §4
  -> bind publishers: customViewRunningEventPublisher, auth.eventPublisher,
       RGCxrClientBLE.shared.connectionStatePublisher, RGCxrClientBLE.shared.notifyPublisher
  -> CxrClient.shared.setNotifyEventListenCmds([
       Custom_View_Opened, Custom_View_Open_Failed, Custom_View_Updated, Custom_View_Closed ])
guard CxrClient.shared.auth.isAuthenticated()        // passes
guard RGCxrClientBLE.shared.isConnected              // passes (device Glasses_0077)
CxrClient.shared.openCustomView(view) { success, errorCode in ... }   // <-- closure NEVER called
```

`installApp` path: `CxrClient.shared.installApp(path) { installed in ... }` — same
shape, completion returns `installed=false` or is never called.

## 4. Configuration facts (pre-filled from repo)

| Field | Value |
|---|---|
| App bundle id | `life.executor.health` |
| App URL schemes | `mobile`, `health` (+ Rokid auth callback scheme below) |
| Rokid auth callback scheme (Info.plist `RokidCXRAuthCallbackScheme`) | `cxrl` |
| Auth callback URL we register/expect | `cxrl://auth/callback` |
| Companion launch URL we open | `rokidai://connect` |
| Authorization appName | `Reva` |
| Authorization scopes requested | `device_control`, `audio_stream` |
| iOS SDK | `RGCxrClient 1.0.1` + `RGCoreKit 0.0.2` (vendored framework, first-class CocoaPod) |
| Callback API build flag | `ROKID_CXRL_CALLBACK_API` defined (`ROKID_IOS_CLIENT_HAS_CALLBACK_API=1`) |
| Reva build under test | EAS build **#167**, app version **1.3.0**, git commit `5e3d1ea2`, EAS profile/channel `rokid-production` |
| CustomView mode | `CxrClient.initialize(mode: .customView)` reported initialized (`CxrClient.isInitialized == true`) |

> Note: an earlier playbook draft referenced callback scheme
> `life.executor.health.rokid://auth/callback`. The **current** build uses `cxrl://auth/callback`
> (set via `ROKID_IOS_CALLBACK_SCHEME=cxrl`). Please confirm which scheme is whitelisted
> for this app id.

## 5. Device / runtime facts — [FILL IN from the failing device]

| Field | Value |
|---|---|
| iPhone model | [FILL IN] |
| iOS version | [FILL IN] |
| Glasses model | [FILL IN — display vs non-display SKU] |
| Glasses internal name | `Glasses_0077` (shown in our diagnostics) |
| Glasses firmware version | [FILL IN] |
| Companion app installed | Rokid AI? Hi Rokid? both? — [FILL IN exact app name + version] |
| Companion app running during the test? | [FILL IN — was it open / backgrounded / force-quit?] |
| Rokid account region | [FILL IN] |
| `UIApplication.open(rokidai://connect)` succeeds? | [FILL IN — yes/no] |
| Auth `openURL` callback received by Reva? | yes (auth completes; `isAuthenticated()==true`) |

## 6. What we have already done / ruled out (Reva side)

- SDK is linked: `canImport(RGCxrClient)` true; first-class pod (not `vendored_frameworks`,
  which silently failed to reach the `-F` search path under Expo `static_framework`).
- `CxrClient.initialize(mode: .customView)` is called on the main thread before auth and
  reports initialized.
- Authorization succeeds (`isAuthenticated()==true`), callback URL is received.
- `setNotifyEventListenCmds([...Custom_View_*])` is subscribed.
- We gate `openCustomView` on `RGCxrClientBLE.shared.isConnected` (firing it before BLE is
  up produced the same silence historically).
- We **disabled** auto-re-firing `openCustomView` on BLE-connect (it caused double-fire →
  SDK never called back); open is now a single manual user action.
- Pending hypothesis fix (build #167): re-apply `setNotifyEventListenCmds` on every BLE
  (re)connect, in case the cmd registration is per-link and lost on reconnect. **If this
  does not change `rawNotify=none`, the silence is below our layer — which is why we are
  asking you.**

## 7. The core question

Between "BLE connected + authenticated" and a working `openCustomView`, **is there a
required session/connect/handshake step on the iOS CXR-L 1.0.1 surface that we are not
calling?** Our diagnostics suggest `isConnected==true` is not sufficient for the glasses
to accept `openCustomView`. We see no public `connect()` / `startSession()` API in the
1.0.1 framework interface.

## 8. Specific questions for Rokid

1. On iOS CXR-L 1.0.1, what is the exact required call sequence from app launch to a
   rendering CustomView? Is there a session/connect step beyond `initialize(mode:.customView)`
   + `auth` + BLE `isConnected`?
2. Is `RGCxrClientBLE.shared.isConnected == true` sufficient to call `openCustomView`, or
   is there a separate "session ready" signal we should wait for? If so, which publisher/event?
3. When `openCustomView`'s completion closure is **never** invoked (no success, no error),
   what does that indicate — command dropped before transport, glasses not in the right
   mode, companion app required, or firmware/SDK mismatch?
4. Does CXR-L iOS require the companion app (Rokid AI / Hi Rokid) to be **running** to bridge
   `openCustomView` to the glasses? Or must it be **fully quit** to free the BLE central?
   Which companion app is supported for CXR-L iOS in our region?
5. Must `setNotifyEventListenCmds([...])` be re-applied after each BLE (re)connection, or is
   it a one-time global registration?
6. Is `RGCxrClient 1.0.1` still compatible with the current companion app + the firmware on
   glasses `Glasses_0077`? Is there a newer iOS SDK (1.0.2+) / private specs repo?
7. Which bundle ids and callback schemes must be whitelisted for this app id? Is
   `cxrl://auth/callback` correct, or should it be `life.executor.health.rokid://auth/callback`?
8. Are scopes `device_control` and `audio_stream` enabled for this app id? Does CustomView
   need an additional console capability beyond the public list?
9. Same question for `installApp(...)`: what makes the completion return `installed=false`
   or never fire on a BLE-connected, authenticated session?

## 9. Message to Rokid (paste-ready)

> Hi Rokid team — we are integrating CXR-L (`RGCxrClient 1.0.1`) on iOS for our health app
> Reva (`life.executor.health`). Authorization succeeds and `RGCxrClientBLE.shared.isConnected`
> is true (glasses `Glasses_0077`), but `openCustomView(view){ success, errorCode }` never
> invokes its completion closure, `customViewRunningEventPublisher` never fires, and
> `notifyPublisher` delivers no events — the glasses render nothing. `installApp(path){ installed }`
> behaves the same. We call `CxrClient.initialize(mode:.customView)` on the main thread, set
> `auth.config`, subscribe `setNotifyEventListenCmds([Custom_View_Opened/Open_Failed/Updated/Closed])`,
> and only call `openCustomView` after `isConnected==true`. What is the required call sequence
> from authenticated+BLE-connected to a rendering CustomView on iOS 1.0.1? Is there a session
> step we are missing, or is this a companion-app/firmware/SDK-version requirement? Full facts,
> config, and questions attached.

## 10. Attachments checklist

- [ ] Screenshot: Rokid push-up screen at 10:29 (CustomView `callback_missing; rawNotify=none; iosBleConnected=true`).
- [ ] Screenshot: Rokid push-up screen at 10:39 (`rokid_glasses_ble_not_connected`).
- [ ] Reva self-check / diagnostics screen screenshot (auth state, CustomView payload hash, raw notify, callback, retry, error timeline).
- [ ] §4 configuration facts table.
- [ ] §5 device/runtime facts table (filled in).
- [ ] Result from the official `ios_cxr_l_sample` run with the **same** developer config, account, companion app, and glasses (per debugging-lessons §4.1 — strongest signal: if the official sample is also silent, the issue is config/firmware/account, not Reva).
