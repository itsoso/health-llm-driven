import ExpoModulesCore
import Security

public class SharedKeychainModule: Module {
    private static let service = "life.executor.health.shared"
    private static let appGroup = "group.life.executor.health"
    private static let tokenKey = "siri_auth_token"
    private static let markerKey = "siri_debug_marker"

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
        }
    }
}
