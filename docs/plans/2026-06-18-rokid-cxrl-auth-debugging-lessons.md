# Rokid CXR-L iOS Auth Debugging Lessons

Date: 2026-06-18
Status: active debugging playbook
Scope: Reva iOS Rokid authorization, CustomView readiness, TestFlight/native build loop

Related files:

- `mobile/modules/rokid-bridge/ios/RokidBridgeModule.swift`
- `mobile/app/rokid-health.tsx`
- `mobile/services/rokidDiagnostics.ts`
- `docs/plans/2026-06-17-rokid-sdk-integration-plan.md`
- `docs/specs/active/2026-06-18-rokid-customapp-install.md`

## 1. Short Answer

This has been hard because the failing path is not a normal in-app bug. It is a five-party handshake:

1. Reva JS screen starts authorization.
2. Reva iOS native bridge configures `RGCxrClient`.
3. iOS launches Rokid AI / Hi Rokid through a custom scheme.
4. Rokid companion app completes cloud/account/device authorization.
5. iOS delivers a callback URL back to Reva, and `RGCxrClient` turns that callback into an authenticated token/session.

Every step can fail with the same user-facing symptom: Reva stays `not_authenticated` or times out. A timeout by itself does not say whether the companion app never opened, the Rokid cloud rejected the app, the bundle id or callback scheme was not whitelisted, the companion app never called back, iOS routed the callback to the wrong app, or the SDK callback handler rejected the URL.

The important conclusion: repeated TestFlight builds are too slow and too low-signal unless each build adds one new boundary observation.

## 2. Why Authorization Has Not Succeeded Yet

Current Reva-side facts:

- The iOS SDK can be linked in the native build.
- The bridge can call into `RGCxrClient`.
- Reva registers and displays a dedicated Rokid callback scheme: `life.executor.health.rokid://auth/callback`.
- Reva has native diagnostics for auth request timing, SDK callback source, iOS `openURL`, callback fingerprint, and retry state.
- Recent builds fixed a real retry bug: an explicit retry now resets more local authorization states, including the `notAuthenticated` state that could otherwise prevent a second external auth attempt.

Still unproven facts:

- Rokid AI / Hi Rokid actually sends the callback URL back to iOS.
- The Rokid developer console has the exact bundle ids and callback scheme/host/path whitelisted for all Reva variants.
- `RGCxrClient 1.0.1` is compatible with the currently installed Rokid companion app and glasses firmware.
- The AppKey/AppSecret/accessKey/account region match the companion app being used.
- The public iOS SDK path has parity with the Android CXR-L 1.0.3 path.

So the current best diagnosis is:

If build 146 still shows no Reva `openURL` callback after completing Rokid-side authorization, the failure boundary is outside the Reva JS screen and likely outside the Reva AppDelegate callback handler. The next useful work is not another UI tweak; it is proving whether Rokid's official sample or a minimal iOS auth probe can receive the callback with the same developer configuration.

## 3. Why This Was Easy To Misdiagnose

### 3.1 The SDK Is A Black Box

The public CXR-L material confirms the Android/iOS direction and the session model, but the iOS auth contract is still under-specified from Reva's point of view. In particular, the docs do not make the callback URL shape, region/app mapping, retry semantics, and companion-app version matrix sufficiently observable.

### 3.2 Expo Adds A Native Boundary

JS/TS code can be changed by OTA, but the Rokid bridge, `Info.plist`, callback scheme, AppDelegate subscriber, Pod version, Swift toolchain, and EAS profile all require a native build. This creates a long feedback loop:

- A UI fix may ship quickly by OTA.
- A native auth fix requires EAS build plus TestFlight processing.
- If the user is not on the exact native build/channel, the test result may describe an older bridge.

### 3.3 The Error Message Is Too Coarse

`authentication request timeout` is not a root cause. It is a terminal symptom for multiple underlying cases:

- Reva never successfully launched the companion app.
- Companion app opened but did not enter the correct authorization flow.
- User completed consent but companion app did not call back.
- Callback scheme was not whitelisted or did not match.
- iOS routed the callback somewhere else.
- `RGCxrClient` received the callback but rejected it.
- The SDK waited for a companion-side window that closed or never appeared.

### 3.4 Companion App Region Matters

Rokid AI and Hi Rokid are not interchangeable assumptions. Public and community signals suggest the iOS CXR-L path may differ by region/app channel. The product UI should stop treating "Hi Rokid" as a generic name and should log/display which companion app was actually opened when possible.

### 3.5 TestFlight Is A Bad Inner Loop

TestFlight is useful for final user validation, but it is a poor debugging loop for SDK authorization:

- It hides native console logs from quick inspection.
- App Store processing creates delay.
- Build number, runtime version, and OTA channel can confuse the result.
- A failed run often gives only a screenshot, not the raw iOS URL or SDK event.

## 4. Better Debugging Method

### 4.1 Use A Control Sample First

Before more Reva changes, run the official `ios_cxr_l_sample` with the same Rokid developer configuration:

- Same AppKey/AppSecret/accessKey.
- Same bundle id class, or a separately whitelisted sample bundle id.
- Same callback scheme/host/path.
- Same iPhone, same Rokid account, same companion app, same glasses.

If the official sample cannot receive the callback, Reva should stop spending time on bridge changes and escalate to Rokid with evidence.

### 4.2 Build A Minimal iOS Auth Probe

