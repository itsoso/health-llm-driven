import XCTest
@testable import HealthAgentMacCore

final class HealthAgentMacCoreTests: XCTestCase {
    func testSidebarDestinationsCoverMobileParityAndDesktopWorkflows() {
        let ids = SidebarDestination.allCases.map(\.id)

        XCTAssertEqual(ids, [
            "today",
            "agent",
            "record",
            "data",
            "genetics",
            "knowledge",
            "jobs",
            "settings"
        ])
    }

    func testAPIEndpointDefaultsToProductionV1() {
        XCTAssertEqual(
            APIEndpoint.defaultBaseURL.absoluteString,
            "https://health.executor.life/api/v1"
        )
    }
}
