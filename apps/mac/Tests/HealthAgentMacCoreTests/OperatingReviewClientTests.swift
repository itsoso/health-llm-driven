import XCTest
@testable import HealthAgentMacCore

final class OperatingReviewClientTests: XCTestCase {
    func testBuildsOperatingReviewSummaryFromCompletedActionsAndMetricChange() {
        let review = HealthOperatingReview(
            windowDays: 7,
            startDate: "2026-06-08",
            endDate: "2026-06-14",
            execution: ExecutionSummary(
                totalEvents: 5,
                completedEvents: 4,
                completionRate: 0.8,
                byStatus: ["done": 4, "skipped": 1],
                byDomain: ["nutrition": 3, "movement": 2]
            ),
            metrics: [
                "weight": MetricChange(
                    status: "present",
                    count: 4,
                    first: 72.4,
                    firstDate: "2026-06-08",
                    current: 71.2,
                    currentDate: "2026-06-14",
                    delta: -1.2
                ),
                "sleep_score": MetricChange(
                    status: "present",
                    count: 5,
                    first: 70,
                    firstDate: "2026-06-08",
                    current: 74,
                    currentDate: "2026-06-14",
                    delta: 4
                )
            ],
            completedActionKeys: ["nutrition.protein", "walk.20", "sleep.bedtime", "measure.weight"]
        )

        let summary = OperatingReviewSummaryBuilder.build(review)

        XCTAssertEqual(summary.title, "执行复盘：80% 完成")
        XCTAssertEqual(summary.subtitle, "过去 7 天完成 4/5 个行动。")
        XCTAssertEqual(summary.items.map(\.label), ["完成率", "已完成", "总行动", "可学习"])
        XCTAssertEqual(summary.items.map(\.value), ["80%", "4", "5", "4"])
        XCTAssertEqual(summary.highlight?.value, "体重 -1.2 kg")
        XCTAssertEqual(summary.highlight?.detail, "时间关联，不等于因果。")
    }
}
