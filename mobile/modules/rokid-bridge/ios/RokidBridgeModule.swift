import ExpoModulesCore
import Combine
import Foundation
import UIKit

#if canImport(RGCxrClient)
import RGCxrClient
#endif

#if canImport(RGCoreKit)
import RGCoreKit
#endif

#if ROKID_IOS_SDK_REQUESTED && !canImport(RGCxrClient) && !ROKID_IOS_SIMULATOR_EXCLUDED
#error("ROKID_IOS_SDK_REQUESTED requires RGCxrClient to be importable. Check ROKID_IOS_CLIENT_FRAMEWORK_PATH and RokidBridge.podspec vendored_frameworks.")
#endif

#if ROKID_CXRL_CALLBACK_API && !canImport(RGCxrClient)
#error("ROKID_CXRL_CALLBACK_API requires the refreshed RGCxrClient framework to be importable.")
#endif

public class RokidBridgeModule: Module {
  private final class PromiseResolutionState {
    var resolved = false
  }

  private static let companionAppName = "Rokid AI / Hi Rokid"
  private static let companionServerScheme = "rokidai"
  private static let companionServerHost = "connect"
  private static let callbackHost = "auth"
  private static let callbackPath = "/callback"
  private static let callbackSchemeInfoPlistKey = "RokidCXRAuthCallbackScheme"
  private static let sdkDefaultCallbackScheme = "cxrl"
  private static let fallbackBundleCallbackScheme = "life.executor.health.rokid"
  private static let authorizationRequestTimeoutSeconds: TimeInterval = 180.0
  private static let querySchemes = ["rokidai"]
  private static var didConfigureAuthentication = false
  private static var didInitializeCustomView = false
  private static var didBindRuntimeEvents = false
  private static var customViewRunning = false
  private static var cxrInitializationOutcome = "not_started"
  private static var lastCallbackUrl: String?
  private static var lastCallbackAt: String?
  private static var lastCallbackHandled: Bool?
  private static var lastAuthorizationAppName: String?
  private static var lastAuthorizationScopes: [String]?
  private static var lastAuthorizationRequestAt: String?
  private static var lastAuthorizationError: String?
  private static var lastAuthorizationErrorAt: String?
  private static var lastAuthorizationEvent: String?
  private static var lastAuthorizationEventAt: String?
  private static var currentDeviceName: String?
  private static var lastOpenUrlFingerprint: String?
  private static var lastOpenUrlAt: String?
  private static var lastOpenUrlExpectedAuthCallback: Bool?
  private static var lastCustomViewPayloadHash: String?
  private static var lastCustomViewPayloadShape: String?
  private static var lastCustomViewPayloadBytes: Int?
  private static var lastCustomViewCommandAt: String?
  private static var lastCustomViewRawNotify: String?
  private static var lastCustomViewRawNotifyAt: String?
  private static var lastCustomViewOpenError: String?
  private static var lastCustomViewOpenCommandAccepted: Bool?
  private static var lastCustomViewOpenCallbackSuccess: Bool?
  private static var lastCustomViewOpenCallbackErrorCode: String?
  private static var lastCustomViewOpenCallbackAt: String?
  private static let customViewOpenSettleDelaySeconds: TimeInterval = 2.0
  private static let authDiagnosticTimelineLimit = 40
  private static var authDiagnosticTimeline: [String] = []
  private static var authorizationAttemptCount = 0
  private static var lastAuthorizationAttemptId: String?
  private static var lastAuthorizationStartedAt: Date?
  private static var lastAuthorizationDurationMs: Int?
  private static var lastAuthorizationPhase: String?
  private static var lastAuthorizationStateBeforeReset: String?
  private static var lastAuthorizationStateAfterReset: String?
  private static var lastAuthorizationStateBeforeAuthenticate: String?
  #if canImport(RGCxrClient)
  private static var cancellables = Set<AnyCancellable>()
  #endif

  private static var bundleCallbackScheme: String {
    guard let bundleIdentifier = Bundle.main.bundleIdentifier, !bundleIdentifier.isEmpty else {
      return fallbackBundleCallbackScheme
    }
    return "\(bundleIdentifier).rokid"
  }

  private static var configuredCallbackScheme: String? {
    guard let configured = Bundle.main.object(forInfoDictionaryKey: callbackSchemeInfoPlistKey) as? String else {
      return nil
    }
    let scheme = configured.trimmingCharacters(in: .whitespacesAndNewlines)
    return scheme.isEmpty ? nil : scheme
  }

  private static var callbackScheme: String {
    configuredCallbackScheme ?? bundleCallbackScheme
  }

  private static var callbackSchemeSource: String {
    configuredCallbackScheme == nil ? "bundle_identifier" : "info_plist"
  }

  private static var acceptedCallbackSchemes: [String] {
    var schemes = [
      callbackScheme,
      bundleCallbackScheme,
    ]
    if callbackScheme.caseInsensitiveCompare(sdkDefaultCallbackScheme) == .orderedSame {
      schemes.append(sdkDefaultCallbackScheme)
    }
    return uniqueSchemes(schemes)
  }

  public func definition() -> ModuleDefinition {
    Name("RokidBridge")

    AsyncFunction("getIntegrationStatus") { () -> [String: Any] in
      RokidBridgeModule.integrationStatusPayload()
    }

    AsyncFunction("openHiRokid") { (promise: Promise) in
      RokidBridgeModule.openHiRokid(promise: promise)
    }

    AsyncFunction("requestAuthorization") { (scopes: [String], appName: String, promise: Promise) in
      RokidBridgeModule.requestAuthorization(scopes: scopes, appName: appName, promise: promise)
    }

    AsyncFunction("clearAuthorization") {
      RokidBridgeModule.clearAuthorization()
    }

    AsyncFunction("openCustomView") { (view: String, promise: Promise) in
      RokidBridgeModule.openCustomView(view, promise: promise)
    }

    AsyncFunction("updateCustomView") { (view: String, promise: Promise) in
      RokidBridgeModule.updateCustomView(view, promise: promise)
    }

    AsyncFunction("closeCustomView") { (view: String, promise: Promise) in
      RokidBridgeModule.closeCustomView(view, promise: promise)
    }

    AsyncFunction("takePhotoBase64") { (width: Int, height: Int, quality: Int, promise: Promise) in
      RokidBridgeModule.takePhotoBase64(width: width, height: height, quality: quality, promise: promise)
    }

    AsyncFunction("queryApp") { (packageName: String, promise: Promise) in
      RokidBridgeModule.queryApp(packageName: packageName, promise: promise)
    }

    AsyncFunction("installBundledApp") { (resourceName: String, resourceExtension: String, packageName: String, promise: Promise) in
      RokidBridgeModule.installBundledApp(
        resourceName: resourceName,
        resourceExtension: resourceExtension,
        packageName: packageName,
        promise: promise
      )
    }

    AsyncFunction("installAppFileUri") { (fileUri: String, packageName: String, promise: Promise) in
      RokidBridgeModule.installAppFileUri(
        fileUri: fileUri,
        packageName: packageName,
        promise: promise
      )
    }

    AsyncFunction("uninstallApp") { (packageName: String, promise: Promise) in
      RokidBridgeModule.uninstallApp(packageName: packageName, promise: promise)
    }

    AsyncFunction("openApp") { (packageName: String, activityName: String, url: String, promise: Promise) in
      RokidBridgeModule.openApp(
        packageName: packageName,
        activityName: activityName,
        url: url,
        promise: promise
      )
    }

    AsyncFunction("stopApp") { (packageName: String, promise: Promise) in
      RokidBridgeModule.stopApp(packageName: packageName, promise: promise)
    }

    AsyncFunction("startRecord") { (type: String, codec: String, mode: String) -> [String: Any] in
      RokidBridgeModule.startRecord(type: type, codec: codec, mode: mode)
    }

    AsyncFunction("stopRecord") { (type: String) -> [String: Any] in
      RokidBridgeModule.stopRecord(type: type)
    }
  }

