import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalHealthKeyStoreTests: XCTestCase {
    func testPasscodeFailureCreatesNoKeySentinelOrVaultArtifacts() throws {
        let keychain = FakeLocalHealthKeychain()
        keychain.saveError = LocalHealthKeychainError.devicePasscodeRequired
        let files = FakeLocalHealthVaultFiles()
        let store = LocalHealthKeyStore(
            keychain: keychain,
            files: files,
            randomBytes: { Data(repeating: 7, count: 32) }
        )

        XCTAssertThrowsError(try store.createVaultKey(identityID: "local-user")) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .devicePasscodeRequired)
        }
        XCTAssertTrue(keychain.items.isEmpty)
        XCTAssertFalse(files.installSentinelExists)
        XCTAssertFalse(files.vaultArtifactsExist)
    }

    func testCreatedRootKeyUsesDeviceOnlyPasscodeProtectedAttributes() throws {
        let keychain = FakeLocalHealthKeychain()
        let files = FakeLocalHealthVaultFiles()
        let store = makeStore(keychain: keychain, files: files)

        let key = try store.createVaultKey(identityID: "local-user")

        XCTAssertEqual(key, Data(repeating: 7, count: 32))
        XCTAssertEqual(
            keychain.items.values.first,
            LocalHealthKeychainItem(
                service: LocalHealthKeyStore.service,
                account: "local-user",
                value: key,
                accessibility: .whenPasscodeSetThisDeviceOnly,
                synchronizable: false,
                useDataProtectionKeychain: true
            )
        )
        XCTAssertTrue(files.installSentinelExists)
    }

    func testMissingInstallSentinelPurgesOrphanedKeyAndVaultArtifacts() throws {
        let keychain = FakeLocalHealthKeychain()
        keychain.items["\(LocalHealthKeyStore.service)|orphan"] = .init(
            service: LocalHealthKeyStore.service,
            account: "orphan",
            value: Data(repeating: 9, count: 32),
            accessibility: .whenPasscodeSetThisDeviceOnly,
            synchronizable: false,
            useDataProtectionKeychain: true
        )
        let files = FakeLocalHealthVaultFiles()
        files.vaultArtifactsExist = true

        _ = try makeStore(keychain: keychain, files: files)
            .createVaultKey(identityID: "new-user")

        XCTAssertNil(keychain.items["\(LocalHealthKeyStore.service)|orphan"])
        XCTAssertNotNil(keychain.items["\(LocalHealthKeyStore.service)|new-user"])
        XCTAssertFalse(files.vaultArtifactsExist)
        XCTAssertTrue(files.installSentinelExists)
    }

    func testExistingCiphertextWithoutKeyIsRecoveryOnly() throws {
        let keychain = FakeLocalHealthKeychain()
        let files = FakeLocalHealthVaultFiles()
        files.installSentinelExists = true
        files.vaultArtifactsExist = true

        let state = try makeStore(keychain: keychain, files: files)
            .accessState(identityID: "local-user")

        XCTAssertEqual(state, .recoveryOnly)
    }

    func testCreateDoesNotOverwriteRecoveryOnlyCiphertext() throws {
        let keychain = FakeLocalHealthKeychain()
        let files = FakeLocalHealthVaultFiles()
        files.installSentinelExists = true
        files.vaultArtifactsExist = true

        XCTAssertThrowsError(
            try makeStore(keychain: keychain, files: files)
                .createVaultKey(identityID: "local-user")
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .vaultKeyMissing)
        }
        XCTAssertTrue(keychain.items.isEmpty)
        XCTAssertTrue(files.vaultArtifactsExist)
    }

    func testLockedKeychainReadDoesNotDeleteOrReplaceVault() throws {
        let keychain = FakeLocalHealthKeychain()
        keychain.loadError = LocalHealthKeychainError.protectedDataUnavailable
        let files = FakeLocalHealthVaultFiles()
        files.installSentinelExists = true
        files.vaultArtifactsExist = true

        XCTAssertThrowsError(
            try makeStore(keychain: keychain, files: files)
                .accessState(identityID: "local-user")
        ) { error in
            XCTAssertEqual(error as? LocalHealthKernelError, .protectedDataUnavailable)
        }
        XCTAssertTrue(files.vaultArtifactsExist)
        XCTAssertTrue(keychain.items.isEmpty)
    }

    func testDeleteVaultDeletesKeyBeforeCiphertextArtifacts() throws {
        var events: [String] = []
        let keychain = FakeLocalHealthKeychain()
        keychain.events = { events.append($0) }
        let files = FakeLocalHealthVaultFiles()
        files.events = { events.append($0) }
        let store = makeStore(keychain: keychain, files: files)
        _ = try store.createVaultKey(identityID: "local-user")
        events.removeAll()

        try store.deleteVault(identityID: "local-user")

        XCTAssertEqual(events, ["delete-key", "delete-artifacts"])
        XCTAssertTrue(keychain.items.isEmpty)
        XCTAssertFalse(files.vaultArtifactsExist)
    }

    private func makeStore(
        keychain: FakeLocalHealthKeychain,
        files: FakeLocalHealthVaultFiles
    ) -> LocalHealthKeyStore {
        LocalHealthKeyStore(
            keychain: keychain,
            files: files,
            randomBytes: { Data(repeating: 7, count: 32) }
        )
    }
}

private final class FakeLocalHealthKeychain: LocalHealthKeychainClient, @unchecked Sendable {
    var items: [String: LocalHealthKeychainItem] = [:]
    var loadError: Error?
    var saveError: Error?
    var events: ((String) -> Void)?

    func load(service: String, account: String) throws -> LocalHealthKeychainItem? {
        if let loadError {
            throw loadError
        }
        return items["\(service)|\(account)"]
    }

    func save(_ item: LocalHealthKeychainItem) throws {
        if let saveError {
            throw saveError
        }
        items["\(item.service)|\(item.account)"] = item
    }

    func delete(service: String, account: String) throws {
        events?("delete-key")
        items.removeValue(forKey: "\(service)|\(account)")
    }

    func deleteAll(service: String) throws {
        items = items.filter { !$0.key.hasPrefix("\(service)|") }
    }
}

private final class FakeLocalHealthVaultFiles: LocalHealthVaultFileClient, @unchecked Sendable {
    var installSentinelExists = false
    var vaultArtifactsExist = false
    var events: ((String) -> Void)?

    func createInstallSentinel() throws {
        installSentinelExists = true
    }

    func deleteVaultArtifacts() throws {
        events?("delete-artifacts")
        vaultArtifactsExist = false
    }
}
