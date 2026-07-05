import XCTest
@testable import HealthAgentMacCore

final class DynamicCardRoutingTests: XCTestCase {
    func testChatPromptRouteResolves() {
        let r = DynamicCardRouting.resolve(route: "/chat?prompt=%E6%A0%B8%E5%AF%B9%E7%94%A8%E8%8D%AF")
        guard case .chatPrompt(let p)? = r else { return XCTFail("expected chatPrompt, got \(String(describing: r))") }
        XCTAssertEqual(p, "核对用药")
    }

    func testKnownPageRoutesMapToSidebar() {
        XCTAssertEqual(DynamicCardRouting.resolve(route: "/medications?draft=medication&name=x"), .sidebar(.prescriptions))
        XCTAssertEqual(DynamicCardRouting.resolve(route: "/agenda"), .sidebar(.agenda))
        XCTAssertEqual(DynamicCardRouting.resolve(route: "/my-progress"), .sidebar(.review))
        XCTAssertEqual(DynamicCardRouting.resolve(route: "/indicator-history?type=weight"), .sidebar(.data))
    }

    func testTabsGroupSegmentIsStripped() {
        XCTAssertEqual(DynamicCardRouting.resolve(route: "/(tabs)/agenda"), .sidebar(.agenda))
    }

    func testUnknownRouteNotActionable() {
        XCTAssertNil(DynamicCardRouting.resolve(route: "/some-unknown-screen"))
        XCTAssertFalse(DynamicCardRouting.isActionable(route: "/some-unknown-screen"))
        XCTAssertNil(DynamicCardRouting.resolve(route: "//evil.example"))
        XCTAssertNil(DynamicCardRouting.resolve(route: "https://evil.example"))
    }

    func testEmptyChatPromptNotActionable() {
        XCTAssertNil(DynamicCardRouting.resolve(route: "/chat?prompt="))
    }
}