  private static func integrationStatusPayload() -> [String: Any] {
    ensureCustomViewInitialized()
    let installed = canOpenHiRokid()
    var payload: [String: Any] = [:]
    payload["platform"] = "ios"
    payload["bridgeAvailable"] = true
    payload["hiRokidInstalled"] = installed
    payload["canOpenHiRokid"] = installed
    payload["mode"] = "sdk_probe"
    payload["sdkLinked"] = sdkLinked()
    payload["sdkLinkedReason"] = sdkLinkedReason()
    payload["iosSdkDependencyMode"] = sdkDependencyMode()
    payload["iosSdkCompatibility"] = "CXR-L iOS public sample uses RGCxrClient 1.0.1; 1.0.2 requires Rokid specs source"
    payload["nativeAppVersion"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? ""
    payload["nativeBuildNumber"] = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? ""
    payload["cxrCallbackApiEnabled"] = cxrCallbackApiEnabled()
    payload["cxrNotifySubscriptionMode"] = cxrNotifySubscriptionMode()
    payload["sessionMode"] = "customView"
    payload["authorizationState"] = authorizationState()
    payload["authorizationRequestTimeoutSeconds"] = authorizationRequestTimeoutSeconds
    payload["iosBleConnected"] = iosBleConnected()
    if let bleDeviceName = iosBleDeviceName() {
      payload["iosBleDeviceName"] = bleDeviceName
    }
    payload["customViewRunning"] = isCustomViewRunning()
    payload["capabilitiesReady"] = capabilitiesReady()
    payload["customAppSupported"] = sdkLinked()
    if let lastCustomViewPayloadHash {
      payload["lastCustomViewPayloadHash"] = lastCustomViewPayloadHash
    }
    if let lastCustomViewPayloadShape {
      payload["lastCustomViewPayloadShape"] = lastCustomViewPayloadShape
    }
    if let lastCustomViewPayloadBytes {
      payload["lastCustomViewPayloadBytes"] = lastCustomViewPayloadBytes
    }
    if let lastCustomViewCommandAt {
      payload["lastCustomViewCommandAt"] = lastCustomViewCommandAt
    }
    if let lastCustomViewRawNotify {
      payload["lastCustomViewRawNotify"] = lastCustomViewRawNotify
    }
    if let lastCustomViewRawNotifyAt {
      payload["lastCustomViewRawNotifyAt"] = lastCustomViewRawNotifyAt
    }
    if let lastCustomViewOpenError {
      payload["lastCustomViewOpenError"] = lastCustomViewOpenError
    }
    if let lastCustomViewOpenCommandAccepted {
      payload["lastCustomViewOpenCommandAccepted"] = lastCustomViewOpenCommandAccepted
    }
    if let lastCustomViewOpenCallbackSuccess {
      payload["lastCustomViewOpenCallbackSuccess"] = lastCustomViewOpenCallbackSuccess
    }
    if let lastCustomViewOpenCallbackErrorCode {
      payload["lastCustomViewOpenCallbackErrorCode"] = lastCustomViewOpenCallbackErrorCode
    }
    if let lastCustomViewOpenCallbackAt {
      payload["lastCustomViewOpenCallbackAt"] = lastCustomViewOpenCallbackAt
    }
    payload["companionAppName"] = companionAppName
    payload["companionServerScheme"] = companionServerScheme
    payload["companionServerHost"] = companionServerHost
    payload["callbackScheme"] = callbackScheme
    payload["callbackUrl"] = "\(callbackScheme)://\(callbackHost)\(callbackPath)"
    payload["callbackSchemeSource"] = callbackSchemeSource
    payload["acceptedCallbackSchemes"] = acceptedCallbackSchemes
    if let bundleIdentifier = Bundle.main.bundleIdentifier {
      payload["bundleIdentifier"] = bundleIdentifier
    }
    payload["authorizationConfigSummary"] = authorizationConfigSummary()
    if authorizationAttemptCount > 0 {
      payload["authorizationAttemptCount"] = authorizationAttemptCount
    }
    if let lastAuthorizationAttemptId {
      payload["lastAuthorizationAttemptId"] = lastAuthorizationAttemptId
    }
    if let lastAuthorizationPhase {
      payload["lastAuthorizationPhase"] = lastAuthorizationPhase
    }
    if let lastAuthorizationDurationMs {
      payload["lastAuthorizationDurationMs"] = lastAuthorizationDurationMs
    }
    if let lastAuthorizationStateBeforeReset {
      payload["lastAuthorizationStateBeforeReset"] = lastAuthorizationStateBeforeReset
    }
    if let lastAuthorizationStateAfterReset {
      payload["lastAuthorizationStateAfterReset"] = lastAuthorizationStateAfterReset
    }
    if let lastAuthorizationStateBeforeAuthenticate {
      payload["lastAuthorizationStateBeforeAuthenticate"] = lastAuthorizationStateBeforeAuthenticate
    }
    if !authDiagnosticTimeline.isEmpty {
      payload["authDiagnosticTimeline"] = authDiagnosticTimeline
    }
    if let lastAuthorizationAppName {
      payload["lastAuthorizationAppName"] = lastAuthorizationAppName
    }
    if let lastAuthorizationScopes {
      payload["lastAuthorizationScopes"] = lastAuthorizationScopes
    }
    if let lastAuthorizationRequestAt {
      payload["lastAuthorizationRequestAt"] = lastAuthorizationRequestAt
    }
    if let lastAuthorizationError {
      payload["lastAuthorizationError"] = lastAuthorizationError
    }
    if let lastAuthorizationErrorAt {
      payload["lastAuthorizationErrorAt"] = lastAuthorizationErrorAt
    }
    if let lastAuthorizationEvent {
      payload["lastAuthorizationEvent"] = lastAuthorizationEvent
    }
    if let lastAuthorizationEventAt {
      payload["lastAuthorizationEventAt"] = lastAuthorizationEventAt
    }
    if let currentDeviceName {
      payload["currentDeviceName"] = currentDeviceName
    }
    if let lastOpenUrlFingerprint {
      payload["lastOpenUrlFingerprint"] = lastOpenUrlFingerprint
    }
    if let lastOpenUrlAt {
      payload["lastOpenUrlAt"] = lastOpenUrlAt
    }
    if let lastOpenUrlExpectedAuthCallback {
      payload["lastOpenUrlExpectedAuthCallback"] = lastOpenUrlExpectedAuthCallback
    }
    payload["cxrClientInitialized"] = cxrClientInitialized()
    payload["cxrInitializationMode"] = cxrInitializationMode()
    payload["cxrInitializationOutcome"] = cxrInitializationOutcome
    if let lastCallbackUrl {
      payload["lastCallbackUrl"] = lastCallbackUrl
    }
    if let lastCallbackAt {
      payload["lastCallbackAt"] = lastCallbackAt
    }
    if let lastCallbackHandled {
      payload["lastCallbackHandled"] = lastCallbackHandled
    }
    payload["querySchemes"] = querySchemes
    payload["sdkClassProbe"] = sdkClassProbe()
    return payload
  }

  private static func openHiRokid(promise: Promise) {
    guard let url = URL(string: "\(companionServerScheme)://"), UIApplication.shared.canOpenURL(url) else {
      recordAuthDiagnostic("companion_open_unavailable", detail: "url=\(companionServerScheme)://")
      promise.resolve(false)
      return
    }

    recordAuthDiagnostic("companion_open_requested", detail: "url=\(companionServerScheme)://")
    DispatchQueue.main.async {
      UIApplication.shared.open(url, options: [:]) { opened in
        recordAuthDiagnostic("companion_open_result", detail: "opened=\(opened)")
        promise.resolve(opened)
      }
    }
  }

  private static func requestAuthorization(scopes: [String], appName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    startAuthorizationAttempt(scopes: scopes, appName: appName)
    ensureCustomViewInitialized()
    recordAuthDiagnostic(
      "cxr_initialization_state",
      detail: "initialized=\(cxrClientInitialized()); mode=\(cxrInitializationMode()); outcome=\(cxrInitializationOutcome)"
    )
    guard cxrClientInitialized() else {
      let reason = "cxr_client_not_initialized:\(cxrInitializationOutcome)"
      recordAuthorizationErrorDescription(reason)
      markAuthorizationPhase("initialize_failed", detail: "\(reason); mode=\(cxrInitializationMode())")
      promise.resolve([
        "ok": false,
        "reason": reason,
        "authorizationState": authorizationState(),
        "authorizationRequestTimeoutSeconds": authorizationRequestTimeoutSeconds,
        "lastAuthorizationAttemptId": lastAuthorizationAttemptId ?? "",
        "authorizationAttemptCount": authorizationAttemptCount,
        "lastAuthorizationPhase": lastAuthorizationPhase ?? "",
        "lastAuthorizationDurationMs": lastAuthorizationDurationMs ?? 0,
        "cxrClientInitialized": cxrClientInitialized(),
        "cxrInitializationMode": cxrInitializationMode(),
        "cxrInitializationOutcome": cxrInitializationOutcome,
      ])
      return
    }
    if CxrClient.shared.auth.isAuthenticated() {
      markAuthorizationPhase("cached_authenticated", detail: "state=authenticated")
      promise.resolve(authorizationSuccessPayload(source: "cached"))
      return
    }
    lastAuthorizationStateBeforeReset = authorizationState()
    recordAuthDiagnostic("state_before_reset", detail: lastAuthorizationStateBeforeReset)
    resetAuthorizationStateForExplicitRequest()
    lastAuthorizationStateAfterReset = authorizationState()
    recordAuthDiagnostic("state_after_reset", detail: lastAuthorizationStateAfterReset)
    configureAuthentication(force: true)
    recordAuthDiagnostic("config_refreshed", detail: authorizationConfigSummary())
    DispatchQueue.main.async {
      lastAuthorizationStateBeforeAuthenticate = authorizationState()
      markAuthorizationPhase("authenticate_invoking", detail: "state=\(lastAuthorizationStateBeforeAuthenticate ?? "unknown")")
      CxrClient.shared.auth.authenticate(
        scopes: scopes,
        bundleId: Bundle.main.bundleIdentifier,
        appName: appName
      ) { result in
        switch result {
        case .success(let authResult):
          markAuthorizationPhase("authenticate_succeeded", detail: "tokenLength=\(authResult.token.count); session=\(authResult.sessionId == nil ? "none" : "present")")
          promise.resolve(authorizationSuccessPayload(
            tokenLength: authResult.token.count,
            sessionId: authResult.sessionId,
            source: "authenticate_completion"
          ))
        case .failure(let error):
          if CxrClient.shared.auth.isAuthenticated() {
            var response = authorizationSuccessPayload(source: "post_failure_state")
            response["nativeWarning"] = String(describing: error)
            markAuthorizationPhase("authenticate_warning_authenticated", detail: String(describing: error))
            promise.resolve(response)
            return
          }
          recordAuthorizationError(error)
          markAuthorizationPhase("authenticate_failed", detail: String(describing: error))
          promise.resolve([
            "ok": false,
            "reason": String(describing: error),
            "authorizationState": authorizationState(),
            "authorizationRequestTimeoutSeconds": authorizationRequestTimeoutSeconds,
            "lastAuthorizationAttemptId": lastAuthorizationAttemptId ?? "",
            "authorizationAttemptCount": authorizationAttemptCount,
            "lastAuthorizationPhase": lastAuthorizationPhase ?? "",
            "lastAuthorizationDurationMs": lastAuthorizationDurationMs ?? 0,
          ])
        }
      }
    }
    #else
    _ = scopes
    _ = appName
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func clearAuthorization() -> Bool {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    CxrClient.shared.auth.clearAuthentication()
    return true
    #else
    return false
    #endif
  }

  private static func openCustomView(_ view: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    recordCustomViewPayload(view)
    recordAuthDiagnostic(
      "custom_view_open_requested",
      detail: "authorized=\(CxrClient.shared.auth.isAuthenticated()); bleConnected=\(iosBleConnected()); bleDevice=\(iosBleDeviceName() ?? "unknown"); bytes=\(view.utf8.count); hash=\(lastCustomViewPayloadHash ?? "unknown"); shape=\(lastCustomViewPayloadShape ?? "unknown"); runningBefore=\(RokidBridgeModule.customViewRunning)"
    )
    guard CxrClient.shared.auth.isAuthenticated() else {
      recordAuthDiagnostic("custom_view_open_blocked", detail: "rokid_not_authorized")
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }
    let bleConnectedBeforeOpen = iosBleConnected()
    let bleDeviceNameBeforeOpen = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
    if !bleConnectedBeforeOpen {
      RokidBridgeModule.lastCustomViewOpenError = "rokid_glasses_ble_not_connected; device=\(bleDeviceNameBeforeOpen); sdk_open_will_still_be_attempted"
    }
    recordAuthDiagnostic(
      "custom_view_ble_preflight",
      detail: "connected=\(bleConnectedBeforeOpen); device=\(bleDeviceNameBeforeOpen); action=attempt_sdk_open"
    )

    let resolutionState = PromiseResolutionState()
    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.openCustomView(view) { success, errorCode in
      DispatchQueue.main.async {
        lastCustomViewOpenCallbackSuccess = success
        lastCustomViewOpenCommandAccepted = success
        lastCustomViewOpenCallbackErrorCode = String(describing: errorCode)
        lastCustomViewOpenCallbackAt = isoTimestamp()
        if success {
          RokidBridgeModule.lastCustomViewOpenError = nil
        } else {
          RokidBridgeModule.customViewRunning = false
          let callbackBleConnected = iosBleConnected()
          let callbackDeviceName = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
          let linkHint = callbackBleConnected ? "ios_ble_connected" : "rokid_glasses_ble_not_connected"
          RokidBridgeModule.lastCustomViewOpenError = "\(linkHint); open_callback_error_code=\(String(describing: errorCode)); device=\(callbackDeviceName)"
        }
        recordAuthDiagnostic(
          "custom_view_open_callback",
          detail: "commandAccepted=\(success); errorCode=\(String(describing: errorCode)); running=\(RokidBridgeModule.customViewRunning); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown")"
        )
        resolveCustomViewOpenPromiseIfNeeded(promise, state: resolutionState, commandAccepted: success)
      }
    }
    #else
    CxrClient.shared.openCustomView(view)
    #endif
    recordAuthDiagnostic(
      "custom_view_open_invoked",
      detail: "bleConnected=\(iosBleConnected()); runningAfterInvoke=\(RokidBridgeModule.customViewRunning); waitingForRunningEvent=\(!RokidBridgeModule.customViewRunning)"
    )
    if RokidBridgeModule.customViewRunning {
      resolveCustomViewOpenPromiseIfNeeded(promise, state: resolutionState, commandAccepted: true)
      return
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + customViewOpenSettleDelaySeconds) {
      let settledCommandAccepted = RokidBridgeModule.customViewRunning
        ? true
        : (RokidBridgeModule.lastCustomViewOpenCommandAccepted ?? false)
      if !RokidBridgeModule.customViewRunning && !settledCommandAccepted && RokidBridgeModule.lastCustomViewOpenError == nil {
        let deviceName = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
        RokidBridgeModule.lastCustomViewOpenError = "rokid_custom_view_not_running_after_open; iosBleConnected=\(iosBleConnected()); device=\(deviceName)"
      }
      recordAuthDiagnostic(
        "custom_view_open_settled",
        detail: "running=\(RokidBridgeModule.customViewRunning); commandAccepted=\(settledCommandAccepted); rawNotify=\(lastCustomViewRawNotify ?? "none"); openError=\(lastCustomViewOpenError ?? "none")"
      )
      resolveCustomViewOpenPromiseIfNeeded(promise, state: resolutionState, commandAccepted: settledCommandAccepted)
    }
    #else
    _ = view
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func updateCustomView(_ view: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard RokidBridgeModule.customViewRunning else {
      promise.resolve(["ok": false, "reason": "rokid_custom_view_not_ready"])
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.updateCustomView(view) { updated in
      DispatchQueue.main.async {
        recordAuthDiagnostic("custom_view_update_callback", detail: "commandAccepted=\(updated)")
        promise.resolve(customViewCommandPayload(commandAccepted: updated))
      }
    }
    #else
    CxrClient.shared.updateCustomView(view)
    promise.resolve(customViewCommandPayload(commandAccepted: true))
    #endif
    #else
    _ = view
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func closeCustomView(_ view: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.closeCustomView(view) { closed in
      DispatchQueue.main.async {
        if closed {
          RokidBridgeModule.customViewRunning = false
        }
        recordAuthDiagnostic(
          "custom_view_close_callback",
          detail: "commandAccepted=\(closed); running=\(RokidBridgeModule.customViewRunning)"
        )
        promise.resolve(customViewCommandPayload(commandAccepted: closed))
      }
    }
    #else
    CxrClient.shared.closeCustomView(view)
    RokidBridgeModule.customViewRunning = false
    promise.resolve(customViewCommandPayload(commandAccepted: true))
    #endif
    #else
    _ = view
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func takePhotoBase64(width: Int, height: Int, quality: Int, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }
    guard RokidBridgeModule.customViewRunning else {
      promise.resolve(["ok": false, "reason": "rokid_custom_view_not_ready"])
      return
    }

    CxrClient.shared.takePhotoWithData(width: width, height: height, quality: quality) { data in
      promise.resolve([
        "ok": true,
        "base64": data.base64EncodedString(),
        "mimeType": "image/jpeg",
        "byteLength": data.count,
      ])
    }
    #else
    _ = width
    _ = height
    _ = quality
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func queryApp(packageName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "installed": false, "reason": "rokid_not_authorized"])
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.queryApp { installed in
      promise.resolve([
        "ok": true,
        "installed": installed,
        "packageName": packageName,
      ])
    }
    #else
    CxrClient.shared.queryApp(packageName: packageName) { installed in
      promise.resolve([
        "ok": true,
        "installed": installed,
        "packageName": packageName,
      ])
    }
    #endif
    #else
    _ = packageName
    promise.resolve(["ok": false, "installed": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func installBundledApp(
    resourceName: String,
    resourceExtension: String,
    packageName: String,
    promise: Promise
  ) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "installed": false, "reason": "rokid_not_authorized"])
      return
    }
    guard let apkURL = Bundle.main.url(forResource: resourceName, withExtension: resourceExtension) ??
      Bundle.main.url(forResource: resourceName, withExtension: resourceExtension, subdirectory: "RokidApps") else {
      promise.resolve([
        "ok": false,
        "installed": false,
        "reason": "rokid_apk_resource_missing",
        "resourceName": resourceName,
        "resourceExtension": resourceExtension,
        "packageName": packageName,
      ])
      return
    }
    installAppAtPath(
      apkURL.path,
      packageName: packageName,
      source: "bundle",
      promise: promise
    )
    #else
    _ = resourceName
    _ = resourceExtension
    _ = packageName
    promise.resolve(["ok": false, "installed": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func installAppFileUri(fileUri: String, packageName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "installed": false, "reason": "rokid_not_authorized"])
      return
    }
    let path: String
    if let url = URL(string: fileUri), url.isFileURL {
      path = url.path
    } else {
      path = fileUri
    }
    installAppAtPath(
      path,
      packageName: packageName,
      source: "file_uri",
      promise: promise
    )
    #else
    _ = fileUri
    _ = packageName
    promise.resolve(["ok": false, "installed": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func uninstallApp(packageName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "uninstalled": false, "reason": "rokid_not_authorized"])
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.uninstallApp { uninstalled in
      promise.resolve([
        "ok": uninstalled,
        "uninstalled": uninstalled,
        "packageName": packageName,
      ])
    }
    #else
    CxrClient.shared.uninstallApp(packageName) { uninstalled in
      promise.resolve([
        "ok": uninstalled,
        "uninstalled": uninstalled,
        "packageName": packageName,
      ])
    }
    #endif
    #else
    _ = packageName
    promise.resolve(["ok": false, "uninstalled": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func openApp(packageName: String, activityName: String, url: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "opened": false, "reason": "rokid_not_authorized"])
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.openApp(activityName: activityName, url: url) { opened in
      promise.resolve([
        "ok": opened,
        "opened": opened,
        "packageName": packageName,
        "activityName": activityName,
      ])
    }
    #else
    CxrClient.shared.openApp(packageName: packageName, activityName: activityName, url: url) { opened in
      promise.resolve([
        "ok": opened,
        "opened": opened,
        "packageName": packageName,
        "activityName": activityName,
      ])
    }
    #endif
    #else
    _ = packageName
    _ = activityName
    _ = url
    promise.resolve(["ok": false, "opened": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func stopApp(packageName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "stopped": false, "reason": "rokid_not_authorized"])
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.stopApp { stopped in
      promise.resolve([
        "ok": stopped,
        "stopped": stopped,
        "packageName": packageName,
      ])
    }
    #else
    CxrClient.shared.stopApp(packageName) { stopped in
      promise.resolve([
        "ok": stopped,
        "stopped": stopped,
        "packageName": packageName,
      ])
    }
    #endif
    #else
    _ = packageName
    promise.resolve(["ok": false, "stopped": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func startRecord(type: String, codec: String, mode: String) -> [String: Any] {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      return ["ok": false, "reason": "rokid_not_authorized"]
    }
    guard RokidBridgeModule.customViewRunning else {
      return ["ok": false, "reason": "rokid_custom_view_not_ready"]
    }

    CxrClient.shared.startRecord(type, codec: audioCodec(codec), mode: audioMode(mode))
    return ["ok": true]
    #else
    _ = type
    _ = codec
    _ = mode
    return ["ok": false, "reason": "ios_sdk_not_linked"]
    #endif
  }

  private static func stopRecord(type: String) -> [String: Any] {
    #if canImport(RGCxrClient)
    CxrClient.shared.stopRecord(type)
    return ["ok": true]
    #else
    _ = type
    return ["ok": false, "reason": "ios_sdk_not_linked"]
    #endif
  }

  private static func customViewCommandPayload(commandAccepted: Bool) -> [String: Any] {
    let running = isCustomViewRunning()
    var response: [String: Any] = [:]
    response["ok"] = commandAccepted
    response["customViewCommandAccepted"] = commandAccepted
    response["customViewRunning"] = running
    response["capabilitiesReady"] = capabilitiesReady()
    response["iosBleConnected"] = iosBleConnected()
    if let bleDeviceName = iosBleDeviceName() {
      response["iosBleDeviceName"] = bleDeviceName
    }
    if let lastCustomViewPayloadHash {
      response["lastCustomViewPayloadHash"] = lastCustomViewPayloadHash
    }
    if let lastCustomViewPayloadShape {
      response["lastCustomViewPayloadShape"] = lastCustomViewPayloadShape
    }
    if let lastCustomViewPayloadBytes {
      response["lastCustomViewPayloadBytes"] = lastCustomViewPayloadBytes
    }
    if let lastCustomViewCommandAt {
      response["lastCustomViewCommandAt"] = lastCustomViewCommandAt
    }
    if let lastCustomViewRawNotify {
      response["lastCustomViewRawNotify"] = lastCustomViewRawNotify
    }
    if let lastCustomViewRawNotifyAt {
      response["lastCustomViewRawNotifyAt"] = lastCustomViewRawNotifyAt
    }
    if let lastCustomViewOpenError {
      response["lastCustomViewOpenError"] = lastCustomViewOpenError
    }
    if let lastCustomViewOpenCommandAccepted {
      response["lastCustomViewOpenCommandAccepted"] = lastCustomViewOpenCommandAccepted
    }
    if let lastCustomViewOpenCallbackSuccess {
      response["lastCustomViewOpenCallbackSuccess"] = lastCustomViewOpenCallbackSuccess
    }
    if let lastCustomViewOpenCallbackErrorCode {
      response["lastCustomViewOpenCallbackErrorCode"] = lastCustomViewOpenCallbackErrorCode
    }
    if let lastCustomViewOpenCallbackAt {
      response["lastCustomViewOpenCallbackAt"] = lastCustomViewOpenCallbackAt
    }
    if !commandAccepted {
      response["reason"] = lastCustomViewOpenError ?? "rokid_custom_view_open_not_accepted"
    }
    response["pendingSessionEvent"] = commandAccepted && !running
    return response
  }

  private static func resolveCustomViewOpenPromiseIfNeeded(
    _ promise: Promise,
    state: PromiseResolutionState,
    commandAccepted: Bool
  ) {
    guard !state.resolved else {
      return
    }
    state.resolved = true
    promise.resolve(customViewCommandPayload(commandAccepted: commandAccepted))
  }

  #if canImport(RGCxrClient)
  private static func authorizationSuccessPayload(
    tokenLength: Int? = nil,
    sessionId: String? = nil,
    source: String
  ) -> [String: Any] {
    clearAuthorizationError()
    var response: [String: Any] = [:]
    response["ok"] = true
    response["authorizationState"] = "authenticated"
    response["source"] = source
    response["tokenLength"] = tokenLength ?? CxrClient.shared.auth.currentToken?.count ?? 0
    response["authorizationRequestTimeoutSeconds"] = authorizationRequestTimeoutSeconds
    if let resolvedSessionId = sessionId ?? CxrClient.shared.auth.currentSessionId {
      response["sessionId"] = resolvedSessionId
    }
    if let lastCallbackUrl {
      response["lastCallbackUrl"] = lastCallbackUrl
    }
    if let lastCallbackHandled {
      response["lastCallbackHandled"] = lastCallbackHandled
    }
    return response
  }
  #endif

  #if canImport(RGCxrClient)
  private static func installAppAtPath(
    _ path: String,
    packageName: String,
    source: String,
    promise: Promise
  ) {
    guard FileManager.default.fileExists(atPath: path) else {
      promise.resolve([
        "ok": false,
        "installed": false,
        "reason": "rokid_apk_file_missing",
        "packageName": packageName,
      ])
      return
    }

    let attributes = try? FileManager.default.attributesOfItem(atPath: path)
    let byteLength = (attributes?[.size] as? NSNumber)?.uint64Value
    let fileName = URL(fileURLWithPath: path).lastPathComponent
    CxrClient.shared.installApp(path) { installed in
      var response: [String: Any] = [:]
      response["ok"] = installed
      response["installed"] = installed
      response["packageName"] = packageName
      response["source"] = source
      response["apkFileName"] = fileName
      if let byteLength {
        response["byteLength"] = byteLength
      }
      promise.resolve(response)
    }
  }
  #endif

  private static func canOpenHiRokid() -> Bool {
    guard let url = URL(string: "\(companionServerScheme)://") else {
      return false
    }
    return UIApplication.shared.canOpenURL(url)
  }

  private static let beijingTimeZone = TimeZone(secondsFromGMT: 8 * 60 * 60)!

  private static func isoTimestamp() -> String {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    formatter.timeZone = beijingTimeZone
    return formatter.string(from: Date())
  }

  private static func uniqueSchemes(_ schemes: [String]) -> [String] {
    var result: [String] = []
    var seen: Set<String> = []
    for rawScheme in schemes {
      let scheme = rawScheme.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !scheme.isEmpty else {
        continue
      }
      let normalized = scheme.lowercased()
      guard !seen.contains(normalized) else {
        continue
      }
      seen.insert(normalized)
      result.append(scheme)
    }
    return result
  }

  private static func authorizationConfigSummary() -> String {
    let callback = "\(callbackScheme)://\(callbackHost)\(callbackPath)"
    return "server=\(companionServerScheme)://\(companionServerHost); callback=\(callback); timeout=\(Int(authorizationRequestTimeoutSeconds))s"
  }

  private static func clearCallbackRouteStateForNewAttempt() {
    lastCallbackUrl = nil
    lastCallbackAt = nil
    lastCallbackHandled = nil
    lastOpenUrlFingerprint = nil
    lastOpenUrlAt = nil
    lastOpenUrlExpectedAuthCallback = nil
  }

  private static func startAuthorizationAttempt(scopes: [String], appName: String) {
    authorizationAttemptCount += 1
    lastAuthorizationAttemptId = "auth-\(authorizationAttemptCount)"
    lastAuthorizationStartedAt = Date()
    lastAuthorizationDurationMs = nil
    lastAuthorizationPhase = "request_started"
    lastAuthorizationStateBeforeReset = nil
    lastAuthorizationStateAfterReset = nil
    lastAuthorizationStateBeforeAuthenticate = nil
    lastAuthorizationAppName = appName
    lastAuthorizationScopes = scopes
    lastAuthorizationRequestAt = isoTimestamp()
    clearAuthorizationError()
    clearCallbackRouteStateForNewAttempt()
    recordAuthDiagnostic(
      "request_started",
      detail: "appName=\(appName); scopes=\(scopes.joined(separator: ",")); bundle=\(Bundle.main.bundleIdentifier ?? "unknown"); \(authorizationConfigSummary())"
    )
  }

  @discardableResult
  private static func markAuthorizationPhase(_ phase: String, detail: String? = nil) -> Int? {
    lastAuthorizationPhase = phase
    if let startedAt = lastAuthorizationStartedAt {
      lastAuthorizationDurationMs = Int(Date().timeIntervalSince(startedAt) * 1000)
    }
    recordAuthDiagnostic(phase, detail: detail)
    return lastAuthorizationDurationMs
  }

  private static func recordAuthDiagnostic(_ phase: String, detail: String? = nil) {
    let attempt = lastAuthorizationAttemptId ?? "no-attempt"
    let cleanDetail = detail.map(sanitizeAuthDiagnosticDetail)
    let line = [
      isoTimestamp(),
      "#\(attempt)",
      phase,
      cleanDetail,
    ]
      .compactMap { $0 }
      .filter { !$0.isEmpty }
      .joined(separator: " ")
    authDiagnosticTimeline.append(line)
    if authDiagnosticTimeline.count > authDiagnosticTimelineLimit {
      authDiagnosticTimeline.removeFirst(authDiagnosticTimeline.count - authDiagnosticTimelineLimit)
    }
    NSLog("[RevaRokidAuth] %@", line)
  }

  private static func sanitizeAuthDiagnosticDetail(_ detail: String) -> String {
    let sanitized = detail
      .replacingOccurrences(of: "\n", with: " ")
      .replacingOccurrences(of: "\r", with: " ")
    if sanitized.count <= 480 {
      return sanitized
    }
    return "\(sanitized.prefix(480))..."
  }

  private static func recordCustomViewPayload(_ view: String) {
    lastCustomViewPayloadBytes = view.utf8.count
    lastCustomViewPayloadHash = fnv1a64Hex(view)
    lastCustomViewPayloadShape = customViewPayloadShape(view)
    lastCustomViewCommandAt = isoTimestamp()
    lastCustomViewOpenError = nil
    lastCustomViewOpenCommandAccepted = nil
    lastCustomViewOpenCallbackSuccess = nil
    lastCustomViewOpenCallbackErrorCode = nil
    lastCustomViewOpenCallbackAt = nil
  }

  private static func fnv1a64Hex(_ value: String) -> String {
    var hash: UInt64 = 0xcbf29ce484222325
    for byte in value.utf8 {
      hash = (hash ^ UInt64(byte)) &* 0x100000001b3
    }
    return String(format: "fnv1a64:%016llx", hash)
  }

  private static func customViewPayloadShape(_ view: String) -> String {
    guard let data = view.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data),
      let root = object as? [String: Any] else {
      return "invalid_json"
    }
    let rootType = root["type"] as? String ?? "unknown"
    let propKeys = (root["props"] as? [String: Any])?.keys.sorted().joined(separator: ",") ?? "none"
    let children = root["children"] as? [[String: Any]] ?? []
    let childTypes = children.compactMap { $0["type"] as? String }.joined(separator: ",")
    let childIds = children.compactMap { child -> String? in
      (child["props"] as? [String: Any])?["id"] as? String
    }.joined(separator: ",")
    var parts = [
      "root=\(rootType)",
      "props=\(propKeys)",
      "children=\(children.count):\(childTypes.isEmpty ? "none" : childTypes)",
    ]
    if !childIds.isEmpty {
      parts.append("ids=\(childIds)")
    }
    return parts.joined(separator: "; ")
  }

  private static func recordAuthorizationError(_ error: Error) {
    recordAuthorizationErrorDescription(String(describing: error))
  }

  private static func recordAuthorizationErrorDescription(_ error: String) {
    lastAuthorizationError = error
    lastAuthorizationErrorAt = isoTimestamp()
    recordAuthDiagnostic("authorization_error", detail: error)
  }

  private static func clearAuthorizationError() {
    lastAuthorizationError = nil
    lastAuthorizationErrorAt = nil
  }

  private static func recordAuthorizationEvent(_ event: String) {
    lastAuthorizationEvent = event
    lastAuthorizationEventAt = isoTimestamp()
    recordAuthDiagnostic("sdk_event", detail: event)
  }

  #if canImport(RGCxrClient)
  private static func resetAuthorizationStateForExplicitRequest() {
    switch CxrClient.shared.auth.currentState {
    case .authenticated(_, _):
      return
    case .notAuthenticated, .authenticating, .expired:
      CxrClient.shared.auth.clearAuthentication()
    case .failed(_):
      CxrClient.shared.auth.clearAuthentication()
    @unknown default:
      CxrClient.shared.auth.clearAuthentication()
    }
  }
  #endif

  private static func ensureCustomViewInitialized() {
    #if canImport(RGCxrClient)
    let initializeConfigureAndBind = {
    #if ROKID_CXRL_CALLBACK_API
      let initializedBefore = CxrClient.isInitialized
      if !RokidBridgeModule.didInitializeCustomView || !initializedBefore {
        let outcome = CxrClient.initialize(
          mode: .customView,
          options: RGCxrClientInitializationOptions(appDisplayName: nil, pageName: nil)
        )
        let outcomeDescription = cxrInitializeOutcomeDescription(outcome)
        let initializedAfter = CxrClient.isInitialized
        RokidBridgeModule.cxrInitializationOutcome = outcomeDescription
        RokidBridgeModule.didInitializeCustomView = initializedAfter
        recordAuthDiagnostic(
          "cxr_initialize",
          detail: "before=\(initializedBefore); outcome=\(outcomeDescription); after=\(initializedAfter); mode=\(cxrInitializationMode())"
        )
      }
    #else
      if !RokidBridgeModule.didInitializeCustomView {
        RokidBridgeModule.cxrInitializationOutcome = "legacy_client_no_initialize_api"
        RokidBridgeModule.didInitializeCustomView = true
      }
    #endif
      configureAuthentication()
      bindRuntimeEvents()
    }
    if Thread.isMainThread {
      initializeConfigureAndBind()
    } else {
      DispatchQueue.main.sync(execute: initializeConfigureAndBind)
    }
    #endif
  }

  #if canImport(RGCxrClient) && ROKID_CXRL_CALLBACK_API
  private static func cxrInitializeOutcomeDescription(_ outcome: RGCxrClientInitializeOutcome) -> String {
    switch outcome {
    case .success:
      return "success"
    case .failureAlreadyInitialized:
      return "failure_already_initialized"
    @unknown default:
      return "unknown"
    }
  }
  #endif

  private static func configureAuthentication(force: Bool = false) {
    #if canImport(RGCxrClient)
    let configure = {
      guard force || !RokidBridgeModule.didConfigureAuthentication else {
        return
      }
      RokidBridgeModule.didConfigureAuthentication = true
      CxrClient.shared.auth.config = RGCxrClientAuthConfig(
        serverScheme: companionServerScheme,
        serverHost: companionServerHost,
        callbackScheme: callbackScheme,
        callbackHost: callbackHost,
        callbackPath: callbackPath,
        requestTimeout: authorizationRequestTimeoutSeconds
      )
    }
    if Thread.isMainThread {
      configure()
    } else {
      DispatchQueue.main.sync(execute: configure)
    }
    #endif
  }

  private static func bindRuntimeEvents() {
    #if canImport(RGCxrClient)
    guard !RokidBridgeModule.didBindRuntimeEvents else {
      return
    }
    RokidBridgeModule.didBindRuntimeEvents = true
    CxrClient.shared.customViewRunningEventPublisher
      .receive(on: DispatchQueue.main)
      .sink { event in
        RokidBridgeModule.customViewRunning = event.isRunning
        RokidBridgeModule.recordAuthDiagnostic("custom_view_event", detail: "isRunning=\(event.isRunning)")
      }
      .store(in: &RokidBridgeModule.cancellables)
    configureCustomViewNotifySubscription()
    CxrClient.shared.auth.eventPublisher
      .receive(on: DispatchQueue.main)
      .sink { event in
        RokidBridgeModule.handleAuthorizationEvent(event)
      }
      .store(in: &RokidBridgeModule.cancellables)
    RGCxrClientBLE.shared.connectionStatePublisher
      .receive(on: DispatchQueue.main)
      .sink { connected in
        if connected, let deviceName = RGCxrClientBLE.shared.connectedDeviceName, !deviceName.isEmpty {
          RokidBridgeModule.currentDeviceName = deviceName
        }
        RokidBridgeModule.recordAuthDiagnostic(
          "ble_connection_event",
          detail: "connected=\(connected); device=\(RGCxrClientBLE.shared.connectedDeviceName ?? "unknown")"
        )
      }
      .store(in: &RokidBridgeModule.cancellables)
    RGCxrClientBLE.shared.notifyPublisher
      .receive(on: DispatchQueue.main)
      .sink { notify in
        RokidBridgeModule.handleCustomViewNotify(notify)
      }
      .store(in: &RokidBridgeModule.cancellables)
    #endif
  }

  #if canImport(RGCxrClient)
  private static func configureCustomViewNotifySubscription() {
    #if ROKID_CXRL_CALLBACK_API
    let commands = [
      RGCxrSubCmd.Custom_View_Opened.rawValue,
      RGCxrSubCmd.Custom_View_Open_Failed.rawValue,
      RGCxrSubCmd.Custom_View_Updated.rawValue,
      RGCxrSubCmd.Custom_View_Closed.rawValue,
    ]
    CxrClient.shared.setNotifyEventListenCmds(commands)
    recordAuthDiagnostic("custom_view_notify_subscription", detail: "mode=setNotifyEventListenCmds; commands=\(commands.joined(separator: ","))")
    #else
    recordAuthDiagnostic("custom_view_notify_subscription", detail: "mode=legacy_notify_publisher_only")
    #endif
  }

  private static func handleCustomViewNotify(_ notify: String) {
    let cleanNotify = sanitizeAuthDiagnosticDetail(notify)
    guard isCustomViewNotify(cleanNotify) else {
      return
    }
    lastCustomViewRawNotify = cleanNotify
    lastCustomViewRawNotifyAt = isoTimestamp()

    let normalized = cleanNotify.lowercased()
    if normalized.contains("custom_view_opened") {
      lastCustomViewOpenCommandAccepted = true
      lastCustomViewOpenError = nil
    } else if normalized.contains("custom_view_open_failed") {
      customViewRunning = false
      lastCustomViewOpenError = cleanNotify
    } else if normalized.contains("custom_view_closed") || normalized.contains("close_custom_view") {
      customViewRunning = false
    }
    recordAuthDiagnostic("custom_view_notify", detail: cleanNotify)
  }

  private static func isCustomViewNotify(_ notify: String) -> Bool {
    let normalized = notify.lowercased()
    return normalized.contains("custom_view") || normalized.contains("customview")
  }

  private static func handleAuthorizationEvent(_ event: RGCxrClientAuthEvent) {
    switch event {
    case .stateChanged(let state):
      let stateDescription = authorizationStateDescription(state)
      recordAuthorizationEvent("stateChanged:\(stateDescription)")
      if case .failed(let error) = state {
        recordAuthorizationErrorDescription(error)
      }
    case .authenticationSucceeded(_, let sessionId, let deviceName):
      clearAuthorizationError()
      if let deviceName, !deviceName.isEmpty {
        currentDeviceName = deviceName
      }
      if let sessionId, !sessionId.isEmpty {
        recordAuthorizationEvent("authenticationSucceeded:session")
      } else {
        recordAuthorizationEvent("authenticationSucceeded")
      }
    case .authenticationFailed(let error):
      recordAuthorizationErrorDescription(error)
      recordAuthorizationEvent("authenticationFailed:\(error)")
    case .tokenExpired:
      recordAuthorizationEvent("tokenExpired")
    @unknown default:
      recordAuthorizationEvent("unknown")
    }
  }

  private static func authorizationStateDescription(_ state: RGCxrClientAuthState) -> String {
    switch state {
    case .notAuthenticated:
      return "not_authenticated"
    case .authenticating:
      return "authenticating"
    case .authenticated(_, _):
      return "authenticated"
    case .expired:
      return "expired"
    case .failed(let error):
      return "failed:\(error)"
    @unknown default:
      return "unknown"
    }
  }
  #endif

  private static func sdkLinked() -> Bool {
    #if canImport(RGCxrClient)
    return true
    #else
    return false
    #endif
  }

  private static func sdkDependencyMode() -> String {
    #if canImport(RGCxrClient)
    return "linked"
    #elseif ROKID_IOS_SIMULATOR_EXCLUDED
    return "simulator_excluded"
    #elseif ROKID_IOS_SDK_REQUESTED
    return "requested_but_unlinked"
    #else
    return "opt_in_disabled"
    #endif
  }

  private static func sdkLinkedReason() -> String {
    #if canImport(RGCxrClient)
    #if ROKID_CXRL_CALLBACK_API
    return "can_import_RGCxrClient_with_callback_api"
    #else
    return "can_import_RGCxrClient_legacy_api"
    #endif
    #elseif ROKID_IOS_SIMULATOR_EXCLUDED
    return "simulator_excluded"
    #elseif ROKID_IOS_SDK_REQUESTED
    #if ROKID_CXRL_CALLBACK_API
    return "sdk_requested_callback_macro_but_RGCxrClient_unavailable"
    #else
    return "sdk_requested_but_RGCxrClient_unavailable"
    #endif
    #else
    return "sdk_opt_in_disabled"
    #endif
  }

  private static func cxrCallbackApiEnabled() -> Bool {
    #if ROKID_CXRL_CALLBACK_API
    return true
    #else
    return false
    #endif
  }

  private static func cxrNotifySubscriptionMode() -> String {
    #if ROKID_CXRL_CALLBACK_API
    return "setNotifyEventListenCmds"
    #elseif canImport(RGCxrClient)
    return "legacy_notify_publisher_only"
    #else
    return "unavailable"
    #endif
  }

  private static func authorizationState() -> String {
    #if canImport(RGCxrClient)
    switch CxrClient.shared.auth.currentState {
    case .notAuthenticated:
      return "not_authenticated"
    case .authenticating:
      return "authenticating"
    case .authenticated(_, _):
      return "authenticated"
    case .expired:
      return "expired"
    case .failed(_):
      return "failed"
    @unknown default:
      return "unknown"
    }
    #else
    return "unknown"
    #endif
  }

  private static func isCustomViewRunning() -> Bool {
    #if canImport(RGCxrClient)
    return RokidBridgeModule.customViewRunning
    #else
    return false
    #endif
  }

  private static func capabilitiesReady() -> Bool {
    #if canImport(RGCxrClient)
    return CxrClient.shared.auth.isAuthenticated() && RokidBridgeModule.customViewRunning
    #else
    return false
    #endif
  }

  private static func iosBleConnected() -> Bool {
    #if canImport(RGCxrClient)
    return RGCxrClientBLE.shared.isConnected
    #else
    return false
    #endif
  }

  private static func iosBleDeviceName() -> String? {
    #if canImport(RGCxrClient)
    return RGCxrClientBLE.shared.connectedDeviceName
    #else
    return nil
    #endif
  }

  private static func cxrClientInitialized() -> Bool {
    #if canImport(RGCxrClient)
    #if ROKID_CXRL_CALLBACK_API
    return CxrClient.isInitialized
    #else
    return true
    #endif
    #else
    return false
    #endif
  }

  private static func cxrInitializationMode() -> String {
    #if canImport(RGCxrClient)
    #if ROKID_CXRL_CALLBACK_API
    guard let mode = CxrClient.initializationMode else {
      return "not_initialized"
    }
    switch mode {
    case .customView:
      return "customView"
    case .customApp:
      return "customApp"
    @unknown default:
      return "unknown"
    }
    #else
    return "legacy_client_no_initialize_api"
    #endif
    #else
    return "unknown"
    #endif
  }

  fileprivate static func isExpectedAuthCallback(_ url: URL) -> Bool {
    guard let urlScheme = url.scheme, acceptedCallbackSchemes.contains(where: {
      $0.caseInsensitiveCompare(urlScheme) == .orderedSame
    }) else {
      return false
    }

    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    if CxrClient.shared.auth.canHandleURL(url) {
      return true
    }
    #endif
    // The callback scheme is app-private; let the SDK inspect vendor path/query variants.
    return true
  }

  fileprivate static func observeOpenURL(_ url: URL) {
    lastOpenUrlFingerprint = urlFingerprint(url)
    lastOpenUrlAt = isoTimestamp()
    lastOpenUrlExpectedAuthCallback = isExpectedAuthCallback(url)
    recordAuthDiagnostic(
      "ios_open_url",
      detail: "\(lastOpenUrlFingerprint ?? "unknown"); expectedAuthCallback=\(lastOpenUrlExpectedAuthCallback == true)"
    )
  }

  private static func urlFingerprint(_ url: URL) -> String {
    let scheme = url.scheme ?? "unknown"
    let host = url.host ?? ""
    let path = url.path
    if !host.isEmpty {
      return "\(scheme)://\(host)\(path)"
    }
    if !path.isEmpty {
      return "\(scheme):\(path)"
    }
    return "\(scheme)://"
  }

  fileprivate static func handleOpenURL(_ url: URL) -> Bool {
    guard isExpectedAuthCallback(url) else {
      recordAuthDiagnostic("callback_ignored", detail: urlFingerprint(url))
      return false
    }

    lastCallbackUrl = url.absoluteString
    lastCallbackAt = isoTimestamp()
    recordAuthDiagnostic("callback_received", detail: urlFingerprint(url))

    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    let handledByAuth = CxrClient.shared.auth.handleCallback(url: url)
    let handledByClient = CxrClient.shared.handleOpenURL(url)
    let handled = handledByAuth || handledByClient || CxrClient.shared.auth.isAuthenticated()
    lastCallbackHandled = handled
    recordAuthDiagnostic(
      "callback_handled",
      detail: "authCallbackHandled=\(handledByAuth); clientOpenUrlHandled=\(handledByClient); authenticated=\(CxrClient.shared.auth.isAuthenticated())"
    )
    return handled
    #else
    lastCallbackHandled = false
    recordAuthDiagnostic("callback_unhandled", detail: "ios_sdk_not_linked")
    return false
    #endif
  }

  private static func sdkClassProbe() -> [String: Bool] {
    [
      "RGCxrClient.CxrClient": classExists("RGCxrClient.CxrClient"),
      "RGCxrClient": classExists("RGCxrClient"),
      "RGCoreKit": classExists("RGCoreKit"),
    ]
  }

  private static func classExists(_ className: String) -> Bool {
    NSClassFromString(className) != nil
  }

  #if canImport(RGCxrClient)
  private static func audioCodec(_ codec: String) -> RGCxrAudioCodec {
    switch codec.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "oggopus", "ogg_opus", "opus":
      return .oggOpus
    case "mp3":
      return .mp3
    default:
      return .pcm
    }
  }

  private static func audioMode(_ mode: String) -> RGCxrAudioMode {
    switch mode.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "xf":
      return .xf
    case "antclose", "ant_close":
      return .antClose
    case "antomni", "ant_omni":
      return .antOmni
    case "xforientation", "xf_orientation":
      return .xfOrientation
    case "barrierfree", "barrier_free":
      return .barrierFree
    default:
      return .rokidOmni
    }
  }
  #endif
}

@objc public class RokidBridgeURLHandler: NSObject {
  @objc public static func observeOpenURL(_ url: URL) {
    RokidBridgeModule.observeOpenURL(url)
  }

  @objc public static func canHandleOpenURL(_ url: URL) -> Bool {
    RokidBridgeModule.isExpectedAuthCallback(url)
  }

  @objc public static func handleOpenURL(_ url: URL) -> Bool {
    RokidBridgeModule.handleOpenURL(url)
  }
}
