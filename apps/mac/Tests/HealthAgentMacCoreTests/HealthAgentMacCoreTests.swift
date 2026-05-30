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
            "workouts",
            "goals",
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
        XCTAssertEqual(L10n.text("disease_risk", language: .zh), "疾病风险")
        XCTAssertEqual(L10n.text("drug_sensitivity", language: .zh), "药物敏感性")
        XCTAssertEqual(L10n.text("height_trait", language: .zh), "身高/体征")
        XCTAssertEqual(L10n.text("variants", language: .zh), "个位点")
        XCTAssertEqual(L10n.text("High", language: .zh), "高")
        XCTAssertEqual(L10n.text("Medium", language: .zh), "中")
    }

    func testMacAppLifecyclePolicyRequiresSingleInstanceAndQuitOnWindowClose() {
        XCTAssertEqual(MacAppLifecyclePolicy.bundleIdentifier, "life.executor.health.mac")
        XCTAssertTrue(MacAppLifecyclePolicy.preventsMultipleInstances)
        XCTAssertTrue(MacAppLifecyclePolicy.terminatesAfterLastWindowClosed)
        XCTAssertEqual(MacAppLifecyclePolicy.multipleInstancePlistKey, "LSMultipleInstancesProhibited")
    }
}
