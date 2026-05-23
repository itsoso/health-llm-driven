import Foundation
import XCTest
@testable import HealthAgentMacCore

final class UserDefaultsTokenStoreTests: XCTestCase {
    private var suiteName: String!
    private var defaults: UserDefaults!

    override func setUp() {
        super.setUp()
        suiteName = "UserDefaultsTokenStoreTests-\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)!
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        defaults = nil
        suiteName = nil
        super.tearDown()
    }

    func testUserDefaultsTokenStoreSavesReadsAndClearsWithoutKeychain() async throws {
        let store = UserDefaultsTokenStore(defaults: defaults)

        try await store.setToken("jwt-token")

        let savedToken = await store.getToken()
        XCTAssertEqual(savedToken, "jwt-token")

        await store.clearToken()

        let clearedToken = await store.getToken()
        XCTAssertNil(clearedToken)
    }
}
