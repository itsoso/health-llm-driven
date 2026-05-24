import XCTest
@testable import HealthAgentMacCore

final class RecordHubPresentationTests: XCTestCase {
    func testRecordHubPresentationShowsTodaySevenDayAndRecentRecords() {
        let summary = RecentRecordsSummary(
            diet: DietRecordSummary(
                todayCount: 2,
                todayCalories: 880,
                last7Count: 16,
                last7Calories: 13682,
                last7AvgCalories: 1954.6
            ),
            water: WaterRecordSummary(
                todayCount: 3,
                todayTotalMl: 1200,
                last7Count: 21,
                last7TotalMl: 7300,
                last7AvgMl: 1042.9
            ),
            date: "2026-05-24",
            latestWeight: DesktopRecordMetric(
                id: 49,
                type: "weight",
                title: "体重",
                value: .double(70.2),
                unit: "kg",
                category: nil,
                recordDate: "2026-05-23"
            ),
            latestBloodPressure: DesktopRecordMetric(
                id: 3,
                type: "blood_pressure",
                title: "血压",
                value: .string("119/75"),
                unit: "mmHg",
                category: "正常",
                recordDate: "2026-05-20"
            ),
            recentRecords: [
                DesktopRecordMetric(id: 625, type: "diet", title: "晚餐", value: .double(650), unit: "kcal", category: nil, recordDate: "2026-05-23"),
                DesktopRecordMetric(id: 626, type: "water", title: "饮水", value: .int(500), unit: "ml", category: nil, recordDate: "2026-05-23")
            ],
            supplements: SupplementRecordSummary(
                activeCount: 4,
                todayCount: 1,
                last7Count: 7,
                last7AvgPerDay: 1.0,
                adherence7Pct: 25
            )
        )

        let presentation = DesktopRecordHubPresentation(summary: summary)

        XCTAssertEqual(presentation.date, "2026-05-24")
        XCTAssertEqual(presentation.todayMetrics.map(\.titleKey), ["Today Diet", "Today Water", "Today Supplements"])
        XCTAssertEqual(presentation.todayMetrics.map(\.value), ["880 kcal", "1200 ml", "1"])
        XCTAssertEqual(presentation.sevenDayMetrics.map(\.titleKey), ["Diet 7d", "Water 7d", "Supplements 7d", "Latest Vitals"])
        XCTAssertEqual(presentation.sevenDayMetrics.map(\.value), ["13682 kcal", "7300 ml", "7", "70.2 kg"])
        XCTAssertEqual(presentation.sevenDayMetrics[3].detail, "119/75 mmHg")
        XCTAssertEqual(presentation.recentRows.map(\.value), ["650 kcal", "500 ml"])
    }
}
