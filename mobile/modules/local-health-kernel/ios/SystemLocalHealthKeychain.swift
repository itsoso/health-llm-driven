import Foundation
import Security

public struct SystemLocalHealthKeychain: LocalHealthKeychainClient {
    public init() {}

    public func load(
        service: String,
        account: String
    ) throws -> LocalHealthKeychainItem? {
        var query = baseQuery(service: service, account: account)
        query[kSecReturnData as String] = kCFBooleanTrue
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess, let data = result as? Data else {
            throw mappedError(status, creatingPasscodeBoundItem: false)
        }
        return LocalHealthKeychainItem(
            service: service,
            account: account,
            value: data,
            accessibility: .whenPasscodeSetThisDeviceOnly,
            synchronizable: false,
            useDataProtectionKeychain: true
        )
    }

    public func save(_ item: LocalHealthKeychainItem) throws {
        guard item.accessibility == .whenPasscodeSetThisDeviceOnly,
              !item.synchronizable,
              item.useDataProtectionKeychain else {
            throw LocalHealthKeychainError.unexpectedStatus(errSecParam)
        }
        var query = baseQuery(service: item.service, account: item.account)
        query[kSecValueData as String] = item.value
        query[kSecAttrAccessible as String] =
            kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw mappedError(status, creatingPasscodeBoundItem: true)
        }
    }

    public func delete(service: String, account: String) throws {
        let status = SecItemDelete(
            baseQuery(service: service, account: account) as CFDictionary
        )
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw mappedError(status, creatingPasscodeBoundItem: false)
        }
    }

    public func deleteAll(service: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrSynchronizable as String: kCFBooleanFalse as Any,
            kSecUseDataProtectionKeychain as String: kCFBooleanTrue as Any,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw mappedError(status, creatingPasscodeBoundItem: false)
        }
    }

    private func baseQuery(service: String, account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrSynchronizable as String: kCFBooleanFalse as Any,
            kSecUseDataProtectionKeychain as String: kCFBooleanTrue as Any,
        ]
    }

    private func mappedError(
        _ status: OSStatus,
        creatingPasscodeBoundItem: Bool
    ) -> LocalHealthKeychainError {
        if creatingPasscodeBoundItem,
           status == errSecAuthFailed || status == errSecInteractionNotAllowed {
            return .devicePasscodeRequired
        }
        if status == errSecInteractionNotAllowed || status == errSecNotAvailable {
            return .protectedDataUnavailable
        }
        return .unexpectedStatus(status)
    }
}
