import AppKit
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
            "trace",
            "settings"
        ])
    }

    func testSidebarDestinationIconsResolveToAvailableSystemSymbols() {
        for destination in SidebarDestination.allCases {
            XCTAssertNotNil(
                NSImage(systemSymbolName: destination.systemImage, accessibilityDescription: nil),
                "\(destination.id) uses unavailable SF Symbol \(destination.systemImage)"
            )
        }
    }

    func testAPIEndpointDefaultsToProductionV1() {
        XCTAssertEqual(
            APIEndpoint.defaultBaseURL.absoluteString,
            "https://health.executor.life/api/v1"
        )
    }

    func testAPIEndpointResolvesStoredBaseURLAndFallsBackForInvalidValue() {
        let suiteName = "HealthAgentMacCoreTests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        defaults.set("https://staging.example.test/api/v1", forKey: APIEndpoint.baseURLDefaultsKey)
        XCTAssertEqual(
            APIEndpoint.resolvedBaseURL(defaults: defaults).absoluteString,
            "https://staging.example.test/api/v1"
        )

        defaults.set("not a url", forKey: APIEndpoint.baseURLDefaultsKey)
        XCTAssertEqual(APIEndpoint.resolvedBaseURL(defaults: defaults), APIEndpoint.defaultBaseURL)
    }

    func testAppLocalizationDefaultsToChineseAndSupportsEnglish() {
        XCTAssertEqual(AppLanguage.defaultLanguage, .zh)
        XCTAssertEqual(AppLanguage(storedValue: "missing"), .zh)
        XCTAssertEqual(L10n.text("Today", language: .zh), "今日")
        XCTAssertEqual(L10n.text("Today", language: .en), "Today")
        XCTAssertEqual(L10n.text("Reopen App", language: .zh), "重新打开 App")
        XCTAssertEqual(L10n.text("Reopen App", language: .en), "Reopen App")
    }

    func testMacAppLifecyclePolicyRequiresSingleInstanceAndQuitOnWindowClose() {
        XCTAssertEqual(MacAppLifecyclePolicy.bundleIdentifier, "life.executor.health.mac")
        XCTAssertTrue(MacAppLifecyclePolicy.preventsMultipleInstances)
        XCTAssertTrue(MacAppLifecyclePolicy.terminatesAfterLastWindowClosed)
        XCTAssertEqual(MacAppLifecyclePolicy.multipleInstancePlistKey, "LSMultipleInstancesProhibited")
    }
}
