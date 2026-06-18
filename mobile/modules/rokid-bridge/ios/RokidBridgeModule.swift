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
  private static let callbackScheme = "life.executor.health.rokid"
  private static let callbackHost = "auth"
  private static let callbackPath = "/callback"
  private static let querySchemes = ["rokidai"]
  private static var didConfigureAuthentication = false
  private static var didInitializeCustomView = false
  private static var didBindRuntimeEvents = false
  private static var customViewRunning = false
  private static var cxrInitializationOutcome = "not_started"
  private static var lastCallbackUrl: String?
  private static var lastCallbackAt: String?
  private static var lastCallbackHandled: Bool?
  #if canImport(RGCxrClient)
  private static var cancellables = Set<AnyCancellable>()
  #endif

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
    payload["customViewRunning"] = isCustomViewRunning()
    payload["capabilitiesReady"] = capabilitiesReady()
    payload["customAppSupported"] = sdkLinked()
    payload["callbackScheme"] = callbackScheme
    payload["callbackUrl"] = "\(callbackScheme)://\(callbackHost)\(callbackPath)"
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
    guard let url = URL(string: "rokidai://"), UIApplication.shared.canOpenURL(url) else {
      promise.resolve(false)
      return
    }

    DispatchQueue.main.async {
      UIApplication.shared.open(url, options: [:]) { opened in
        promise.resolve(opened)
      }
    }
  }

  private static func requestAuthorization(scopes: [String], appName: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    if CxrClient.shared.auth.isAuthenticated() {
      promise.resolve(authorizationSuccessPayload(source: "cached"))
      return
    }
    DispatchQueue.main.async {
      CxrClient.shared.auth.authenticate(
        scopes: scopes,
        appName: appName
      ) { result in
        switch result {
        case .success(let authResult):
          promise.resolve(authorizationSuccessPayload(
            tokenLength: authResult.token.count,
            sessionId: authResult.sessionId,
            source: "authenticate_completion"
          ))
        case .failure(let error):
          if CxrClient.shared.auth.isAuthenticated() {
            var response = authorizationSuccessPayload(source: "post_failure_state")
            response["nativeWarning"] = String(describing: error)
            promise.resolve(response)
            return
          }
          promise.resolve([
            "ok": false,
            "reason": String(describing: error),
            "authorizationState": authorizationState(),
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
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }

    CxrClient.shared.openCustomView(view)
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
    response["pendingSessionEvent"] = commandAccepted && !running
    return response
  }

  #if canImport(RGCxrClient)
  private static func authorizationSuccessPayload(
    tokenLength: Int? = nil,
    sessionId: String? = nil,
    source: String
  ) -> [String: Any] {
    var response: [String: Any] = [:]
    response["ok"] = true
    response["authorizationState"] = "authenticated"
    response["source"] = source
    response["tokenLength"] = tokenLength ?? CxrClient.shared.auth.currentToken?.count ?? 0
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
    guard let url = URL(string: "rokidai://") else {
      return false
    }
    return UIApplication.shared.canOpenURL(url)
  }

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

  private static func configureAuthentication() {
    #if canImport(RGCxrClient)
    guard !RokidBridgeModule.didConfigureAuthentication else {
      return
    }
    RokidBridgeModule.didConfigureAuthentication = true
    CxrClient.shared.auth.config = RGCxrClientAuthConfig(
      callbackScheme: callbackScheme,
      callbackHost: callbackHost,
      callbackPath: callbackPath
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
      }
      .store(in: &RokidBridgeModule.cancellables)
    #endif
  }

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
    guard url.scheme?.caseInsensitiveCompare(callbackScheme) == .orderedSame else {
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

  fileprivate static func handleOpenURL(_ url: URL) -> Bool {
    guard isExpectedAuthCallback(url) else {
      return false
    }

    lastCallbackUrl = url.absoluteString
    lastCallbackAt = ISO8601DateFormatter().string(from: Date())

    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    let handledByAuth = CxrClient.shared.auth.handleCallback(url: url)
    let handledByClient = handledByAuth ? false : CxrClient.shared.handleOpenURL(url)
    let handled = handledByAuth || handledByClient || CxrClient.shared.auth.isAuthenticated()
    lastCallbackHandled = handled
    return handled
    #else
    lastCallbackHandled = false
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
  @objc public static func canHandleOpenURL(_ url: URL) -> Bool {
    RokidBridgeModule.isExpectedAuthCallback(url)
  }

  @objc public static func handleOpenURL(_ url: URL) -> Bool {
    RokidBridgeModule.handleOpenURL(url)
  }
}
