import ExpoModulesCore
import Foundation
import Security

public class SharedKeychainModule: Module {
    private static let service = "life.executor.health.shared"
    private static let appGroup = "group.life.executor.health"
    private static let tokenKey = "siri_auth_token"
    private static let legacyMarkerKey = "siri_debug_marker"
    private static let tokenChangedNotification = Notification.Name("RevaSharedAuthTokenChanged")

    public func definition() -> ModuleDefinition {
        Name("SharedKeychain")

        AsyncFunction("saveToken") { (token: String) -> Int in
            SharedKeychainModule.purgeLegacyDefaults()
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
            ]
            SecItemDelete(query as CFDictionary)
            var add = query
            add[kSecValueData as String] = Data(token.utf8)
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            let keychainStatus = SecItemAdd(add as CFDictionary, nil)
            NotificationCenter.default.post(name: SharedKeychainModule.tokenChangedNotification, object: nil)

            return Int(keychainStatus)
        }

        AsyncFunction("deleteToken") {
            SharedKeychainModule.purgeLegacyDefaults()
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
            ]
            SecItemDelete(query as CFDictionary)
            NotificationCenter.default.post(name: SharedKeychainModule.tokenChangedNotification, object: nil)
        }

        AsyncFunction("readToken") { () -> String? in
            SharedKeychainModule.purgeLegacyDefaults()

            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
                kSecReturnData as String: true,
                kSecMatchLimit as String: kSecMatchLimitOne,
            ]
            var result: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            guard status == errSecSuccess,
                  let data = result as? Data,
                  let token = String(data: data, encoding: .utf8),
                  !token.isEmpty else {
                return nil
            }
            return token
        }

        /// 诊断只报告 Keychain 状态，不回读或暴露 token。
        AsyncFunction("readDiagnostic") { () -> String in
            SharedKeychainModule.purgeLegacyDefaults()
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
                kSecReturnData as String: true,
            ]
            var result: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            return "KC=\(status)"
        }
    }

    private static func purgeLegacyDefaults() {
        guard let defaults = UserDefaults(suiteName: appGroup) else { return }
        defaults.removeObject(forKey: tokenKey)
        defaults.removeObject(forKey: legacyMarkerKey)
    }
}
