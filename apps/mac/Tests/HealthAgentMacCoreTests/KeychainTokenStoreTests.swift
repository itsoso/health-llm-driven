import XCTest
@testable import HealthAgentMacCore

final class KeychainTokenStoreTests: XCTestCase {
    func testKeychainStorePurgesHistoricalUserDefaultsTokenOnInit() {
        let suiteName = "KeychainTokenStoreTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.set("legacy-jwt", forKey: UserDefaultsTokenStore.defaultsKey)

        _ = KeychainTokenStore(
            service: "life.executor.health.tests",
            account: "token-\(UUID().uuidString)",
            legacyDefaults: defaults
        )

        XCTAssertNil(defaults.string(forKey: UserDefaultsTokenStore.defaultsKey))
        defaults.removePersistentDomain(forName: suiteName)
    }

    func testKeychainTokenStoreSavesReadsAndClearsToken() async throws {
        guard ProcessInfo.processInfo.environment["HEALTH_RUN_KEYCHAIN_TESTS"] == "1" else {
            throw XCTSkip("Real macOS keychain tests are opt-in to avoid blocking on GUI authorization prompts.")
        }

        let store = KeychainTokenStore(
            service: "life.executor.health.tests",
            account: "token-\(UUID().uuidString)"
        )

        try await store.setToken("secret-token")
        let saved = await store.getToken()
        XCTAssertEqual(saved, "secret-token")

        await store.clearToken()
        let cleared = await store.getToken()
        XCTAssertNil(cleared)
    }
}
