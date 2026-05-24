import XCTest
@testable import HealthAgentMacCore

@MainActor
final class TodayViewModelTests: XCTestCase {
    func testTodayViewModelLoadsTopActionsAndMenuBarJobs() async {
        let service = StaticBootstrapService(bootstrap: .fixture)
        let model = TodayViewModel(service: service)

        await model.refresh()

        XCTAssertEqual(model.topActions.map(\.title), ["补水", "散步", "睡前放松"])
        XCTAssertEqual(model.activeJobs.map(\.jobType), ["gene_reanalysis"])
        XCTAssertNil(model.errorMessage)
    }

    func testTodayViewModelFallsBackToActionCardsForMenuBarActions() async {
        let service = StaticBootstrapService(bootstrap: .fixtureWithActionCardsOnly)
        let model = TodayViewModel(service: service)

        await model.refresh()

        XCTAssertEqual(model.topActions.map(\.title), ["复查血常规", "补剂试验"])
        XCTAssertEqual(model.topActions.map(\.domain), ["action_card", "action_card"])
    }
}

private struct StaticBootstrapService: DesktopBootstrapServicing {
    let bootstrap: DesktopBootstrap

    func fetchBootstrap() async throws -> DesktopBootstrap {
        bootstrap
    }
}

private extension DesktopBootstrap {
    static let fixture = DesktopBootstrap(
        user: DesktopUser(id: 3, name: "itsoso", email: nil),
        modelPreference: ModelPreference(llmModelID: "qwen"),
        dailyPlan: DailyOperatingPlan(
            planDate: "2026-05-23",
            actions: [
                DailyPlanAction(actionKey: "water", title: "补水", domain: "nutrition"),
                DailyPlanAction(actionKey: "walk", title: "散步", domain: "movement"),
                DailyPlanAction(actionKey: "sleep", title: "睡前放松", domain: "sleep"),
                DailyPlanAction(actionKey: "extra", title: "额外行动", domain: "measurement")
            ]
        ),
        trajectory: TrajectorySummary(focusDomains: ["metabolic_health"]),
        actionCards: [],
        recentMemory: [],
        recentRecordsSummary: RecentRecordsSummary(
            diet: DietRecordSummary(todayCount: 1, todayCalories: 520),
            water: WaterRecordSummary(todayCount: 1, todayTotalMl: 500)
        ),
        activeJobs: [
            DesktopJobSummary(id: 1, jobType: "gene_reanalysis", status: "queued", progress: 0)
        ]
    )

    static let fixtureWithActionCardsOnly = DesktopBootstrap(
        user: DesktopUser(id: 3, name: "itsoso", email: nil),
        modelPreference: ModelPreference(llmModelID: "qwen"),
        dailyPlan: DailyOperatingPlan(planDate: "2026-05-24", actions: []),
        trajectory: TrajectorySummary(focusDomains: ["metabolic_health"]),
        actionCards: [
            ActionCardSummary(id: 24, title: "复查血常规", status: "active", priority: 80),
            ActionCardSummary(id: 23, title: "补剂试验", status: "active", priority: 30)
        ],
        recentMemory: [],
        recentRecordsSummary: RecentRecordsSummary(),
        activeJobs: []
    )
}
