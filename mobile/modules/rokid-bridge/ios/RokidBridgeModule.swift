import ExpoModulesCore
import AVFoundation
import Combine
import Foundation
import Speech
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

  private static let transcriptEventName = "onRokidTranscript"
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
  private static var didInitializeCustomApp = false
  private static var didBindRuntimeEvents = false
  private static var customViewRunning = false
  private static var customViewDisplayInferred = false
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
  private static var pendingCustomViewPayload: String?
  private static var lastCustomViewAutoRetryAt: String?
  private static var lastCustomViewCommandAt: String?
  private static var lastCustomViewSessionEvidenceAt: String?
  private static var lastCustomViewSessionEvidenceReason: String?
  private static var lastCustomViewRawNotify: String?
  private static var lastCustomViewRawNotifyAt: String?
  private static var lastCustomViewOpenError: String?
  private static var lastCustomViewOpenCommandAccepted: Bool?
  private static var lastCustomViewOpenCallbackSuccess: Bool?
  private static var lastCustomViewOpenCallbackErrorCode: String?
  private static var lastCustomViewOpenCallbackAt: String?
  private static var activeRecordType: String?
  private static var audioStreamChunkCount = 0
  private static var audioStreamByteCount = 0
  private static var lastAudioEventAt: String?
  private static var lastAudioEventType: String?
  private static var lastAudioRecordType: String?
  private static var lastAudioCodec: Int32?
  private static var lastAudioChannels: UInt32?
  private static var lastAudioChunkBytes: Int?
  private static var lastAudioTimestamp: UInt64?
  private static var speechRecognitionState = "idle"
  private static var speechAuthorizationStatus = "not_determined"
  private static var speechRecognizerAvailable: Bool?
  private static var speechRecognitionLocale = "zh-CN"
  private static var speechAudioSampleRate: Double = 16000
  private static var speechAudioChannels: UInt32 = 1
  private static var speechAudioAppendCount = 0
  private static var speechAudioFrameCount: AVAudioFramePosition = 0
  private static var lastSpeechTranscript: String?
  private static var lastSpeechTranscriptAt: String?
  private static var lastSpeechEventAt: String?
  private static var lastSpeechEventSource: String?
  private static var lastSpeechResultIsFinal: Bool?
  private static var lastSpeechError: String?
  private static var lastSpeechRecognitionType: String?
  private static var lastEmittedSpeechTranscript: String?
  private static let speechStabilityDelaySeconds: TimeInterval = 0.9
  private static var emitTranscriptEvent: (([String: Any]) -> Void)?
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
  private static var speechRecognizer: SFSpeechRecognizer?
  private static var speechRecognitionRequest: SFSpeechAudioBufferRecognitionRequest?
  private static var speechRecognitionTask: SFSpeechRecognitionTask?
  private static var speechAudioFormat: AVAudioFormat?
  private static var speechStabilityWorkItem: DispatchWorkItem?
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
    Events(RokidBridgeModule.transcriptEventName)

    OnCreate {
      RokidBridgeModule.emitTranscriptEvent = { [weak self] payload in
        DispatchQueue.main.async {
          self?.sendEvent(RokidBridgeModule.transcriptEventName, payload)
        }
      }
    }

    OnDestroy {
      RokidBridgeModule.emitTranscriptEvent = nil
    }

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

    AsyncFunction("startRecord") { (type: String, codec: String, mode: String, promise: Promise) in
      RokidBridgeModule.startRecord(type: type, codec: codec, mode: mode, promise: promise)
    }

    AsyncFunction("stopRecord") { (type: String) -> [String: Any] in
      RokidBridgeModule.stopRecord(type: type)
    }
  }

  private static func integrationStatusPayload() -> [String: Any] {
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
    payload["customViewSessionEvidence"] = hasCustomViewSessionEvidence()
    payload["customViewDisplayInferred"] = customViewDisplayInferred
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
    payload["customViewPendingRetry"] = pendingCustomViewPayload != nil
    if let lastCustomViewAutoRetryAt {
      payload["lastCustomViewAutoRetryAt"] = lastCustomViewAutoRetryAt
    }
    if let lastCustomViewCommandAt {
      payload["lastCustomViewCommandAt"] = lastCustomViewCommandAt
    }
    if let lastCustomViewSessionEvidenceAt {
      payload["lastCustomViewSessionEvidenceAt"] = lastCustomViewSessionEvidenceAt
    }
    if let lastCustomViewSessionEvidenceReason {
      payload["lastCustomViewSessionEvidenceReason"] = lastCustomViewSessionEvidenceReason
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
    payload["audioStreamChunkCount"] = audioStreamChunkCount
    payload["audioStreamByteCount"] = audioStreamByteCount
    if let activeRecordType {
      payload["activeRecordType"] = activeRecordType
    }
    if let lastAudioEventAt {
      payload["lastAudioEventAt"] = lastAudioEventAt
    }
    if let lastAudioEventType {
      payload["lastAudioEventType"] = lastAudioEventType
    }
    if let lastAudioRecordType {
      payload["lastAudioRecordType"] = lastAudioRecordType
    }
    if let lastAudioCodec {
      payload["lastAudioCodec"] = lastAudioCodec
    }
    if let lastAudioChannels {
      payload["lastAudioChannels"] = lastAudioChannels
    }
    if let lastAudioChunkBytes {
      payload["lastAudioChunkBytes"] = lastAudioChunkBytes
    }
    if let lastAudioTimestamp {
      payload["lastAudioTimestamp"] = String(lastAudioTimestamp)
    }
    payload["speechRecognitionState"] = speechRecognitionState
    payload["speechAuthorizationStatus"] = speechAuthorizationStatus
    payload["speechRecognitionLocale"] = speechRecognitionLocale
    payload["speechAudioSampleRate"] = speechAudioSampleRate
    payload["speechAudioChannels"] = speechAudioChannels
    payload["speechAudioAppendCount"] = speechAudioAppendCount
    payload["speechAudioFrameCount"] = speechAudioFrameCount
    if let speechRecognizerAvailable {
      payload["speechRecognizerAvailable"] = speechRecognizerAvailable
    }
    if let lastSpeechRecognitionType {
      payload["lastSpeechRecognitionType"] = lastSpeechRecognitionType
    }
    if let lastSpeechTranscript {
      payload["lastSpeechTranscript"] = lastSpeechTranscript
    }
    if let lastSpeechTranscriptAt {
      payload["lastSpeechTranscriptAt"] = lastSpeechTranscriptAt
    }
    if let lastSpeechEventAt {
      payload["lastSpeechEventAt"] = lastSpeechEventAt
    }
    if let lastSpeechEventSource {
      payload["lastSpeechEventSource"] = lastSpeechEventSource
    }
    if let lastSpeechResultIsFinal {
      payload["lastSpeechResultIsFinal"] = lastSpeechResultIsFinal
    }
    if let lastSpeechError {
      payload["lastSpeechError"] = lastSpeechError
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
    pendingCustomViewPayload = view
    recordAuthDiagnostic(
      "custom_view_open_requested",
      detail: "authorized=\(CxrClient.shared.auth.isAuthenticated()); bleConnected=\(iosBleConnected()); bleDevice=\(iosBleDeviceName() ?? "unknown"); bytes=\(view.utf8.count); hash=\(lastCustomViewPayloadHash ?? "unknown"); shape=\(lastCustomViewPayloadShape ?? "unknown"); runningBefore=\(RokidBridgeModule.customViewRunning)"
    )
    guard CxrClient.shared.auth.isAuthenticated() else {
      recordAuthDiagnostic("custom_view_open_blocked", detail: "rokid_not_authorized")
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }
    // 实证回归修复(EAS build #158 ab0674de 有此 guard → 眼镜可"连上等待命令";
    // #159 8db5fa54 删除后眼镜不再渲染、rawNotify=none)。openCustomView 只能在 BLE 真就绪时
    // 发给 SDK —— 过早发会让眼镜进坏状态、之后连上也不渲染。pendingCustomViewPayload 已在上方
    // 设好,connectionStatePublisher 连上时自动重发,所以阻断不影响 hand-off。
    let bleDeviceNameBeforeOpen = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
    guard iosBleConnected() else {
      let reason = "rokid_glasses_ble_not_connected"
      RokidBridgeModule.lastCustomViewOpenError = "\(reason); device=\(bleDeviceNameBeforeOpen); pending_retry_on_ble_connect"
      recordAuthDiagnostic(
        "custom_view_open_blocked",
        detail: "rokid_glasses_ble_not_connected; device=\(bleDeviceNameBeforeOpen); authorized=true; pendingRetry=true"
      )
      var response = customViewCommandPayload(commandAccepted: false)
      response["reason"] = reason
      response["iosBleConnected"] = false
      response["iosBleDeviceName"] = bleDeviceNameBeforeOpen
      promise.resolve(response)
      return
    }
    recordAuthDiagnostic(
      "custom_view_ble_preflight",
      detail: "connected=true; device=\(bleDeviceNameBeforeOpen); action=attempt_sdk_open"
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
          RokidBridgeModule.markCustomViewSessionEvidence("open_callback_success")
        } else {
          RokidBridgeModule.customViewRunning = false
          let callbackBleConnected = iosBleConnected()
          let callbackDeviceName = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
          let linkHint = callbackBleConnected ? "ios_ble_connected" : "rokid_glasses_ble_not_connected"
          RokidBridgeModule.lastCustomViewOpenError = "\(linkHint); open_callback_error_code=\(String(describing: errorCode)); device=\(callbackDeviceName)"
          if callbackBleConnected && errorCode == nil {
            RokidBridgeModule.markCustomViewSessionEvidence("open_callback_false_nil_error_ble_connected")
          } else {
            RokidBridgeModule.clearCustomViewSessionEvidence("open_callback_failed")
          }
        }
        recordAuthDiagnostic(
          "custom_view_open_callback",
          detail: "commandAccepted=\(success); errorCode=\(String(describing: errorCode)); running=\(RokidBridgeModule.customViewRunning); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown")"
        )
        if !success || RokidBridgeModule.customViewRunning {
          resolveCustomViewOpenPromiseIfNeeded(promise, state: resolutionState, commandAccepted: success)
        }
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
      let settledCommandAccepted = RokidBridgeModule.customViewOpenSettleCommandAccepted()
      RokidBridgeModule.markCustomViewOpenUnconfirmedIfNeeded(commandAccepted: settledCommandAccepted)
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
    guard RokidBridgeModule.hasCustomViewSessionEvidence() else {
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
          RokidBridgeModule.clearCustomViewSessionEvidence("custom_view_close_callback")
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
    RokidBridgeModule.clearCustomViewSessionEvidence("custom_view_close_legacy")
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
    guard iosBleConnected() else {
      promise.resolve([
        "ok": false,
        "reason": "rokid_glasses_ble_not_connected",
        "customViewRunning": RokidBridgeModule.customViewRunning,
        "customViewSessionEvidence": RokidBridgeModule.hasCustomViewSessionEvidence(),
        "iosBleConnected": false,
        "iosBleDeviceName": iosBleDeviceName() ?? currentDeviceName ?? "",
      ])
      return
    }
    guard RokidBridgeModule.hasCustomViewMediaSession() else {
      promise.resolve([
        "ok": false,
        "reason": "rokid_custom_view_not_ready",
        "customViewRunning": RokidBridgeModule.customViewRunning,
        "customViewSessionEvidence": RokidBridgeModule.hasCustomViewSessionEvidence(),
        "iosBleConnected": iosBleConnected(),
        "iosBleDeviceName": iosBleDeviceName() ?? currentDeviceName ?? "",
      ])
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
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "queryApp",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["installed"] = false
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "queryApp", reason: "rokid_not_authorized")
      response["ok"] = false
      response["installed"] = false
      promise.resolve(response)
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.queryApp { installed in
      var response = customAppDiagnostics(packageName: packageName, operation: "queryApp")
      response["ok"] = true
      response["installed"] = installed
      promise.resolve(response)
    }
    #else
    CxrClient.shared.queryApp(packageName: packageName) { installed in
      var response = customAppDiagnostics(packageName: packageName, operation: "queryApp")
      response["ok"] = true
      response["installed"] = installed
      promise.resolve(response)
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
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "installBundledApp",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["installed"] = false
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "installBundledApp", reason: "rokid_not_authorized")
      response["ok"] = false
      response["installed"] = false
      promise.resolve(response)
      return
    }
    guard let apkURL = Bundle.main.url(forResource: resourceName, withExtension: resourceExtension) ??
      Bundle.main.url(forResource: resourceName, withExtension: resourceExtension, subdirectory: "RokidApps") else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "installBundledApp",
        reason: "rokid_apk_resource_missing"
      )
      response["ok"] = false
      response["installed"] = false
      response["resourceName"] = resourceName
      response["resourceExtension"] = resourceExtension
      promise.resolve(response)
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
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "installAppFileUri",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["installed"] = false
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "installAppFileUri", reason: "rokid_not_authorized")
      response["ok"] = false
      response["installed"] = false
      promise.resolve(response)
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
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "uninstallApp",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["uninstalled"] = false
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "uninstallApp", reason: "rokid_not_authorized")
      response["ok"] = false
      response["uninstalled"] = false
      promise.resolve(response)
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.uninstallApp { uninstalled in
      var response = customAppDiagnostics(packageName: packageName, operation: "uninstallApp")
      response["ok"] = uninstalled
      response["uninstalled"] = uninstalled
      if !uninstalled {
        response["reason"] = "rokid_app_uninstall_rejected"
      }
      promise.resolve(response)
    }
    #else
    CxrClient.shared.uninstallApp(packageName) { uninstalled in
      var response = customAppDiagnostics(packageName: packageName, operation: "uninstallApp")
      response["ok"] = uninstalled
      response["uninstalled"] = uninstalled
      if !uninstalled {
        response["reason"] = "rokid_app_uninstall_rejected"
      }
      promise.resolve(response)
    }
    #endif
    #else
    _ = packageName
    promise.resolve(["ok": false, "uninstalled": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func openApp(packageName: String, activityName: String, url: String, promise: Promise) {
    #if canImport(RGCxrClient)
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "openApp",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["opened"] = false
      response["activityName"] = activityName
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "openApp", reason: "rokid_not_authorized")
      response["ok"] = false
      response["opened"] = false
      response["activityName"] = activityName
      promise.resolve(response)
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.openApp(activityName: activityName, url: url) { opened in
      var response = customAppDiagnostics(packageName: packageName, operation: "openApp")
      response["ok"] = opened
      response["opened"] = opened
      response["activityName"] = activityName
      if !opened {
        response["reason"] = "rokid_app_open_rejected"
      }
      promise.resolve(response)
    }
    #else
    CxrClient.shared.openApp(packageName: packageName, activityName: activityName, url: url) { opened in
      var response = customAppDiagnostics(packageName: packageName, operation: "openApp")
      response["ok"] = opened
      response["opened"] = opened
      response["activityName"] = activityName
      if !opened {
        response["reason"] = "rokid_app_open_rejected"
      }
      promise.resolve(response)
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
    guard ensureCustomAppInitialized(packageName: packageName) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "stopApp",
        reason: "rokid_cxrl_wrong_session_mode"
      )
      response["ok"] = false
      response["stopped"] = false
      response["relaunchRequired"] = true
      promise.resolve(response)
      return
    }
    guard CxrClient.shared.auth.isAuthenticated() else {
      var response = customAppDiagnostics(packageName: packageName, operation: "stopApp", reason: "rokid_not_authorized")
      response["ok"] = false
      response["stopped"] = false
      promise.resolve(response)
      return
    }

    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.stopApp { stopped in
      var response = customAppDiagnostics(packageName: packageName, operation: "stopApp")
      response["ok"] = stopped
      response["stopped"] = stopped
      if !stopped {
        response["reason"] = "rokid_app_stop_rejected"
      }
      promise.resolve(response)
    }
    #else
    CxrClient.shared.stopApp(packageName) { stopped in
      var response = customAppDiagnostics(packageName: packageName, operation: "stopApp")
      response["ok"] = stopped
      response["stopped"] = stopped
      if !stopped {
        response["reason"] = "rokid_app_stop_rejected"
      }
      promise.resolve(response)
    }
    #endif
    #else
    _ = packageName
    promise.resolve(["ok": false, "stopped": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func startRecord(type: String, codec: String, mode: String, promise: Promise) {
    #if canImport(RGCxrClient)
    ensureCustomViewInitialized()
    guard CxrClient.shared.auth.isAuthenticated() else {
      promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
      return
    }
    guard iosBleConnected() else {
      lastAudioEventAt = isoTimestamp()
      lastAudioEventType = "record_start_rejected"
      lastAudioRecordType = type
      activeRecordType = nil
      recordAuthDiagnostic(
        "audio_record_start_rejected",
        detail: "reason=rokid_glasses_ble_not_connected; running=\(RokidBridgeModule.customViewRunning); evidence=\(RokidBridgeModule.hasCustomViewSessionEvidence()); bleConnected=false; device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
      )
      promise.resolve([
        "ok": false,
        "reason": "rokid_glasses_ble_not_connected",
        "customViewRunning": RokidBridgeModule.customViewRunning,
        "customViewSessionEvidence": RokidBridgeModule.hasCustomViewSessionEvidence(),
        "iosBleConnected": false,
        "iosBleDeviceName": iosBleDeviceName() ?? currentDeviceName ?? "",
      ])
      return
    }
    guard RokidBridgeModule.hasCustomViewMediaSession() else {
      lastAudioEventAt = isoTimestamp()
      lastAudioEventType = "record_start_rejected"
      lastAudioRecordType = type
      activeRecordType = nil
      recordAuthDiagnostic(
        "audio_record_start_rejected",
        detail: "reason=rokid_audio_session_not_ready; running=\(RokidBridgeModule.customViewRunning); evidence=\(RokidBridgeModule.hasCustomViewSessionEvidence()); bleConnected=true; device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
      )
      promise.resolve([
        "ok": false,
        "reason": "rokid_audio_session_not_ready",
        "customViewRunning": RokidBridgeModule.customViewRunning,
        "customViewSessionEvidence": RokidBridgeModule.hasCustomViewSessionEvidence(),
        "iosBleConnected": iosBleConnected(),
        "iosBleDeviceName": iosBleDeviceName() ?? currentDeviceName ?? "",
      ])
      return
    }

    prepareSpeechRecognitionForStart(type: type) { speechReady, reason in
      DispatchQueue.main.async {
        if !speechReady {
          RokidBridgeModule.recordAuthDiagnostic(
            "speech_recognition_not_ready_recording_continues",
            detail: "type=\(type); reason=\(reason ?? "speech_recognition_unavailable")"
          )
        }

        prepareAudioDiagnosticsForStart(type: type, codec: codec, mode: mode)
        CxrClient.shared.startRecord(type, codec: audioCodec(codec), mode: audioMode(mode))
        promise.resolve([
          "ok": true,
          "speechRecognitionReady": speechReady,
          "speechRecognitionReason": reason ?? "",
          "speechRecognitionState": RokidBridgeModule.speechRecognitionState,
          "speechAuthorizationStatus": RokidBridgeModule.speechAuthorizationStatus,
        ])
      }
    }
    #else
    _ = type
    _ = codec
    _ = mode
    promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
    #endif
  }

  private static func stopRecord(type: String) -> [String: Any] {
    #if canImport(RGCxrClient)
    CxrClient.shared.stopRecord(type)
    finishSpeechRecognitionSession(reason: "record_stop_requested")
    lastAudioEventAt = isoTimestamp()
    lastAudioEventType = "record_stop_requested"
    activeRecordType = nil
    recordAuthDiagnostic(
      "audio_record_stop_requested",
      detail: "type=\(type); chunks=\(audioStreamChunkCount); totalBytes=\(audioStreamByteCount)"
    )
    return ["ok": true]
    #else
    _ = type
    return ["ok": false, "reason": "ios_sdk_not_linked"]
    #endif
  }

  #if canImport(RGCxrClient)
  private static func prepareAudioDiagnosticsForStart(type: String, codec: String, mode: String) {
    activeRecordType = type
    audioStreamChunkCount = 0
    audioStreamByteCount = 0
    lastAudioEventAt = isoTimestamp()
    lastAudioEventType = "record_start_requested"
    lastAudioRecordType = type
    lastAudioCodec = nil
    lastAudioChannels = nil
    lastAudioChunkBytes = nil
    lastAudioTimestamp = nil
    recordAuthDiagnostic(
      "audio_record_start_requested",
      detail: "type=\(type); codec=\(codec); mode=\(mode)"
    )
  }

  private static func handleAudioEvent(_ event: RGCxrClientAudioEvent) {
    switch event {
    case .started(let startEvent):
      activeRecordType = startEvent.type
      audioStreamChunkCount = 0
      audioStreamByteCount = 0
      lastAudioEventAt = isoTimestamp()
      lastAudioEventType = "started"
      lastAudioRecordType = startEvent.type
      lastAudioCodec = startEvent.codec
      lastAudioChannels = startEvent.channels
      lastAudioChunkBytes = nil
      lastAudioTimestamp = nil
      configureSpeechAudioFormat(channels: startEvent.channels)
      recordAuthDiagnostic(
        "audio_event_started",
        detail: "type=\(startEvent.type); codec=\(startEvent.codec); channels=\(startEvent.channels); speechSampleRate=\(Int(speechAudioSampleRate))"
      )
    case .stream(let dataEvent):
      let byteCount = dataEvent.data.count
      audioStreamChunkCount += 1
      audioStreamByteCount += byteCount
      lastAudioEventAt = isoTimestamp()
      lastAudioEventType = "stream"
      lastAudioChunkBytes = byteCount
      lastAudioTimestamp = dataEvent.timestamp
      // Privacy: never log or forward raw PCM bytes here; diagnostics only expose counters and sizes.
      appendRokidAudioToSpeechRecognizer(dataEvent.data, timestamp: dataEvent.timestamp)
      if audioStreamChunkCount <= 3 || audioStreamChunkCount % 20 == 0 {
        recordAuthDiagnostic(
          "audio_event_stream",
          detail: "bytes=\(byteCount); chunks=\(audioStreamChunkCount); totalBytes=\(audioStreamByteCount); timestamp=\(dataEvent.timestamp); type=\(lastAudioRecordType ?? activeRecordType ?? "unknown"); speechState=\(speechRecognitionState); speechAppends=\(speechAudioAppendCount)"
        )
      }
    @unknown default:
      recordAuthDiagnostic("audio_event_unknown", detail: "event=\(String(describing: event))")
    }
  }

  private static func prepareSpeechRecognitionForStart(
    type: String,
    completion: @escaping (Bool, String?) -> Void
  ) {
    let currentAuthorization = SFSpeechRecognizer.authorizationStatus()
    speechAuthorizationStatus = speechAuthorizationStatusDescription(currentAuthorization)
    switch currentAuthorization {
    case .authorized:
      completion(startSpeechRecognitionSession(type: type), lastSpeechError)
    case .notDetermined:
      speechRecognitionState = "requesting_authorization"
      recordAuthDiagnostic("speech_authorization_request", detail: "locale=\(speechRecognitionLocale)")
      SFSpeechRecognizer.requestAuthorization { status in
        DispatchQueue.main.async {
          speechAuthorizationStatus = speechAuthorizationStatusDescription(status)
          recordAuthDiagnostic("speech_authorization_result", detail: "status=\(speechAuthorizationStatus)")
          if status == .authorized {
            completion(startSpeechRecognitionSession(type: type), lastSpeechError)
          } else {
            speechRecognitionState = "authorization_denied"
            lastSpeechError = "ios_speech_authorization_\(speechAuthorizationStatus)"
            completion(false, lastSpeechError)
          }
        }
      }
    case .denied:
      speechRecognitionState = "authorization_denied"
      lastSpeechError = "ios_speech_authorization_denied"
      completion(false, lastSpeechError)
    case .restricted:
      speechRecognitionState = "authorization_restricted"
      lastSpeechError = "ios_speech_authorization_restricted"
      completion(false, lastSpeechError)
    @unknown default:
      speechRecognitionState = "authorization_unknown"
      lastSpeechError = "ios_speech_authorization_unknown"
      completion(false, lastSpeechError)
    }
  }

  private static func startSpeechRecognitionSession(type: String) -> Bool {
    cancelSpeechRecognitionSession(reason: "restart")
    let recognizer = SFSpeechRecognizer(locale: Locale(identifier: speechRecognitionLocale))
    speechRecognizer = recognizer
    speechRecognizerAvailable = recognizer?.isAvailable
    guard let recognizer, recognizer.isAvailable else {
      speechRecognitionState = "recognizer_unavailable"
      lastSpeechError = "ios_speech_recognizer_unavailable"
      recordAuthDiagnostic("speech_recognition_unavailable", detail: "locale=\(speechRecognitionLocale)")
      return false
    }

    let request = SFSpeechAudioBufferRecognitionRequest()
    request.shouldReportPartialResults = true
    request.taskHint = .dictation
    speechRecognitionRequest = request
    speechRecognitionState = "recognizing"
    lastSpeechRecognitionType = type
    lastSpeechError = nil
    lastSpeechTranscript = nil
    lastSpeechTranscriptAt = nil
    lastSpeechEventAt = nil
    lastSpeechEventSource = nil
    lastSpeechResultIsFinal = nil
    lastEmittedSpeechTranscript = nil
    speechAudioAppendCount = 0
    speechAudioFrameCount = 0
    speechAudioChannels = 1
    speechAudioSampleRate = 16000
    speechAudioFormat = makeSpeechAudioFormat(channels: speechAudioChannels)

    speechRecognitionTask = recognizer.recognitionTask(with: request) { result, error in
      DispatchQueue.main.async {
        handleSpeechRecognitionResult(result, error: error)
      }
    }
    recordAuthDiagnostic(
      "speech_recognition_started",
      detail: "type=\(type); locale=\(speechRecognitionLocale); sampleRate=\(Int(speechAudioSampleRate)); stabilityMs=\(Int(speechStabilityDelaySeconds * 1000))"
    )
    return true
  }

  private static func cancelSpeechRecognitionSession(reason: String) {
    speechStabilityWorkItem?.cancel()
    speechStabilityWorkItem = nil
    speechRecognitionTask?.cancel()
    speechRecognitionTask = nil
    speechRecognitionRequest?.endAudio()
    speechRecognitionRequest = nil
    if speechRecognitionState == "recognizing" || speechRecognitionState == "requesting_authorization" {
      speechRecognitionState = "cancelled"
    }
    if reason != "restart" {
      recordAuthDiagnostic("speech_recognition_cancelled", detail: "reason=\(reason)")
    }
  }

  private static func finishSpeechRecognitionSession(reason: String) {
    speechStabilityWorkItem?.cancel()
    speechStabilityWorkItem = nil
    speechRecognitionRequest?.endAudio()
    speechRecognitionTask?.finish()
    speechRecognitionRequest = nil
    speechRecognitionTask = nil
    if speechRecognitionState == "recognizing" {
      speechRecognitionState = "ending"
    }
    recordAuthDiagnostic(
      "speech_recognition_finish_requested",
      detail: "reason=\(reason); appends=\(speechAudioAppendCount); frames=\(speechAudioFrameCount); lastTranscript=\(lastSpeechTranscript == nil ? "none" : "present")"
    )
  }

  private static func configureSpeechAudioFormat(channels: UInt32) {
    let resolvedChannels = max(1, channels)
    speechAudioChannels = resolvedChannels
    speechAudioSampleRate = 16000
    speechAudioFormat = makeSpeechAudioFormat(channels: resolvedChannels)
  }

  private static func makeSpeechAudioFormat(channels: UInt32) -> AVAudioFormat? {
    AVAudioFormat(
      commonFormat: .pcmFormatInt16,
      sampleRate: speechAudioSampleRate,
      channels: AVAudioChannelCount(max(1, channels)),
      interleaved: true
    )
  }

  private static func appendRokidAudioToSpeechRecognizer(_ data: Data, timestamp: UInt64) {
    guard speechRecognitionState == "recognizing", let request = speechRecognitionRequest else {
      return
    }
    guard let format = speechAudioFormat ?? makeSpeechAudioFormat(channels: speechAudioChannels) else {
      lastSpeechError = "ios_speech_audio_format_unavailable"
      recordAuthDiagnostic("speech_audio_append_failed", detail: "reason=audio_format_unavailable; bytes=\(data.count)")
      return
    }
    let bytesPerFrame = Int(format.streamDescription.pointee.mBytesPerFrame)
    guard bytesPerFrame > 0 else {
      lastSpeechError = "ios_speech_audio_bytes_per_frame_invalid"
      recordAuthDiagnostic("speech_audio_append_failed", detail: "reason=bytes_per_frame_invalid; bytes=\(data.count)")
      return
    }
    let frameCount = data.count / bytesPerFrame
    guard frameCount > 0 else {
      return
    }
    guard let buffer = AVAudioPCMBuffer(
      pcmFormat: format,
      frameCapacity: AVAudioFrameCount(frameCount)
    ) else {
      lastSpeechError = "ios_speech_audio_buffer_allocation_failed"
      recordAuthDiagnostic("speech_audio_append_failed", detail: "reason=buffer_allocation_failed; bytes=\(data.count)")
      return
    }

    buffer.frameLength = AVAudioFrameCount(frameCount)
    let bytesToCopy = frameCount * bytesPerFrame
    data.withUnsafeBytes { rawBuffer in
      guard let source = rawBuffer.baseAddress,
        let destination = buffer.mutableAudioBufferList.pointee.mBuffers.mData else {
        return
      }
      memcpy(destination, source, bytesToCopy)
      buffer.mutableAudioBufferList.pointee.mBuffers.mDataByteSize = UInt32(bytesToCopy)
    }

    request.append(buffer)
    speechAudioAppendCount += 1
    speechAudioFrameCount += AVAudioFramePosition(frameCount)
    if speechAudioAppendCount <= 3 || speechAudioAppendCount % 20 == 0 {
      recordAuthDiagnostic(
        "speech_audio_appended",
        detail: "bytes=\(bytesToCopy); frames=\(frameCount); appends=\(speechAudioAppendCount); timestamp=\(timestamp); sampleRate=\(Int(speechAudioSampleRate)); channels=\(speechAudioChannels)"
      )
    }
  }

  private static func handleSpeechRecognitionResult(_ result: SFSpeechRecognitionResult?, error: Error?) {
    if let error {
      let description = sanitizeAuthDiagnosticDetail(String(describing: error))
      lastSpeechError = description
      lastSpeechEventAt = isoTimestamp()
      if speechRecognitionState == "recognizing" || speechRecognitionState == "ending" {
        speechRecognitionState = "failed"
      }
      recordAuthDiagnostic("speech_recognition_error", detail: description)
      return
    }

    guard let result else {
      return
    }
    let transcript = result.bestTranscription.formattedString.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !transcript.isEmpty else {
      return
    }
    let confidence = averageSpeechConfidence(result)
    lastSpeechTranscript = transcript
    lastSpeechTranscriptAt = isoTimestamp()
    lastSpeechEventAt = lastSpeechTranscriptAt
    lastSpeechResultIsFinal = result.isFinal
    lastSpeechError = nil
    if result.isFinal {
      speechRecognitionState = "final"
      emitSpeechTranscript(transcript, confidence: confidence, source: "ios_speech_final", isFinal: true)
    } else {
      speechRecognitionState = "recognizing"
      scheduleStableSpeechTranscript(transcript, confidence: confidence)
    }
  }

  private static func scheduleStableSpeechTranscript(_ transcript: String, confidence: Double?) {
    speechStabilityWorkItem?.cancel()
    let workItem = DispatchWorkItem {
      guard lastSpeechTranscript == transcript, speechRecognitionState == "recognizing" else {
        return
      }
      emitSpeechTranscript(transcript, confidence: confidence, source: "ios_speech_stable", isFinal: true)
    }
    speechStabilityWorkItem = workItem
    DispatchQueue.main.asyncAfter(deadline: .now() + speechStabilityDelaySeconds, execute: workItem)
  }

  private static func emitSpeechTranscript(
    _ transcript: String,
    confidence: Double?,
    source: String,
    isFinal: Bool
  ) {
    let normalized = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else {
      return
    }
    if isFinal && lastEmittedSpeechTranscript == normalized {
      return
    }
    if isFinal {
      lastEmittedSpeechTranscript = normalized
    }
    let capturedAt = isoTimestamp()
    lastSpeechEventAt = capturedAt
    lastSpeechEventSource = source
    lastSpeechResultIsFinal = isFinal
    var payload: [String: Any] = [
      "transcript": normalized,
      "text": normalized,
      "capturedAt": capturedAt,
      "captured_at": capturedAt,
      "source": source,
      "type": lastSpeechRecognitionType ?? activeRecordType ?? "reva_voice_command",
      "partial": !isFinal,
      "isFinal": isFinal,
      "is_final": isFinal,
      "final": isFinal,
      "meta": [
        "audio_chunks": audioStreamChunkCount,
        "audio_bytes": audioStreamByteCount,
        "speech_appends": speechAudioAppendCount,
        "speech_frames": speechAudioFrameCount,
        "speech_sample_rate": speechAudioSampleRate,
        "speech_channels": speechAudioChannels,
        "privacy_note": "no_raw_audio_forwarded",
      ],
    ]
    if let confidence {
      payload["confidence"] = confidence
    }
    emitTranscriptEvent?(payload)
    recordAuthDiagnostic(
      "speech_transcript_emitted",
      detail: "source=\(source); final=\(isFinal); chars=\(normalized.count); chunks=\(audioStreamChunkCount); appends=\(speechAudioAppendCount)"
    )
  }

  private static func averageSpeechConfidence(_ result: SFSpeechRecognitionResult) -> Double? {
    let confidences = result.bestTranscription.segments
      .map { Double($0.confidence) }
      .filter { $0 >= 0 && $0 <= 1 }
    guard !confidences.isEmpty else {
      return nil
    }
    return confidences.reduce(0, +) / Double(confidences.count)
  }

  private static func speechAuthorizationStatusDescription(_ status: SFSpeechRecognizerAuthorizationStatus) -> String {
    switch status {
    case .authorized:
      return "authorized"
    case .denied:
      return "denied"
    case .restricted:
      return "restricted"
    case .notDetermined:
      return "not_determined"
    @unknown default:
      return "unknown"
    }
  }
  #endif

  private static func customViewOpenSettleCommandAccepted() -> Bool {
    if RokidBridgeModule.customViewRunning {
      return true
    }
    #if ROKID_CXRL_CALLBACK_API
    if let commandAccepted = RokidBridgeModule.lastCustomViewOpenCommandAccepted {
      return commandAccepted
    }
    return !iosBleConnected()
    #else
    return true
    #endif
  }

  private static func markCustomViewOpenUnconfirmedIfNeeded(commandAccepted: Bool) {
    guard !RokidBridgeModule.customViewRunning, RokidBridgeModule.lastCustomViewOpenError == nil else {
      return
    }
    guard iosBleConnected() else {
      return
    }

    let deviceName = iosBleDeviceName() ?? RokidBridgeModule.currentDeviceName ?? "unknown"
    let rawNotify = RokidBridgeModule.lastCustomViewRawNotify ?? "none"
    #if ROKID_CXRL_CALLBACK_API
    if RokidBridgeModule.lastCustomViewOpenCommandAccepted == nil {
      RokidBridgeModule.lastCustomViewOpenError = "rokid_custom_view_open_callback_missing; running=false; rawNotify=\(rawNotify); iosBleConnected=\(iosBleConnected()); device=\(deviceName)"
      RokidBridgeModule.pendingCustomViewPayload = nil
      return
    }
    #endif
    if commandAccepted {
      RokidBridgeModule.lastCustomViewOpenError = "rokid_custom_view_not_running_after_open; commandAccepted=true; rawNotify=\(rawNotify); iosBleConnected=\(iosBleConnected()); device=\(deviceName)"
    } else {
      RokidBridgeModule.lastCustomViewOpenError = "rokid_custom_view_open_not_accepted; running=false; rawNotify=\(rawNotify); iosBleConnected=\(iosBleConnected()); device=\(deviceName)"
    }
    RokidBridgeModule.pendingCustomViewPayload = nil
  }

  private static func customViewCommandPayload(commandAccepted: Bool) -> [String: Any] {
    let running = isCustomViewRunning()
    let ok = commandAccepted && (running || lastCustomViewOpenError == nil)
    var response: [String: Any] = [:]
    response["ok"] = ok
    response["customViewCommandAccepted"] = commandAccepted
    response["customViewRunning"] = running
    response["customViewSessionEvidence"] = hasCustomViewSessionEvidence()
    response["customViewDisplayInferred"] = customViewDisplayInferred
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
    response["customViewPendingRetry"] = pendingCustomViewPayload != nil
    if let lastCustomViewAutoRetryAt {
      response["lastCustomViewAutoRetryAt"] = lastCustomViewAutoRetryAt
    }
    if let lastCustomViewCommandAt {
      response["lastCustomViewCommandAt"] = lastCustomViewCommandAt
    }
    if let lastCustomViewSessionEvidenceAt {
      response["lastCustomViewSessionEvidenceAt"] = lastCustomViewSessionEvidenceAt
    }
    if let lastCustomViewSessionEvidenceReason {
      response["lastCustomViewSessionEvidenceReason"] = lastCustomViewSessionEvidenceReason
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
    if !ok {
      response["reason"] = lastCustomViewOpenError ?? "rokid_custom_view_open_not_accepted"
    }
    response["pendingSessionEvent"] = ok && commandAccepted && !running
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
  private static func customAppDiagnostics(
    packageName: String,
    operation: String,
    reason: String? = nil
  ) -> [String: Any] {
    var response: [String: Any] = [:]
    response["packageName"] = packageName
    response["operation"] = operation
    response["authorizationState"] = authorizationState()
    response["cxrClientInitialized"] = cxrClientInitialized()
    response["cxrInitializationMode"] = cxrInitializationMode()
    response["cxrInitializationOutcome"] = cxrInitializationOutcome
    response["iosBleConnected"] = iosBleConnected()
    if let deviceName = iosBleDeviceName() ?? currentDeviceName {
      response["iosBleDeviceName"] = deviceName
    }
    if let reason {
      response["reason"] = reason
    }
    return response
  }

  private static func installAppAtPath(
    _ path: String,
    packageName: String,
    source: String,
    promise: Promise
  ) {
    guard FileManager.default.fileExists(atPath: path) else {
      var response = customAppDiagnostics(
        packageName: packageName,
        operation: "installApp",
        reason: "rokid_apk_file_missing"
      )
      response["ok"] = false
      response["installed"] = false
      promise.resolve(response)
      return
    }

    let attributes = try? FileManager.default.attributesOfItem(atPath: path)
    let byteLength = (attributes?[.size] as? NSNumber)?.uint64Value
    let fileName = URL(fileURLWithPath: path).lastPathComponent
    recordAuthDiagnostic(
      "custom_app_install_invoked",
      detail: "source=\(source); package=\(packageName); file=\(fileName); bytes=\(byteLength.map { String($0) } ?? "unknown"); mode=\(cxrInitializationMode()); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
    )
    CxrClient.shared.installApp(path) { installed in
      var response = customAppDiagnostics(packageName: packageName, operation: "installApp")
      response["ok"] = installed
      response["installed"] = installed
      response["source"] = source
      response["apkFileName"] = fileName
      if let byteLength {
        response["byteLength"] = byteLength
      }
      if !installed {
        response["reason"] = "rokid_app_install_rejected"
      }
      recordAuthDiagnostic(
        "custom_app_install_callback",
        detail: "installed=\(installed); source=\(source); package=\(packageName); mode=\(cxrInitializationMode()); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
      )
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
    customViewDisplayInferred = false
    lastCustomViewSessionEvidenceAt = nil
    lastCustomViewSessionEvidenceReason = nil
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

  private static func ensureCustomAppInitialized(packageName: String) -> Bool {
    #if canImport(RGCxrClient)
    var ready = false
    let initializeConfigureAndBind = {
    #if ROKID_CXRL_CALLBACK_API
      let initializedBefore = CxrClient.isInitialized
      let modeBefore = cxrInitializationMode()
      if initializedBefore && modeBefore != "customApp" {
        RokidBridgeModule.cxrInitializationOutcome = "failure_already_initialized:\(modeBefore)"
        recordAuthDiagnostic(
          "cxr_initialize_custom_app_blocked",
          detail: "before=\(initializedBefore); requestedMode=customApp; existingMode=\(modeBefore); package=\(packageName)"
        )
        ready = false
      } else if !RokidBridgeModule.didInitializeCustomApp || !initializedBefore {
        let outcome = CxrClient.initialize(
          mode: .customApp,
          options: RGCxrClientInitializationOptions(appDisplayName: nil, pageName: packageName)
        )
        let outcomeDescription = cxrInitializeOutcomeDescription(outcome)
        let initializedAfter = CxrClient.isInitialized
        let modeAfter = cxrInitializationMode()
        RokidBridgeModule.cxrInitializationOutcome = outcomeDescription
        RokidBridgeModule.didInitializeCustomApp = initializedAfter && modeAfter == "customApp"
        recordAuthDiagnostic(
          "cxr_initialize_custom_app",
          detail: "before=\(initializedBefore); outcome=\(outcomeDescription); after=\(initializedAfter); mode=\(modeAfter); pageName=\(packageName)"
        )
        ready = RokidBridgeModule.didInitializeCustomApp
      } else {
        ready = cxrInitializationMode() == "customApp"
      }
    #else
      if !RokidBridgeModule.didInitializeCustomApp {
        RokidBridgeModule.cxrInitializationOutcome = "legacy_client_no_initialize_api"
        RokidBridgeModule.didInitializeCustomApp = true
      }
      ready = true
    #endif
      configureAuthentication()
      bindRuntimeEvents()
    }
    if Thread.isMainThread {
      initializeConfigureAndBind()
    } else {
      DispatchQueue.main.sync(execute: initializeConfigureAndBind)
    }
    return ready
    #else
    _ = packageName
    return false
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
        if event.isRunning {
          RokidBridgeModule.pendingCustomViewPayload = nil
          RokidBridgeModule.lastCustomViewOpenCommandAccepted = true
          RokidBridgeModule.lastCustomViewOpenError = nil
          RokidBridgeModule.markCustomViewSessionEvidence("running_event_true")
        } else {
          RokidBridgeModule.clearCustomViewSessionEvidence("running_event_false")
        }
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
    CxrClient.shared.audioEventPublisher
      .receive(on: DispatchQueue.main)
      .sink { event in
        RokidBridgeModule.handleAudioEvent(event)
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
        // openCustomView 的"自动重发"仍停用:设备实证(build #158 无自动重发、手动单发 →
        // 眼镜渲染;#160-162 在 BLE 刚连上瞬间自动重发 openCustomView(会话未就绪)+ 与手动点
        // 双发 → SDK 不回 callback、眼镜不渲染)。回到 #158 的"手动点一次"路径。
        //
        // 但 notify 订阅(setNotifyEventListenCmds)之前只在首次 bindRuntimeEvents 调一次。
        // 真机实证(2026-06-20 截图)显示 openCustomView 后 rawNotify=none / running=false /
        // callback 从不触发,而 iosBleConnected=true —— 一种解释是:订阅是在 BLE 还没真连上(或
        // 上一条链路)时贴的,SDK 的 cmd 监听注册是 per-link、重连后失效 → 眼镜的 Custom_View_*
        // notify 根本没被转发回来。BLE 真就绪时重贴一次订阅(只贴订阅、不发任何 openCustomView 命令,
        // 与上面停用的自动重发不同,不会双发),针对性消除 rawNotify=none 这一边界。
        // 若重贴后真机仍 rawNotify=none,则证明静默不在订阅层,而在 companion/固件/会话层(按
        // docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md §4.3/§6 升级 Rokid)。
        if connected {
          RokidBridgeModule.configureCustomViewNotifySubscription()
          RokidBridgeModule.recordAuthDiagnostic(
            "custom_view_notify_resubscribe_on_connect",
            detail: "device=\(RGCxrClientBLE.shared.connectedDeviceName ?? "unknown")"
          )
          // 回归修复(council 标定):retryPendingCustomViewAfterBleConnected 此前是死代码、从未被调 →
          // 排队的 openCustomView 在 BLE 连上后永不重发 → 用户"连不上"。这里接上,但用"延迟 + 单飞"
          // 规避 #160-162 的坑:延迟 1.5s 让 CXR 会话在 BLE 刚连上后 settle(避免"会话未就绪即发"),
          // retry 内部 nil 掉 pending 做单飞、且只在仍连接+未运行时发,避免与手动点双发。
          DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            RokidBridgeModule.retryPendingCustomViewAfterBleConnected()
          }
        }
      }
      .store(in: &RokidBridgeModule.cancellables)
    RGCxrClientBLE.shared.notifyPublisher
      .receive(on: DispatchQueue.main)
      .sink { notify in
        RokidBridgeModule.handleCustomViewNotify(notify)
      }
      .store(in: &RokidBridgeModule.cancellables)
    #if ROKID_CXRL_CALLBACK_API
    // 真机实证(build #167)rawNotify=none 的确定根因:setNotifyEventListenCmds 注册在
    // CxrClient 上,匹配的结构化事件从 CxrClient.notifyEventPublisher(RGCxrClientNotifyEvent)
    // 派发 —— 但上面只订了 RGCxrClientBLE.notifyPublisher(原始 String),从不订 typed publisher,
    // 二者是 SDK 设计上的配对(注册过滤器 + 收 typed 事件),配错对象 → Custom_View_* notify 永收不到。
    // 这里补订 typed publisher(保留 BLE String sink 作回退)。也是决定性诊断:若 typed channel 仍空
    // 且 callback/runningEvent 也空 = 三通道全静默,证明静默在我们层之下(companion/固件/会话),
    // 按 docs/plans/2026-06-18-rokid-cxrl-auth-debugging-lessons.md §6 带证据升级 Rokid。
    CxrClient.shared.notifyEventPublisher
      .receive(on: DispatchQueue.main)
      .sink { event in
        RokidBridgeModule.handleTypedNotifyEvent(event)
      }
      .store(in: &RokidBridgeModule.cancellables)
    #endif
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
      // #169 通信诊断:让眼镜的电量/屏幕/网络/WiFi notify 也回传,定位 CXR 的 TCP/WiFi 数据通道为何不通。
      // Dev_BatteryChanged 当"notify 通道是否活着"的金丝雀:收到=通道通、问题专在 CustomView;全程零事件=
      // 整条 notify/会话死(TCP/WiFi 没起);NoNetwork=眼镜无网络(数据通道前提);Dev_Screen_Status=息屏渲染不出。
      RGCxrSubCmd.Dev_BatteryChanged.rawValue,
      RGCxrSubCmd.Dev_Screen_Status.rawValue,
      RGCxrSubCmd.NoNetwork.rawValue,
      RGCxrSubCmd.Wifi_Status.rawValue,
      RGCxrSubCmd.Wifi_Connect_Status.rawValue,
    ]
    CxrClient.shared.setNotifyEventListenCmds(commands)
    recordAuthDiagnostic("custom_view_notify_subscription", detail: "mode=setNotifyEventListenCmds; commands=\(commands.joined(separator: ","))")
    #else
    recordAuthDiagnostic("custom_view_notify_subscription", detail: "mode=legacy_notify_publisher_only")
    #endif
  }

  #if ROKID_CXRL_CALLBACK_API
  // 处理来自 CxrClient.notifyEventPublisher 的结构化 CustomView notify(setNotifyEventListenCmds 的配对出口)。
  // 每条都记 custom_view_notify_typed 诊断(不预过滤),用 subCmd 等值匹配 RGCxrSubCmd.Custom_View_* 驱动状态。
  private static func handleTypedNotifyEvent(_ event: RGCxrClientNotifyEvent) {
    let summary = "cmd=\(event.cmd); subCmd=\(event.subCmd); status=\(event.status); reqId=\(event.reqId)"
    recordAuthDiagnostic("custom_view_notify_typed", detail: summary)
    lastCustomViewRawNotify = summary
    lastCustomViewRawNotifyAt = isoTimestamp()
    if event.subCmd == RGCxrSubCmd.Custom_View_Opened.rawValue {
      lastCustomViewOpenCommandAccepted = true
      lastCustomViewOpenError = nil
      pendingCustomViewPayload = nil
      markCustomViewSessionEvidence("typed_notify_custom_view_opened")
    } else if event.subCmd == RGCxrSubCmd.Custom_View_Open_Failed.rawValue {
      customViewRunning = false
      lastCustomViewOpenError = "rokid_custom_view_open_failed; status=\(event.status); \(summary)"
      pendingCustomViewPayload = nil
      clearCustomViewSessionEvidence("typed_notify_custom_view_open_failed")
    } else if event.subCmd == RGCxrSubCmd.Custom_View_Closed.rawValue {
      customViewRunning = false
      pendingCustomViewPayload = nil
      clearCustomViewSessionEvidence("typed_notify_custom_view_closed")
    } else if event.subCmd == RGCxrSubCmd.NoNetwork.rawValue {
      // 眼镜上报无网络 → CXR 数据通道(TCP/WiFi)起不来,是 CustomView/install 静默的直接根因。
      // 抬到用户可见的错误行(settle 只在 error==nil 时写,这里先占位不会被覆盖)。
      lastCustomViewOpenError = "rokid_glasses_no_network; CXR 数据通道(TCP/WiFi)需眼镜联网; \(summary)"
      clearCustomViewSessionEvidence("typed_notify_no_network")
    }
  }
  #endif

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
      pendingCustomViewPayload = nil
      markCustomViewSessionEvidence("raw_notify_custom_view_opened")
    } else if normalized.contains("custom_view_open_failed") {
      customViewRunning = false
      lastCustomViewOpenError = cleanNotify
      pendingCustomViewPayload = nil
      clearCustomViewSessionEvidence("raw_notify_custom_view_open_failed")
    } else if normalized.contains("custom_view_closed") || normalized.contains("close_custom_view") {
      customViewRunning = false
      pendingCustomViewPayload = nil
      clearCustomViewSessionEvidence("raw_notify_custom_view_closed")
    }
    recordAuthDiagnostic("custom_view_notify", detail: cleanNotify)
  }

  private static func retryPendingCustomViewAfterBleConnected() {
    guard let view = pendingCustomViewPayload else {
      return
    }
    guard iosBleConnected(), CxrClient.shared.auth.isAuthenticated(), !customViewRunning else {
      return
    }
    pendingCustomViewPayload = nil  // 单飞:重发一次即清,避免重复 connect 事件 / 与手动点双发;失败后用户可手动重开
    lastCustomViewAutoRetryAt = isoTimestamp()
    recordAuthDiagnostic(
      "custom_view_auto_retry",
      detail: "trigger=ble_connected; device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown"); bytes=\(view.utf8.count); hash=\(lastCustomViewPayloadHash ?? "unknown")"
    )
    #if ROKID_CXRL_CALLBACK_API
    CxrClient.shared.openCustomView(view) { success, errorCode in
      DispatchQueue.main.async {
        lastCustomViewOpenCallbackSuccess = success
        lastCustomViewOpenCommandAccepted = success
        lastCustomViewOpenCallbackErrorCode = String(describing: errorCode)
        lastCustomViewOpenCallbackAt = isoTimestamp()
        if success {
          lastCustomViewOpenError = nil
        } else {
          let callbackBleConnected = iosBleConnected()
          let callbackDeviceName = iosBleDeviceName() ?? currentDeviceName ?? "unknown"
          let linkHint = callbackBleConnected ? "ios_ble_connected" : "rokid_glasses_ble_not_connected"
          lastCustomViewOpenError = "\(linkHint); auto_retry_open_callback_error_code=\(String(describing: errorCode)); device=\(callbackDeviceName)"
        }
        recordAuthDiagnostic(
          "custom_view_auto_retry_callback",
          detail: "commandAccepted=\(success); errorCode=\(String(describing: errorCode)); running=\(customViewRunning); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
        )
      }
    }
    #else
    CxrClient.shared.openCustomView(view)
    lastCustomViewOpenCommandAccepted = true
    #endif
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

  private static func hasCustomViewNotifyEvidence() -> Bool {
    guard let notify = RokidBridgeModule.lastCustomViewRawNotify?.trimmingCharacters(in: .whitespacesAndNewlines),
      !notify.isEmpty else {
      return false
    }
    let normalized = notify.lowercased()
    return normalized != "none"
      && !normalized.contains("nonetwork")
      && !normalized.contains("open_failed")
  }

  private static func hasCustomViewSessionEvidence() -> Bool {
    #if canImport(RGCxrClient)
    return RokidBridgeModule.customViewRunning
      || RokidBridgeModule.customViewDisplayInferred
      || (RokidBridgeModule.lastCustomViewOpenCommandAccepted == true && iosBleConnected())
      || (hasCustomViewNotifyEvidence() && iosBleConnected())
    #else
    return false
    #endif
  }

  private static func hasCustomViewMediaSession() -> Bool {
    #if canImport(RGCxrClient)
    return CxrClient.shared.auth.isAuthenticated()
      && iosBleConnected()
      && RokidBridgeModule.hasCustomViewSessionEvidence()
    #else
    return false
    #endif
  }

  private static func markCustomViewSessionEvidence(_ reason: String) {
    customViewDisplayInferred = true
    lastCustomViewSessionEvidenceAt = isoTimestamp()
    lastCustomViewSessionEvidenceReason = reason
    recordAuthDiagnostic(
      "custom_view_session_evidence",
      detail: "\(reason); running=\(customViewRunning); bleConnected=\(iosBleConnected()); device=\(iosBleDeviceName() ?? currentDeviceName ?? "unknown")"
    )
  }

  private static func clearCustomViewSessionEvidence(_ reason: String) {
    customViewDisplayInferred = false
    lastCustomViewSessionEvidenceReason = reason
    lastCustomViewSessionEvidenceAt = isoTimestamp()
  }

  private static func capabilitiesReady() -> Bool {
    #if canImport(RGCxrClient)
    return RokidBridgeModule.hasCustomViewMediaSession()
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
