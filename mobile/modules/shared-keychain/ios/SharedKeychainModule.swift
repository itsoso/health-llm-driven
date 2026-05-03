import ExpoModulesCore
import Security

public class SharedKeychainModule: Module {
    private static let service = "life.executor.health.shared"
    private static let appGroup = "group.life.executor.health"
    private static let tokenKey = "siri_auth_token"

    public func definition() -> ModuleDefinition {
        Name("SharedKeychain")

        // Returns OSStatus as Int. 0 = success. Negative = SecItem error code,
        // e.g. -34018 errSecMissingEntitlement. Never throws —— Swift errors
        // from keychain are returned as OSStatus so JS can surface them in UI.
        AsyncFunction("saveToken") { (token: String) -> Int in
            let data = Data(token.utf8)
            let query: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: SharedKeychainModule.service,
                kSecAttrAccount as String: SharedKeychainModule.tokenKey,
                kSecAttrAccessGroup as String: SharedKeychainModule.appGroup,
            ]
            SecItemDelete(query as CFDictionary)
            var add = query
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
            let status = SecItemAdd(add as CFDictionary, nil)
            return Int(status)
        }

        AsyncFunction("deleteToken") {
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
