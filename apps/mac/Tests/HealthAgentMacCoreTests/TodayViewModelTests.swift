import XCTest
@testable import HealthAgentMacCore

@MainActor
final class TodayViewModelTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

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

    func testTodayViewModelPrefersAhengDynamicTodayActions() async {
        let service = StaticBootstrapService(bootstrap: .fixture)
        let dynamicService = StaticTodayDynamicViewService(view: .fixtureDailyArtifact)
        let model = TodayViewModel(service: service, dynamicViewService: dynamicService)

        await model.refresh()

        XCTAssertEqual(model.topActions.map(\.title), ["阿衡动态生成的餐后步行"])
        XCTAssertEqual(model.topActions.map(\.domain), ["daily_artifact"])
        XCTAssertEqual(model.activeJobs.map(\.jobType), ["gene_reanalysis"])
        XCTAssertNil(model.errorMessage)
    }

    func testTodayViewModelFallsBackToBootstrapWhenDynamicTodayFails() async {
        let service = StaticBootstrapService(bootstrap: .fixture)
        let dynamicService = StaticTodayDynamicViewService(error: APIError.emptyResponse)
        let model = TodayViewModel(service: service, dynamicViewService: dynamicService)

        await model.refresh()

        XCTAssertEqual(model.topActions.map(\.title), ["补水", "散步", "睡前放松"])
        XCTAssertNil(model.errorMessage)
    }

    func testTodayDynamicViewClientPostsMacContextToDynamicViewAPI() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/dynamic-views/today")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token-123")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")

            let body = try XCTUnwrap(request.bodyDataForTesting)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(object["surface"] as? String, "mobile.today")
            XCTAssertEqual(object["trigger"] as? String, "pull_refresh")
            let context = try XCTUnwrap(object["client_context"] as? [String: Any])
            XCTAssertEqual(context["client"] as? String, "mac")
            XCTAssertEqual(context["client_capabilities"] as? [String], ["daily_artifact", "runtime_agenda"])

            let data = """
            {
              "view_id": "today:2026-06-29:abc",
              "surface": "mobile.today",
              "trigger": "pull_refresh",
              "generated_by": "aheng_today_view_v1",
              "context_hash": "abc",
              "safety_boundary": "健康管理行动建议,不替代医生诊断。",
              "sections": [
                {
                  "slot": "hero",
                  "priority": 100,
                  "title": "今日状态",
                  "cards": [
                    {
                      "type": "daily_artifact",
                      "render": {"atom": "daily_artifact", "dedupe_key": "title:walk", "reason": "primary_today_action"},
                      "data": {
                        "top_action": {"id": "walk", "title": "餐后步行"}
                      }
                    }
                  ]
                }
              ]
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let apiClient = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        )
        let client = TodayDynamicViewClient(apiClient: apiClient)

        let view = try await client.fetchTodayDynamicView(trigger: "pull_refresh")

        XCTAssertEqual(view.viewID, "today:2026-06-29:abc")
        XCTAssertEqual(view.menuBarActions.map(\.title), ["餐后步行"])
        XCTAssertEqual(view.sections.first?.cards.first?.render?.atom, "daily_artifact")
    }
}

private struct StaticBootstrapService: DesktopBootstrapServicing {
    let bootstrap: DesktopBootstrap

    func fetchBootstrap() async throws -> DesktopBootstrap {
        bootstrap
    }
}

private struct StaticTodayDynamicViewService: TodayDynamicViewServicing {
    let view: TodayDynamicView?
    let error: Error?

    init(view: TodayDynamicView? = nil, error: Error? = nil) {
        self.view = view
        self.error = error
    }

    func fetchTodayDynamicView(trigger: TodayDynamicTrigger) async throws -> TodayDynamicView {
        if let error {
            throw error
        }
        return view ?? .empty
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

private extension TodayDynamicView {
    static let empty = TodayDynamicView(
        viewID: "today:empty",
        surface: "mobile.today",
        trigger: "open",
        generatedBy: "aheng_today_view_v1",
        contextHash: "",
        safetyBoundary: nil,
        sections: []
    )

    static let fixtureDailyArtifact = TodayDynamicView(
        viewID: "today:2026-06-29:abc",
        surface: "mobile.today",
        trigger: "open",
        generatedBy: "aheng_today_view_v1",
        contextHash: "abc",
        safetyBoundary: "健康管理行动建议,不替代医生诊断。",
        sections: [
            TodayDynamicSection(
                slot: "hero",
                priority: 100,
                title: nil,
                cards: [
                    AgentDynamicCardDescriptor(
                        type: "agent_atom",
                        render: AgentDynamicCardRenderDescriptor(
                            atom: "daily_artifact",
                            reason: "primary_today_action"
                        ),
                        data: .object([
                            "artifact_date": .string("2026-06-29"),
                            "top_action": .object([
                                "id": .string("walk-after-meal"),
                                "title": .string("阿衡动态生成的餐后步行")
                            ])
                        ])
                    )
                ]
            )
        ]
    )
}
