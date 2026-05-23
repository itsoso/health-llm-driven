import XCTest
@testable import HealthAgentMacCore

final class DesktopDashboardPresentationTests: XCTestCase {
    func testDashboardPresentationUsesRecentAndLatestDataWhenTodayIsEmpty() {
        let bootstrap = DesktopBootstrap(
            user: DesktopUser(id: 3, name: "baokun", email: "itsoso@126.com"),
            modelPreference: ModelPreference(llmModelID: "commercial/Gemini-3.1-Pro-Preview"),
            dailyPlan: DailyOperatingPlan(planDate: "2026-05-23", actions: [
                DailyPlanAction(actionKey: "weight", title: "晨起记录体重和腰围", domain: "measurement"),
                DailyPlanAction(actionKey: "protein", title: "今天蛋白质目标 113g", domain: "nutrition")
            ]),
            trajectory: TrajectorySummary(focusDomains: ["血脂", "血糖", "睡眠"]),
            actionCards: [
                ActionCardSummary(id: 1, title: "血脂风险以 LDL-C/ApoB 轨迹为锚点", status: "active", priority: 80)
            ],
            recentMemory: [
                MemoryFactSummary(id: 1, objectValue: "4"),
                MemoryFactSummary(id: 4, objectValue: "医生建议短期按说明书需要时服用，不建议连续多天高频或大剂量使用。"),
                MemoryFactSummary(id: 9, objectValue: "注意事项：有肝病时慎用对乙酰氨基酚。")
            ],
            recentRecordsSummary: RecentRecordsSummary(
                diet: DietRecordSummary(
                    todayCount: 0,
                    todayCalories: 0,
                    last7Count: 16,
                    last7Calories: 3450,
                    last7AvgCalories: 492.9,
                    last30Count: 113,
                    last30Calories: 47661,
                    last30AvgCalories: 1588.7,
                    daily7: [
                        DietDailyPoint(date: "2026-05-17", count: 2, calories: 600),
                        DietDailyPoint(date: "2026-05-18", count: 2, calories: 450),
                        DietDailyPoint(date: "2026-05-19", count: 3, calories: 700),
                        DietDailyPoint(date: "2026-05-20", count: 3, calories: 520),
                        DietDailyPoint(date: "2026-05-21", count: 2, calories: 530),
                        DietDailyPoint(date: "2026-05-22", count: 4, calories: 650),
                        DietDailyPoint(date: "2026-05-23", count: 0, calories: 0)
                    ]
                ),
                water: WaterRecordSummary(
                    todayCount: 0,
                    todayTotalMl: 0,
                    last7Count: 18,
                    last7TotalMl: 7900,
                    last7AvgMl: 1128.6,
                    last30Count: 137,
                    last30TotalMl: 35650,
                    last30AvgMl: 1188.3,
                    daily7: [
                        WaterDailyPoint(date: "2026-05-17", count: 2, totalMl: 900),
                        WaterDailyPoint(date: "2026-05-18", count: 2, totalMl: 1200),
                        WaterDailyPoint(date: "2026-05-19", count: 3, totalMl: 1300),
                        WaterDailyPoint(date: "2026-05-20", count: 3, totalMl: 1100),
                        WaterDailyPoint(date: "2026-05-21", count: 2, totalMl: 1400),
                        WaterDailyPoint(date: "2026-05-22", count: 6, totalMl: 2000),
                        WaterDailyPoint(date: "2026-05-23", count: 0, totalMl: 0)
                    ]
                ),
                date: "2026-05-23",
                rangeDays: 7,
                availableRanges: [7, 30],
                latestWeight: DesktopRecordMetric(
                    id: 49,
                    type: "weight",
                    title: "体重",
                    value: .double(70.5),
                    unit: "kg",
                    category: nil,
                    recordDate: "2026-05-16"
                ),
                latestBloodPressure: DesktopRecordMetric(
                    id: 3,
                    type: "blood_pressure",
                    title: "血压",
                    value: .string("119/75"),
                    unit: "mmHg",
                    category: "正常",
                    recordDate: "2026-04-05"
                ),
                latestGarmin: GarminMetricSummary(
                    id: 1558,
                    type: "garmin",
                    title: "Garmin",
                    recordDate: "2026-05-23",
                    steps: 971,
                    sleepScore: 89,
                    spo2Avg: 93.0,
                    restingHeartRate: 48,
                    hrv: 62.0,
                    trainingReadinessScore: 94
                ),
                recentRecords: [
                    DesktopRecordMetric(id: 625, type: "diet", title: "晚餐", value: .double(650), unit: "kcal", category: nil, recordDate: "2026-05-22"),
                    DesktopRecordMetric(id: 626, type: "water", title: "饮水", value: .int(500), unit: "ml", category: nil, recordDate: "2026-05-22")
                ],
                supplements: SupplementRecordSummary(
                    activeCount: 4,
                    todayCount: 0,
                    last7Count: 6,
                    last7AvgPerDay: 0.9,
                    last30Count: 22,
                    last30AvgPerDay: 0.7,
                    adherence7Pct: 21.4,
                    adherence30Pct: 18.3,
                    daily7: [
                        SupplementDailyPoint(date: "2026-05-17", count: 1),
                        SupplementDailyPoint(date: "2026-05-18", count: 1),
                        SupplementDailyPoint(date: "2026-05-19", count: 1),
                        SupplementDailyPoint(date: "2026-05-20", count: 1),
                        SupplementDailyPoint(date: "2026-05-21", count: 1),
                        SupplementDailyPoint(date: "2026-05-22", count: 1),
                        SupplementDailyPoint(date: "2026-05-23", count: 0)
                    ],
                    topItems: [SupplementTopItem(name: "鱼油", count: 6)]
                )
            ),
            activeJobs: []
        )

        let presentation = DesktopDashboardPresentation(bootstrap: bootstrap)

        XCTAssertEqual(presentation.heroTitle, "baokun")
        XCTAssertEqual(presentation.heroMetrics.map(\.value), ["971", "89", "93%", "70.5 kg"])
        XCTAssertEqual(presentation.primaryMetrics.map(\.value), ["3,450 kcal", "7,900 ml", "6", "119/75 mmHg"])
        XCTAssertEqual(presentation.thirtyDayMetrics.map(\.value), ["47,661 kcal", "35,650 ml", "22", "119/75 mmHg"])
        XCTAssertEqual(presentation.sevenDayTrends.map(\.points.count), [7, 7, 7])
        XCTAssertEqual(presentation.wearableMetrics.map(\.value), ["971", "89", "93%", "48"])
        XCTAssertEqual(presentation.focusChips, ["血脂", "血糖", "睡眠"])
        XCTAssertEqual(presentation.recentRecordRows.map(\.value), ["650 kcal", "500 ml"])
        XCTAssertEqual(presentation.memoryRows.count, 2)
        XCTAssertFalse(presentation.memoryRows.map(\.title).contains("4"))
        XCTAssertEqual(presentation.actionRows.map(\.title), ["晨起记录体重和腰围", "今天蛋白质目标 113g"])
    }
}