Create a tiny Swift/Xcode probe app outside Expo:

- One button: `requestAuthorization`.
- One AppDelegate/SceneDelegate URL handler.
- Raw logging of every incoming URL, redacted query, and SDK callback result.
- Same callback scheme as a whitelisted probe bundle.
- Direct Xcode install to the iPhone.

This removes React Native, Expo prebuild, EAS, OTA, navigation, and TestFlight from the equation. If the probe works and Reva does not, the bug is in Reva's native integration. If the probe also fails, the issue is Rokid SDK/config/companion/account/firmware.

### 4.3 Use Evidence Gates

| Evidence | Boundary | Next action |
| --- | --- | --- |
| Companion app cannot be opened | iOS scheme / `LSApplicationQueriesSchemes` | Fix scheme detection/opening. |
| Companion opens, but Reva records no `openURL` | Rokid companion / console whitelist / region / callback config | Verify official sample and contact Rokid. |
| Reva records wrong callback URL | Bundle or callback scheme mismatch | Fix developer console and `Info.plist` together. |
| Reva records correct callback but SDK stays unauthenticated | SDK callback handler / token validation | Compare official sample callback handling and SDK version. |
| Auth succeeds but CustomView fails | CXR-L session construction | Debug `connect`, Bluetooth state, and `customViewOpen`. |
| CustomView opens but photo/audio fails | Capability gating | Verify session build completion and capability matrix. |

### 4.4 Stop Shipping Blind Native Builds

A new TestFlight build is justified only when one of these changes is true:

- It adds a new boundary signal.
- It fixes a proven mismatch.
- It changes the actual native bridge or native config.
- It updates the SDK/toolchain/profile.

Otherwise, run the local probe or official sample first.

## 5. Immediate Next Steps

1. Install the latest Rokid native build and verify the exact build number in Reva diagnostics.
2. Tap authorization once, complete the Rokid-side flow, return to Reva, refresh, and capture the self-check screen.
3. Read these fields first:
   - SDK auth state.
   - Last auth request time.
   - Last SDK auth event.
   - Last iOS `openURL` callback.
   - Last callback fingerprint.
   - Last auth error.
4. If there is no iOS callback, freeze Reva code changes and test the official sample/probe.
5. If there is a callback, compare its scheme/host/path/query with the configured `life.executor.health.rokid://auth/callback`.
6. If auth succeeds, only then proceed to CustomView/session/capability verification.

## 6. Support Package For Rokid

When contacting Rokid, send a compact package:

- Reva bundle id: `life.executor.health` or the exact test bundle.
- Reva callback: `life.executor.health.rokid://auth/callback`.
- Reva build number, git commit, EAS profile, runtime version, update channel.
- SDK version: `RGCxrClient 1.0.1` unless changed.
- Rokid AI / Hi Rokid exact app name and version.
- iOS version, iPhone model, glasses model, glasses firmware.
- Whether `UIApplication.open` succeeds.
- Whether Reva receives any `openURL`.
- Redacted callback URL fingerprint if received.
- Screenshot of Reva self-check diagnostics.
- Result from official `ios_cxr_l_sample` with the same developer configuration.

Questions to ask:

- Which companion app is supported for CXR-L iOS in this region: Rokid AI, Hi Rokid, or both?
- Is `RGCxrClient 1.0.1` still supported with the current companion app?
- Is there a private specs repo for `RGCxrClient 1.0.2+` or a newer iOS SDK package?
- What exact callback URL shape does the iOS SDK expect?
- Which bundle ids and callback schemes must be whitelisted?
- Are scopes such as `device_control` and `audio_stream` enabled for this app id?
- Does CXR-L iOS require a console capability beyond the public app capability list?

## 7. Product And Engineering Lessons

- Add diagnostics before the third speculative fix.
- Never call a vendor SDK auth path fixed until a physical device proves callback receipt and SDK authentication.
- Treat timeout as "insufficient evidence", not as a root cause.
- Keep native build number, runtime version, channel, commit, SDK version, and companion app name visible in diagnostics.
- Do not mix production OTA channels with native SDK test packages.
- Keep Rokid AI and Hi Rokid separate in logs and UI.
- Prefer a standalone probe for black-box SDK auth before integrating the full product surface.
- Do not change callback scheme, bundle id, SDK version, scopes, and UI in the same release.
- Preserve a decision table for every external-device integration: no callback, wrong callback, callback rejected, auth ok/session failed, session ok/capability failed.

## 8. Definition Of Done

Rokid authorization is not done until all are true on a physical device:

- Reva opens the intended companion app.
- User completes Rokid-side authorization.
- Reva records a matching iOS callback.
- `RGCxrClient` reports authenticated state.
- Reva can call `connect` and receive linked glasses state.
- CustomView opens and the glasses show the Reva view.
- Capability-specific calls are tested only after session construction is complete.

## 9. References

- Official Rokid CXR-L SDK direction: <https://ar.rokid.com/sdk?lang=en>
- Current Reva integration plan: `docs/plans/2026-06-17-rokid-sdk-integration-plan.md`
- Current CustomApp install plan: `docs/specs/active/2026-06-18-rokid-customapp-install.md`
- Non-authoritative community signal: <https://www.reddit.com/r/rokid_official/comments/1tkh3ba/authentication_problem_with_cxrl_sdk_ios/>
