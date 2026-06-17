import ExpoModulesCore
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

  public func definition() -> ModuleDefinition {
    Name("RokidBridge")

    AsyncFunction("getIntegrationStatus") { () -> [String: Any] in
      let installed = canOpenHiRokid()
      return [
        "platform": "ios",
        "bridgeAvailable": true,
        "hiRokidInstalled": installed,
        "canOpenHiRokid": installed,
        "mode": "sdk_probe",
        "sdkLinked": sdkLinked(),
        "iosSdkDependencyMode": sdkDependencyMode(),
        "iosSdkCompatibility": "RGCxrClient 1.0.1 requires a Swift toolchain compatible with Rokid's binary framework",
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
      CxrClient.shared.auth.config = RGCxrClientAuthConfig(
        serverScheme: "rokidai",
        serverHost: "connect",
        callbackScheme: callbackScheme,
        callbackHost: "auth",
        callbackPath: "/callback",
        requestTimeout: 60.0,
        timestampTolerance: 300.0
      )
      DispatchQueue.main.async {
        CxrClient.shared.auth.authenticate(
          scopes: scopes,
          bundleId: Bundle.main.bundleIdentifier,
          appName: appName
        ) { result in
          switch result {
          case .success(let auth):
            promise.resolve([
              "ok": true,
              "tokenLength": auth.token.count,
              "sessionId": auth.sessionId as Any,
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

    AsyncFunction("openCustomView") { (view: String) -> [String: Any] in
      #if canImport(RGCxrClient)
      CxrClient.shared.openCustomView(view)
      return ["ok": true]
      #else
      _ = view
      return ["ok": false, "reason": "ios_sdk_not_linked"]
      #endif
    }

    AsyncFunction("updateCustomView") { (view: String) -> [String: Any] in
      #if canImport(RGCxrClient)
      CxrClient.shared.updateCustomView(view)
      return ["ok": true]
      #else
      _ = view
      return ["ok": false, "reason": "ios_sdk_not_linked"]
      #endif
    }

    AsyncFunction("closeCustomView") { (view: String) -> [String: Any] in
      #if canImport(RGCxrClient)
      CxrClient.shared.closeCustomView(view)
      return ["ok": true]
      #else
      _ = view
      return ["ok": false, "reason": "ios_sdk_not_linked"]
      #endif
    }

    AsyncFunction("takePhotoBase64") { (width: Int, height: Int, quality: Int, promise: Promise) in
      #if canImport(RGCxrClient)
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
    #else
    return "opt_in_disabled"
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
    return CxrClient.shared.handleOpenURL(url) || CxrClient.shared.auth.handleCallback(url: url)
    #else
    _ = url
    return false
    #endif
  }
}
