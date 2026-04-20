import ExpoModulesCore
import Security

public class SharedKeychainModule: Module {
    private static let service = "life.executor.health.shared"
    private static let appGroup = "group.life.executor.health"
    private static let tokenKey = "siri_auth_token"

    public func definition() -> ModuleDefinition {
        Name("SharedKeychain")

        AsyncFunction("saveToken") { (token: String) -> Bool in
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
            return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
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
