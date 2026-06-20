# Rokid CXR-L iOS Support Package — CustomView / installApp silent after auth

Date: 2026-06-20
Status: draft — transport/session focused. Send ONLY after build #169 device retest per the gate below (zero notify incl. no `Dev_BatteryChanged`, or after WiFi/companion ruled out)
Owner: Reva (health.executor.life)
Related: `docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md` §6 (this package implements §6 for the *post-auth* boundary)

> How to use this file: it is pre-filled with everything we can know from the repo.
> Fill the `[FILL IN]` device/runtime fields from the failing device, attach the
> listed screenshots/logs, then send the "Message to Rokid" section (§9) plus the
> facts table.
>
> UPDATE 2026-06-20 (after a 38-agent swiftinterface audit + transport analysis):
> - Build #167 (re-subscribe on reconnect) did NOT fix it — device-confirmed `rawNotify=none`.
> - Audit found a real bridge bug: we observed the WRONG notify publisher. The SDK feeds
>   `setNotifyEventListenCmds`-matched events on `CxrClient.notifyEventPublisher`
>   (`RGCxrClientNotifyEvent`), but the bridge subscribed only `RGCxrClientBLE.notifyPublisher`
>   (raw `String`). **Build #168 (commit 5e3d1ea2/5a671d3e) subscribes the typed publisher.**
> - Transport analysis: CXR-L is BLE (control) + TCP/WiFi (data). **Build #169 (commit 01c519b4)**
>   adds `Dev_BatteryChanged`/`NoNetwork`/`Wifi_Status`/`Wifi_Connect_Status`/`Dev_Screen_Status`
>   to the listen set, so the next device test shows whether the notify channel is alive at all
>   and whether the glasses report no-network.
>
> **Send gate — retest on build #169 first.** Decision rule from the `custom_view_notify_typed`
> diagnostic timeline:
> - `Custom_View_*` events appear → it was our wrong-pipe bug; do NOT escalate.
> - Only `Dev_BatteryChanged` (no `Custom_View_*`) → notify channel alive, CustomView-specific
>   issue → escalate with that nuance.
> - `NoNetwork` / WiFi-error events → glasses not networked → fix WiFi first (glasses on WiFi,
>   phone+glasses same network, companion running), do NOT escalate yet.
> - **ZERO events (not even `Dev_BatteryChanged`)** → the data session/transport is down →
>   escalate (this package is warranted).
>
> Also verified: the SDK exposes NO app-callable `connect()/startSession()/wifi` — do not ask
> Rokid for a "missing init step"; ask about the TCP/WiFi **data session** (see §7/§8).

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
| Companion app | **Rokid AI** (observed via the "◀ Rokid AI" return link on device); confirm exact version, and whether Hi Rokid is also installed — [FILL IN version] |
| Companion running during the test? | [FILL IN — open / backgrounded / force-quit?] |
| **Glasses connected to WiFi?** | [FILL IN — CRITICAL: the CXR data channel is TCP over WiFi] |
| **Phone + glasses on the SAME WiFi / mutually reachable network?** | [FILL IN] |
| Rokid account region | [FILL IN] |
| `UIApplication.open(rokidai://connect)` succeeds? | [FILL IN — yes/no] |
| Auth `openURL` callback received by Reva? | yes (auth completes; `isAuthenticated()==true`) |
| Reva build under test | **#169** (EAS build `54d79578`, commit `01c519b4`) — typed `notifyEventPublisher` now subscribed + `Dev_BatteryChanged`/`NoNetwork`/`Wifi_Status`/`Wifi_Connect_Status`/`Dev_Screen_Status` added to `setNotifyEventListenCmds` |
| `custom_view_notify_typed` events seen on #169? | [FILL IN — none at all / only `Dev_BatteryChanged` / `NoNetwork` / `Custom_View_*` ...] |

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
- Build #167: re-applied `setNotifyEventListenCmds` on every BLE (re)connect — **device-tested,
  did NOT change `rawNotify=none`** (refuted the per-link-subscription hypothesis).
- Build #168 (commit `5e3d1ea2`): found we observed the WRONG notify publisher — the bridge
  subscribed only `RGCxrClientBLE.shared.notifyPublisher` (raw `String`), never
  `CxrClient.shared.notifyEventPublisher` (`RGCxrClientNotifyEvent`), which is the channel
  `setNotifyEventListenCmds` actually feeds. Now both are subscribed.
- Build #169 (commit `01c519b4`): added `Dev_BatteryChanged` / `NoNetwork` / `Wifi_Status` /
  `Wifi_Connect_Status` / `Dev_Screen_Status` to the listen set, to observe whether the SDK's
  notify channel is alive at all and whether the glasses report no-network. **If #169 still
  shows zero typed events (not even `Dev_BatteryChanged`), the data session is not up — which
  is why we are asking you.**
- We verified (over the byte-identical public+private `.swiftinterface`) there is **NO**
  app-callable `connect()/startSession()/bind()/wifi` API; the session
  (`startSession → sessionResponse(tcpPort) → heartbeat → data`) is SDK-internal after auth.
  The Android bridge calls no such API either.

## 7. The core question

CXR-L is a **dual transport**: BLE (`CoreBluetooth`) for control/handshake + **TCP (Apple
`Network`) for the data channel**. The `RGCxrClient 1.0.1` interface imports `Network`,
`RGCxrSessionResponse` carries `tcpPort: UInt16?` + `heartbeatInterval`, the wire protocol
`RGCxrMessageType` is `auth → authResponse → startSession → sessionResponse → heartbeat → data
→ endSession`, and there is a full `Wifi_*` / `NoNetwork` cmd set.

