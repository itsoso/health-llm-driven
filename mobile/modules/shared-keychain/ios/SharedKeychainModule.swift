import ExpoModulesCore
import Foundation
import Security

public class SharedKeychainModule: Module {
    private static let service = "life.executor.health.shared"
    private static let appGroup = "group.life.executor.health"
    private static let tokenKey = "siri_auth_token"
    private static let markerKey = "siri_debug_marker"
    private static let tokenChangedNotification = Notification.Name("RevaSharedAuthTokenChanged")

    public func definition() -> ModuleDefinition {
        Name("SharedKeychain")

        AsyncFunction("saveToken") { (token: String) -> Int in
            var anySuccess = false

            // Write to App Group UserDefaults (primary)
            if let defaults = UserDefaults(suiteName: SharedKeychainModule.appGroup) {
                defaults.set(token, forKey: SharedKeychainModule.tokenKey)
                // Marker 带时间戳 —— Siri 端能读到它说明 UserDefaults 确实跨进程共享
                let ts = ISO8601DateFormatter().string(from: Date())
                defaults.set(ts, forKey: SharedKeychainModule.markerKey)
                defaults.synchronize()
                anySuccess = true
            }

            // Write to shared keychain (fallback)
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
            ]
            SecItemDelete(query as CFDictionary)
            var add = query
            add[kSecValueData as String] = Data(token.utf8)
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            let keychainStatus = SecItemAdd(add as CFDictionary, nil)
            if keychainStatus == errSecSuccess {
                anySuccess = true
            }
            NotificationCenter.default.post(name: SharedKeychainModule.tokenChangedNotification, object: nil)

            return anySuccess ? 0 : Int(keychainStatus)
        }

        AsyncFunction("deleteToken") {
            if let defaults = UserDefaults(suiteName: SharedKeychainModule.appGroup) {
                defaults.removeObject(forKey: SharedKeychainModule.tokenKey)
                defaults.removeObject(forKey: SharedKeychainModule.markerKey)
            }
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
            ]
            SecItemDelete(query as CFDictionary)
            NotificationCenter.default.post(name: SharedKeychainModule.tokenChangedNotification, object: nil)
        }

        /// 诊断: 主 App 读回自己写到 App Group UserDefaults 的 marker 和 token。
        /// 如果这里读不到, 说明 UserDefaults(suiteName:) 在主 App 进程里就降级了,
        /// 根本没写到真正的 shared container —— Siri 自然也读不到。
        AsyncFunction("readDiagnostic") { () -> String in
            var parts: [String] = []

            if let defaults = UserDefaults(suiteName: SharedKeychainModule.appGroup) {
                let marker = defaults.string(forKey: SharedKeychainModule.markerKey)
                let token = defaults.string(forKey: SharedKeychainModule.tokenKey)
                parts.append("UD open")
                parts.append("marker=\(marker ?? "nil")")
                parts.append("token=\(token?.count != nil ? "\(token!.count)ch" : "nil")")
            } else {
                parts.append("UD nil")
            }

            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
                kSecReturnData as String: true,
            ]
            var result: AnyObject?
            let status = SecItemCopyMatching(query as CFDictionary, &result)
            parts.append("KC=\(status)")

            return parts.joined(separator: ", ")
        }
    }
}
