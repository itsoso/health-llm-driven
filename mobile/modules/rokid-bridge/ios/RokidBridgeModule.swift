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

public class RokidBridgeModule: Module {
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
    payload["iosSdkDependencyMode"] = sdkDependencyMode()
    payload["iosSdkCompatibility"] = "CXR-L iOS public sample uses RGCxrClient 1.0.1; 1.0.2 requires Rokid specs source"
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
    ensureCustomViewInitialized()
    startAuthorizationAttempt(scopes: scopes, appName: appName)
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
    recordAuthDiagnostic(
      "custom_view_open_requested",
      detail: "authorized=\(CxrClient.shared.auth.isAuthenticated()); bleConnected=\(iosBleConnected()); bleDevice=\(iosBleDeviceName() ?? "unknown"); bytes=\(view.utf8.count); runningBefore=\(RokidBridgeModule.customViewRunning)"
    )
    guard CxrClient.shared.auth.isAuthenticated() else {
      recordAuthDiagnostic("custom_view_open_blocked", detail: "rokid_not_authorized")
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }

    CxrClient.shared.openCustomView(view)
    recordAuthDiagnostic(
      "custom_view_open_invoked",
      detail: "bleConnected=\(iosBleConnected()); runningAfterInvoke=\(RokidBridgeModule.customViewRunning); waitingForRunningEvent=\(!RokidBridgeModule.customViewRunning)"
    )
    promise.resolve(customViewCommandPayload(commandAccepted: true))
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

    CxrClient.shared.updateCustomView(view)
    promise.resolve(customViewCommandPayload(commandAccepted: true))
    #else
    _ = view
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func closeCustomView(_ view: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    CxrClient.shared.closeCustomView(view)
    RokidBridgeModule.customViewRunning = false
    promise.resolve(customViewCommandPayload(commandAccepted: true))
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

    CxrClient.shared.queryApp(packageName: packageName) { installed in
      promise.resolve([
        "ok": true,
        "installed": installed,
        "packageName": packageName,
      ])
    }
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

    CxrClient.shared.uninstallApp(packageName) { uninstalled in
      promise.resolve([
        "ok": uninstalled,
        "uninstalled": uninstalled,
        "packageName": packageName,
      ])
    }
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

    CxrClient.shared.openApp(packageName: packageName, activityName: activityName, url: url) { opened in
      promise.resolve([
        "ok": opened,
        "opened": opened,
        "packageName": packageName,
        "activityName": activityName,
      ])
    }
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

    CxrClient.shared.stopApp(packageName) { stopped in
      promise.resolve([
        "ok": stopped,
        "stopped": stopped,
        "packageName": packageName,
      ])
    }
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
    response["pendingSessionEvent"] = commandAccepted && !running
    return response
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

  private static func isoTimestamp() -> String {
    ISO8601DateFormatter().string(from: Date())
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
    detail
      .replacingOccurrences(of: "\n", with: " ")
      .replacingOccurrences(of: "\r", with: " ")
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
    if !RokidBridgeModule.didInitializeCustomView {
      RokidBridgeModule.cxrInitializationOutcome = "legacy_client_no_initialize_api"
      RokidBridgeModule.didInitializeCustomView = true
    }
    configureAuthentication()
    bindRuntimeEvents()
    #endif
  }

  private static func configureAuthentication(force: Bool = false) {
    #if canImport(RGCxrClient)
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
    #endif
  }

  #if canImport(RGCxrClient)
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
    return true
    #else
    return false
    #endif
  }

  private static func cxrInitializationMode() -> String {
    #if canImport(RGCxrClient)
    return "implicit_legacy_client"
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
    configureAuthentication()
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
    let handledByClient = handledByAuth ? false : CxrClient.shared.handleOpenURL(url)
    let handled = handledByAuth || handledByClient || CxrClient.shared.auth.isAuthenticated()
    lastCallbackHandled = handled
    recordAuthDiagnostic(
      "callback_handled",
      detail: "handledByAuth=\(handledByAuth); handledByClient=\(handledByClient); authenticated=\(CxrClient.shared.auth.isAuthenticated())"
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
