import XCTest
@testable import HealthAgentMacCore

final class DesktopDashboardLayoutPolicyTests: XCTestCase {
    func testWideWindowUsesLeadingAppleSidebarSpacingAndExpandsMainColumn() {
        let layout = DesktopDashboardLayoutPolicy.metrics(forAvailableWidth: 1_898)

        XCTAssertEqual(layout.horizontalPadding, 24)
        XCTAssertEqual(layout.columnSpacing, 20)
        XCTAssertEqual(layout.rightRailWidth, 360)
        XCTAssertEqual(layout.contentMaxWidth, 1_660)
        XCTAssertGreaterThanOrEqual(layout.mainColumnWidth, 1_280)
    }

    func testMediumWindowKeepsReadableRailsWithoutCenteringContent() {
        let layout = DesktopDashboardLayoutPolicy.metrics(forAvailableWidth: 1_280)

        XCTAssertEqual(layout.horizontalPadding, 20)
        XCTAssertEqual(layout.columnSpacing, 16)
        XCTAssertEqual(layout.rightRailWidth, 320)
        XCTAssertEqual(layout.contentMaxWidth, 1_240)
        XCTAssertEqual(layout.mainColumnWidth, 904)
    }
}