With auth OK and `RGCxrClientBLE.shared.isConnected == true`, but `openCustomView` /
`installApp` totally silent (no completion callback, no `customViewRunningEvent`, no notify on
either publisher), our strong hypothesis is that **the TCP/WiFi data session is not coming up**
— the BLE control link is fine, but the data channel that actually carries CustomView frames /
APK bytes never establishes. We verified there is **no** app-callable
`connect()/startSession()/wifi` API (and Android calls none either), so this session is
SDK-internal after auth.

Core question: **what must be true for the SDK's internal `startSession → sessionResponse(tcpPort)
→ data` channel to come up over CXR-L iOS — specifically, does it require the glasses to be on
WiFi, the phone and glasses on the same network, and/or the companion app running — and how do
we observe or trigger it from the app?**

## 8. Specific questions for Rokid (transport / session focused)

1. **TCP data session**: After `auth` + `RGCxrClientBLE.isConnected==true`, does CXR-L iOS need
   a TCP data session (`RGCxrSessionResponse.tcpPort`) to be established before `openCustomView`
   can render? Is `startSession → sessionResponse(tcpPort) → heartbeat` driven entirely by the
   SDK, or must the app/companion do something? What blocks it from coming up?
2. **WiFi / network requirement**: Must the **glasses be connected to WiFi** for the data
   channel? Must the **phone and glasses be on the same network** (local TCP), or does the data
   path go through Rokid cloud? What is the exact network topology for CustomView frames?
3. **`NoNetwork`**: Under what conditions do the glasses emit the `NoNetwork` notify, and what
   is the app's correct remediation (drive `Wifi_Connect`? defer to companion?)?
4. **Companion role**: Is the **Rokid AI companion required to be running** to establish/bridge
   the CXR-L session (WiFi setup, TCP relay)? Earlier guidance suggested fully quitting it to
   free the BLE central — which is correct for CXR-L iOS: companion running, or quit?
5. **Readiness signal**: Is `RGCxrClientBLE.isConnected==true` sufficient to call
   `openCustomView`, or is there a separate "data session ready" event/publisher we must wait
   for? (We currently gate only on BLE `isConnected`.)
6. **Silent completion**: When `openCustomView(view){success,errorCode}` is **never** invoked
   (no success, no error) and **no** `RGCxrClientNotifyEvent` arrives on
   `CxrClient.notifyEventPublisher` (we now subscribe it) — even `Dev_BatteryChanged` is absent
   — what does total notify silence indicate at the transport layer?
7. **Version/firmware**: Is `RGCxrClient 1.0.1` compatible with the current Rokid AI version +
   the firmware on glasses `Glasses_0077`? Is there a newer iOS SDK (1.0.2+) / private specs repo?
8. **Whitelisting/scopes**: Are bundle id `life.executor.health` + callback `cxrl://auth/callback`
   whitelisted, and are scopes `device_control` + `audio_stream` enabled for this app id? Does
   CustomView/data need any console capability beyond the public list?
9. **installApp**: Same transport question for `installApp(path){installed}` — does it also ride
   the TCP data session, and why would it return `installed=false`/never fire on a BLE-connected,
   authenticated session?

## 9. Message to Rokid (paste-ready)

> Hi Rokid team — we are integrating CXR-L (`RGCxrClient 1.0.1`) on iOS for our health app
> Reva (`life.executor.health`, callback `cxrl://auth/callback`). Authorization succeeds
> (`auth.isAuthenticated()==true`) and `RGCxrClientBLE.shared.isConnected==true` to glasses
> `Glasses_0077`, but `openCustomView(view){success,errorCode}` **never invokes its completion
> closure**, `customViewRunningEventPublisher` never fires, and we receive **zero** events on
> both `CxrClient.notifyEventPublisher` (typed `RGCxrClientNotifyEvent`) and
> `RGCxrClientBLE.notifyPublisher` (we subscribe both) — not even `Dev_BatteryChanged`. The
> glasses render nothing; `installApp(path){installed}` is identically silent. We do
> `initialize(mode:.customView)` (main thread) → set `auth.config` → subscribe the publishers →
> `setNotifyEventListenCmds([Custom_View_*, Dev_BatteryChanged, NoNetwork, Wifi_Status, ...])`
> → call `openCustomView` only after `isConnected==true`. We verified there is no app-callable
> `connect()/startSession()/wifi` API (Android calls none either). Since the SDK imports
> `Network` and `RGCxrSessionResponse` carries `tcpPort`+heartbeat, our hypothesis is that the
> **TCP/WiFi data session never establishes** even though BLE is connected. **What must be true
> for that session to come up — glasses on WiFi, phone+glasses on the same network, companion
> running — and how do we observe/trigger it?** Full facts, config, device info, and questions
> attached.

## 10. Attachments checklist

- [ ] Screenshot: Rokid push-up screen at 10:29 (CustomView `callback_missing; rawNotify=none; iosBleConnected=true`).
- [ ] Screenshot: Rokid push-up screen at 10:39 (`rokid_glasses_ble_not_connected`).
- [ ] Reva self-check / diagnostics screen screenshot (auth state, CustomView payload hash, raw notify, callback, retry, error timeline).
- [ ] §4 configuration facts table.
- [ ] §5 device/runtime facts table (filled in).
- [ ] Result from the official `ios_cxr_l_sample` run with the **same** developer config, account, companion app, and glasses (per debugging-lessons §4.1 — strongest signal: if the official sample is also silent, the issue is config/firmware/account, not Reva).
