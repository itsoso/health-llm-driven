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
  private let callbackScheme = "life.executor.health.rokid"
  private let querySchemes = ["rokidai"]
  private static var didInitializeCustomView = false
  private static var didBindRuntimeEvents = false
  private static var customViewRunning = false
  #if canImport(RGCxrClient)
  private static var cancellables = Set<AnyCancellable>()
  #endif

  public func definition() -> ModuleDefinition {
    Name("RokidBridge")

    AsyncFunction("getIntegrationStatus") { () -> [String: Any] in
      ensureCustomViewInitialized()
      let installed = canOpenHiRokid()
      return [
        "platform": "ios",
        "bridgeAvailable": true,
        "hiRokidInstalled": installed,
        "canOpenHiRokid": installed,
        "mode": "sdk_probe",
        "sdkLinked": sdkLinked(),
        "iosSdkDependencyMode": sdkDependencyMode(),
        "iosSdkCompatibility": "CXR-L iOS public sample uses RGCxrClient 1.0.1; 1.0.2 requires Rokid specs source",
        "sessionMode": "customView",
        "authorizationState": authorizationState(),
        "customViewRunning": customViewRunning(),
        "capabilitiesReady": capabilitiesReady(),
        "callbackScheme": callbackScheme,
        "querySchemes": querySchemes,
        "sdkClassProbe": sdkClassProbe(),
      ]
    }

    AsyncFunction("openHiRokid") { (promise: Promise) in
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

    AsyncFunction("requestAuthorization") { (scopes: [String], appName: String, promise: Promise) in
      #if canImport(RGCxrClient)
      ensureCustomViewInitialized()
      DispatchQueue.main.async {
        CxrClient.shared.auth.authenticate(
          scopes: scopes,
          appName: appName
        ) { result in
          switch result {
          case .success(let (token, sessionId)):
            promise.resolve([
              "ok": true,
              "tokenLength": token.count,
              "sessionId": sessionId as Any,
              "authorizationState": "authenticated",
            ])
          case .failure(let error):
            promise.resolve([
              "ok": false,
              "reason": String(describing: error),
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

    AsyncFunction("clearAuthorization") {
      #if canImport(RGCxrClient)
      CxrClient.shared.auth.clearAuthentication()
      return true
      #else
      return false
      #endif
    }

    AsyncFunction("openCustomView") { (view: String, promise: Promise) in
      #if canImport(RGCxrClient)
      ensureCustomViewInitialized()
      guard CxrClient.shared.auth.isAuthenticated() else {
        promise.resolve(["ok": false, "reason": "rokid_not_authorized"])
        return
      }
      CxrClient.shared.openCustomView(view) { success, errorCode in
        RokidBridgeModule.customViewRunning = success
        var response: [String: Any] = [
          "ok": success,
          "customViewRunning": success,
          "capabilitiesReady": success,
        ]
        if !success {
          response["errorCode"] = String(describing: errorCode as Any)
        }
        promise.resolve(response)
      }
      #else
      _ = view
      promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
      #endif
    }

    AsyncFunction("updateCustomView") { (view: String, promise: Promise) in
      #if canImport(RGCxrClient)
      ensureCustomViewInitialized()
      guard RokidBridgeModule.customViewRunning else {
        promise.resolve(["ok": false, "reason": "rokid_custom_view_not_ready"])
        return
      }
      CxrClient.shared.updateCustomView(view) { success in
        promise.resolve(["ok": success])
      }
      #else
      _ = view
      promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
      #endif
    }

    AsyncFunction("closeCustomView") { (view: String, promise: Promise) in
      #if canImport(RGCxrClient)
      ensureCustomViewInitialized()
      CxrClient.shared.closeCustomView(view) { success in
        if success {
          RokidBridgeModule.customViewRunning = false
        }
        promise.resolve([
          "ok": success,
          "customViewRunning": RokidBridgeModule.customViewRunning,
          "capabilitiesReady": self.capabilitiesReady(),
        ])
      }
      #else
      _ = view
      promise.resolve(["ok": false, "reason": "ios_sdk_not_linked"])
      #endif
    }

    AsyncFunction("takePhotoBase64") { (width: Int, height: Int, quality: Int, promise: Promise) in
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

    AsyncFunction("startRecord") { (type: String, codec: String, mode: String) -> [String: Any] in
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

    AsyncFunction("stopRecord") { (type: String) -> [String: Any] in
      #if canImport(RGCxrClient)
      CxrClient.shared.stopRecord(type)
      return ["ok": true]
      #else
      _ = type
      return ["ok": false, "reason": "ios_sdk_not_linked"]
      #endif
    }
  }

  private func canOpenHiRokid() -> Bool {
    guard let url = URL(string: "rokidai://") else {
      return false
    }
    return UIApplication.shared.canOpenURL(url)
  }

  private func ensureCustomViewInitialized() {
    #if canImport(RGCxrClient)
    if !RokidBridgeModule.didInitializeCustomView {
      CxrClient.initialize(mode: .customView, options: .init(appDisplayName: "Reva", pageName: nil))
      RokidBridgeModule.didInitializeCustomView = true
    }
    bindRuntimeEvents()
    #endif
  }

  private func bindRuntimeEvents() {
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

  private func sdkLinked() -> Bool {
    #if canImport(RGCxrClient)
    return true
    #else
    return false
    #endif
  }

  private func sdkDependencyMode() -> String {
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

  private func authorizationState() -> String {
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
    }
    #else
    return "unknown"
    #endif
  }

  private func customViewRunning() -> Bool {
    #if canImport(RGCxrClient)
    return RokidBridgeModule.customViewRunning
    #else
    return false
    #endif
  }

  private func capabilitiesReady() -> Bool {
    #if canImport(RGCxrClient)
    return CxrClient.shared.auth.isAuthenticated() && RokidBridgeModule.customViewRunning
    #else
    return false
    #endif
  }

  private func sdkClassProbe() -> [String: Bool] {
    [
      "RGCxrClient.CxrClient": classExists("RGCxrClient.CxrClient"),
      "RGCxrClient": classExists("RGCxrClient"),
      "RGCoreKit": classExists("RGCoreKit"),
    ]
  }

  private func classExists(_ className: String) -> Bool {
    NSClassFromString(className) != nil
  }

  #if canImport(RGCxrClient)
  private func audioCodec(_ codec: String) -> RGCxrAudioCodec {
    switch codec.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "oggopus", "ogg_opus", "opus":
      return .oggOpus
    case "mp3":
      return .mp3
    default:
      return .pcm
    }
  }

  private func audioMode(_ mode: String) -> RGCxrAudioMode {
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
  @objc public static func handleOpenURL(_ url: URL) -> Bool {
    #if canImport(RGCxrClient)
    return CxrClient.shared.handleOpenURL(url)
    #else
    _ = url
    return false
    #endif
  }
}
