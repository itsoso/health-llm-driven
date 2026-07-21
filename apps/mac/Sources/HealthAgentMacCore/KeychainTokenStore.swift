import Foundation
import Security

public enum KeychainTokenStoreError: Error, Equatable {
    case saveFailed(OSStatus)
}

public final class KeychainTokenStore: AuthTokenStoring, @unchecked Sendable {
    private let service: String
    private let account: String

    public init(
        service: String = "life.executor.health.mac",
        account: String = "auth-token-v2",
        legacyDefaults: UserDefaults? = .standard
    ) {
        self.service = service
        self.account = account
        legacyDefaults?.removeObject(forKey: UserDefaultsTokenStore.defaultsKey)
    }

    public func setToken(_ token: String) async throws {
        let data = Data(token.utf8)
        let lookupQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecUseAuthenticationUI as String: kSecUseAuthenticationUISkip
        ]

        let updateStatus = SecItemUpdate(
            lookupQuery as CFDictionary,
            [kSecValueData as String: data] as CFDictionary
        )
        if updateStatus == errSecSuccess {
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainTokenStoreError.saveFailed(updateStatus)
        }

        var addQuery = lookupQuery
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly

        let status = SecItemAdd(addQuery as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw KeychainTokenStoreError.saveFailed(status)
        }
    }

    public func getToken() async -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecUseAuthenticationUI as String: kSecUseAuthenticationUISkip
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    public func clearToken() async {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecUseAuthenticationUI as String: kSecUseAuthenticationUISkip
        ]
        SecItemDelete(query as CFDictionary)
    }
}
