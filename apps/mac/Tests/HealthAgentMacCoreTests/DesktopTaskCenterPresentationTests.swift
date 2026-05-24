import XCTest
@testable import HealthAgentMacCore

final class DesktopTaskCenterPresentationTests: XCTestCase {
    func testPresentationUsesActionCardsWhenDesktopJobsAreEmpty() {
        let actionCards = [
            ActionCardSummary(id: 24, title: "4–6 周复查血常规", status: "active", priority: 80, metricKey: "cbc"),
            ActionCardSummary(id: 23, title: "12 周补剂试验：5-MTHF", status: "active", priority: 30, metricKey: "hcy")
        ]

        let presentation = DesktopTaskCenterPresentation(jobs: [], actionCards: actionCards)

        XCTAssertFalse(presentation.isEmpty)
        XCTAssertEqual(presentation.totalCount, 2)
        XCTAssertEqual(presentation.runningJobCount, 0)
        XCTAssertEqual(presentation.failedJobCount, 0)
        XCTAssertEqual(presentation.actionCards.map(\.title), ["4–6 周复查血常规", "12 周补剂试验：5-MTHF"])
    }

    func testPresentationCombinesDesktopJobsAndActionCards() {
        let jobs = [
            DesktopJobSummary(
                id: 91,
                jobType: "medical_import",
                status: "running",
                progress: 40,
                sourceKind: "apple_health_export",
                sourceName: "export.zip"
            ),
            DesktopJobSummary(
                id: 92,
                jobType: "genomic_reanalysis",
                status: "failed",
                progress: 20,
                sourceKind: "wegene",
                sourceName: "genotype.txt"
            )
        ]
        let actionCards = [
            ActionCardSummary(id: 24, title: "4–6 周复查血常规", status: "active", priority: 80),
            ActionCardSummary(id: 23, title: "12 周补剂试验：5-MTHF", status: "active", priority: 30)
        ]

        let presentation = DesktopTaskCenterPresentation(jobs: jobs, actionCards: actionCards)

        XCTAssertEqual(presentation.totalCount, 4)
        XCTAssertEqual(presentation.runningJobCount, 1)
        XCTAssertEqual(presentation.failedJobCount, 1)
        XCTAssertEqual(presentation.actionCards.map(\.priority), [80, 30])
    }
}
