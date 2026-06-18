import ExpoModulesCore
import UIKit

public class RokidBridgeAppDelegateSubscriber: ExpoAppDelegateSubscriber {
  public func application(
    _ app: UIApplication,
    open url: URL,
    options: [UIApplication.OpenURLOptionsKey: Any] = [:]
  ) -> Bool {
    RokidBridgeURLHandler.observeOpenURL(url)
    return RokidBridgeURLHandler.handleOpenURL(url)
  }
}
