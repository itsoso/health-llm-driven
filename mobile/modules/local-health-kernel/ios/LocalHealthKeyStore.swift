import Foundation

public enum LocalHealthKernelError: String, Error, Equatable, Sendable {
    case devicePasscodeRequired = "device_passcode_required"
    case protectedDataUnavailable = "protected_data_unavailable"
    case vaultKeyMissing = "vault_key_missing"
    case vaultNotEmpty = "vault_not_empty"
    case authenticationFailed = "authentication_failed"
    case invalidEnvelope = "invalid_envelope"
    case storageFailure = "storage_failure"
}

public enum LocalHealthKeychainError: Error, Equatable, Sendable {
    case devicePasscodeRequired
    case protectedDataUnavailable
    case unexpectedStatus(Int32)
}

public enum LocalHealthKeyAccessibility: String, Equatable, Sendable {
    case whenPasscodeSetThisDeviceOnly
}

public struct LocalHealthKeychainItem: Equatable, Sendable {
    public let service: String
    public let account: String
    public let value: Data
    public let accessibility: LocalHealthKeyAccessibility
    public let synchronizable: Bool
    public let useDataProtectionKeychain: Bool

    public init(
        service: String,
        account: String,
        value: Data,
        accessibility: LocalHealthKeyAccessibility,
        synchronizable: Bool,
        useDataProtectionKeychain: Bool
    ) {
        self.service = service
        self.account = account
        self.value = value
        self.accessibility = accessibility
        self.synchronizable = synchronizable
        self.useDataProtectionKeychain = useDataProtectionKeychain
    }
}

public protocol LocalHealthKeychainClient: Sendable {
    func load(service: String, account: String) throws -> LocalHealthKeychainItem?
    func save(_ item: LocalHealthKeychainItem) throws
    func delete(service: String, account: String) throws
    func deleteAll(service: String) throws
}

public protocol LocalHealthVaultFileClient: Sendable {
    var installSentinelExists: Bool { get }
    var vaultArtifactsExist: Bool { get }
    func createInstallSentinel() throws
    func deleteVaultArtifacts() throws
}

public enum LocalHealthVaultAccessState: Equatable, Sendable {
    case absent
    case ready(rootKey: Data)
    case recoveryOnly
}

public struct LocalHealthKeyStore: Sendable {
    public static let service = "life.executor.health.local-health-kernel"

    private let keychain: any LocalHealthKeychainClient
    private let files: any LocalHealthVaultFileClient
    private let randomBytes: @Sendable () throws -> Data

    public init(
        keychain: any LocalHealthKeychainClient,
        files: any LocalHealthVaultFileClient,
        randomBytes: @escaping @Sendable () throws -> Data
    ) {
        self.keychain = keychain
        self.files = files
        self.randomBytes = randomBytes
    }

    @discardableResult
    public func createVaultKey(identityID: String) throws -> Data {
        if !files.installSentinelExists {
            try keychain.deleteAll(service: Self.service)
            try files.deleteVaultArtifacts()
        } else {
            let existingItem: LocalHealthKeychainItem?
            do {
                existingItem = try keychain.load(
                    service: Self.service,
                    account: identityID
                )
            } catch LocalHealthKeychainError.protectedDataUnavailable {
                throw LocalHealthKernelError.protectedDataUnavailable
            } catch {
                throw LocalHealthKernelError.storageFailure
            }
            if existingItem != nil {
                throw LocalHealthKernelError.vaultNotEmpty
            }
            if files.vaultArtifactsExist {
                throw LocalHealthKernelError.vaultKeyMissing
            }
        }

        let rootKey = try randomBytes()
        guard rootKey.count == 32 else {
            throw LocalHealthKernelError.storageFailure
        }
        let item = LocalHealthKeychainItem(
            service: Self.service,
            account: identityID,
            value: rootKey,
            accessibility: .whenPasscodeSetThisDeviceOnly,
            synchronizable: false,
            useDataProtectionKeychain: true
        )
        do {
            try keychain.save(item)
        } catch LocalHealthKeychainError.devicePasscodeRequired {
            throw LocalHealthKernelError.devicePasscodeRequired
        } catch LocalHealthKeychainError.protectedDataUnavailable {
            throw LocalHealthKernelError.protectedDataUnavailable
        } catch {
            throw LocalHealthKernelError.storageFailure
        }

        do {
            try files.createInstallSentinel()
        } catch {
            try? keychain.delete(service: Self.service, account: identityID)
            throw LocalHealthKernelError.storageFailure
        }
        return rootKey
    }

    public func accessState(identityID: String) throws -> LocalHealthVaultAccessState {
        do {
            if let item = try keychain.load(service: Self.service, account: identityID) {
                return .ready(rootKey: item.value)
            }
            return files.vaultArtifactsExist ? .recoveryOnly : .absent
        } catch LocalHealthKeychainError.protectedDataUnavailable {
            throw LocalHealthKernelError.protectedDataUnavailable
        } catch {
            throw LocalHealthKernelError.storageFailure
        }
    }

    public func deleteVault(identityID: String) throws {
        do {
            try keychain.delete(service: Self.service, account: identityID)
            try files.deleteVaultArtifacts()
        } catch {
            throw LocalHealthKernelError.storageFailure
        }
    }
}
