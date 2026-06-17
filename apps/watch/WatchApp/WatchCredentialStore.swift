import Foundation
import Security

/// Watch 本机凭据。token 只落 Keychain;apiBase 不是秘密,放 UserDefaults 便于灰度切换。
final class WatchCredentialStore {
    static let shared = WatchCredentialStore()

    static let contextTokenKey = "watch_auth_token"
    static let contextTokenDeletedKey = "watch_auth_token_deleted"
    static let contextAPIBaseKey = "watch_api_base"

    private let service = "life.executor.health.watch"
    private let tokenAccount = "watch_auth_token"
    private let apiBaseKey = "watch.api_base"
    private let defaults = UserDefaults.standard

    func applyApplicationContext(_ context: [String: Any]) {
        if let apiBase = context[Self.contextAPIBaseKey] as? String, !apiBase.isEmpty {
            defaults.set(apiBase, forKey: apiBaseKey)
        }
        if (context[Self.contextTokenDeletedKey] as? Bool) == true {
            deleteToken()
            return
        }
        if let token = context[Self.contextTokenKey] as? String, !token.isEmpty {
            saveToken(token)
        }
    }

    func apiBase() -> String {
        defaults.string(forKey: apiBaseKey) ?? WatchBackendRequest.defaultAPIBase
    }

    func token() -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func saveToken(_ token: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = Data(token.utf8)
        add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock
        SecItemAdd(add as CFDictionary, nil)
    }

    func deleteToken() {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: tokenAccount,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
