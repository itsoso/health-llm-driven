import XCTest
@testable import HealthAgentMacCore

final class KeychainTokenStoreTests: XCTestCase {
    func testKeychainTokenStoreSavesReadsAndClearsToken() async throws {
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
