import AppKit
import XCTest
@testable import HealthAgentMacCore

final class HealthAgentMacCoreTests: XCTestCase {
    func testSidebarDestinationsCoverMobileParityAndDesktopWorkflows() {
        let ids = SidebarDestination.allCases.map(\.id)

        XCTAssertEqual(ids, [
            "today",
            "schedule",
            "agenda",
            "review",
            "timeline",
            "calendar",
            "agent",
            "record",
            "data",
            "dataSources",
            "dataConnections",
            "prescriptions",
            "liver",
            "healthExtras",
            "genetics",
            "knowledge",
            "workouts",
            "goals",
            "jobs",
            "trace",
            "settings"
        ])
    }

    func testInsightsSectionConsolidatesToHubPlusGenetics() {
        let sections = SidebarDestination.sidebarSections
        let insights = sections.first { $0.id == "insights" }
        XCTAssertNotNil(insights, "insights section must exist")
        // 洞察收敛为两行:健康洞察 hub(.healthExtras)+ 基因。
        XCTAssertEqual(insights?.items, [.healthExtras, .genetics])

        // 复盘 / 肝脏趋势 不再是独立侧栏行(改由 hub 承载),但仍是有效 enum case
        // (命令面板 / 证据深链 / 动态卡片路由用)。
        XCTAssertFalse(SidebarDestination.sidebarVisible.contains(.review))
        XCTAssertFalse(SidebarDestination.sidebarVisible.contains(.liver))
        XCTAssertTrue(SidebarDestination.allCases.contains(.review))
        XCTAssertTrue(SidebarDestination.allCases.contains(.liver))
    }

    func testOriginatorLivesInMedicationSection() {
        let sections = SidebarDestination.sidebarSections
        let medication = sections.first { $0.id == "medication" }
        XCTAssertNotNil(medication, "medication section must exist")
        XCTAssertEqual(medication?.items, [.prescriptions])
        XCTAssertEqual(medication?.titleKey, "Medication")
        // 原研药不再挂在洞察下。
        let insights = sections.first { $0.id == "insights" }
        XCTAssertFalse(insights?.items.contains(.prescriptions) ?? false)
    }

    func testHealthInsightsHubEntryAndTabLabelsLocalize() {
        XCTAssertEqual(SidebarDestination.healthExtras.title(language: .zh), "健康洞察")
        XCTAssertEqual(L10n.text("Advanced Abilities", language: .zh), "进阶能力")
        XCTAssertEqual(L10n.text("Organ Trends", language: .zh), "器官趋势")
        XCTAssertEqual(L10n.text("Review", language: .zh), "复盘")
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

    func testSingleInstanceLaunchGuardActivatesExistingAppAndTerminatesDuplicate() {
        let action = MacSingleInstanceLaunchGuard.launchAction(
            currentProcessIdentifier: 100,
            runningApplications: [
                .init(processIdentifier: 100, isTerminated: false),
                .init(processIdentifier: 200, isTerminated: false)
            ],
            preventsMultipleInstances: true
        )

        XCTAssertEqual(action, .activateExistingAndTerminate(processIdentifier: 200))
    }

    func testSingleInstanceLaunchGuardContinuesWhenOnlyCurrentOrTerminatedInstancesExist() {
        let action = MacSingleInstanceLaunchGuard.launchAction(
            currentProcessIdentifier: 100,
            runningApplications: [
                .init(processIdentifier: 100, isTerminated: false),
                .init(processIdentifier: 200, isTerminated: true)
            ],
            preventsMultipleInstances: true
        )

        XCTAssertEqual(action, .continueLaunching)
    }

    func testSplitCompoundMetricValueStacksMiddotJoinedValue() {
        // 今日蛋白's compound value splits on the middot into primary + secondary.
        let split = ChatTranscriptHTML.splitCompoundMetricValue("33/114g · 还差81g")
        XCTAssertEqual(split?.primary, "33/114g")
        XCTAssertEqual(split?.secondary, "还差81g")
    }

    func testSplitCompoundMetricValueReturnsNilForPlainValue() {
        // Plain single values (the 5 per-meal tiles) must NOT be split.
        XCTAssertNil(ChatTranscriptHTML.splitCompoundMetricValue("430kcal"))
        XCTAssertNil(ChatTranscriptHTML.splitCompoundMetricValue("15g"))
        // A middot with an empty side is not a valid compound → single value.
        XCTAssertNil(ChatTranscriptHTML.splitCompoundMetricValue("33/114g · "))
    }
}
