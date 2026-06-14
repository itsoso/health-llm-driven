import XCTest
@testable import HealthAgentMacCore

final class OutcomeProofClientTests: XCTestCase {
    func testBuildsOutcomeProofSummaryFromVerifiedProgress() {
        let dashboard = ProgressDashboard(
            stats: ProgressStats(
                totalSurfaced: 8,
                graded: 4,
                improved: 2,
                improvementRate: 0.5
            ),
            closedCards: [
                ProgressCard(
                    id: 42,
                    title: "提高早餐蛋白",
                    outcome: "improved",
                    metricKey: "weight_kg",
                    baselineValue: "72.4",
                    actualValue: "70.9"
                )
            ],
            verifyingCards: [
                ProgressCard(id: 43, title: "步行 20 分钟")
            ]
        )

        let summary = OutcomeProofSummaryBuilder.build(dashboard)

        XCTAssertEqual(summary.title, "个人证据：2 项已改善")
        XCTAssertEqual(summary.subtitle, "已验证 4 项，2/4 对你有效。")
        XCTAssertEqual(summary.items.map(\.label), ["已验证", "已改善", "验证中", "改善率"])
        XCTAssertEqual(summary.items.map(\.value), ["4", "2", "1", "50%"])
        XCTAssertEqual(summary.highlight?.detail, "weight_kg 72.4 → 70.9")
    }

    func testBuildsVerifyingOutcomeProofSummaryBeforeResults() {
        let dashboard = ProgressDashboard(
            stats: ProgressStats(totalSurfaced: 3, graded: 0, improved: 0, improvementRate: nil),
            closedCards: [],
            verifyingCards: [
                ProgressCard(id: 43, title: "步行 20 分钟")
            ]
        )

        let summary = OutcomeProofSummaryBuilder.build(dashboard)

        XCTAssertEqual(summary.title, "个人证据验证中")
        XCTAssertEqual(summary.subtitle, "1 个干预已完成，等待指标变化。")
        XCTAssertNil(summary.highlight)
    }
}
