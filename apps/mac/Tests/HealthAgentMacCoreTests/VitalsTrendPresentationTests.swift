import Foundation
import XCTest
@testable import HealthAgentMacCore

final class VitalsTrendPresentationTests: XCTestCase {
    private func record(
        _ date: String,
        hrv: Double? = nil,
        rhr: Int? = nil,
        avgHR: Int? = nil,
        stress: Int? = nil,
        battery: Int? = nil,
        batteryLow: Int? = nil,
        sleepScore: Int? = nil,
        sleepMin: Int? = nil,
        deep: Int? = nil,
        light: Int? = nil,
        rem: Int? = nil,
        awake: Int? = nil
    ) -> GarminDailyRecord {
        GarminDailyRecord(
            id: abs(date.hashValue),
            recordDate: date,
            hrv: hrv,
            restingHeartRate: rhr,
            avgHeartRate: avgHR,
            stressLevel: stress,
            bodyBatteryCurrent: battery,
            bodyBatteryLowest: batteryLow,
            sleepScore: sleepScore,
            totalSleepMinutes: sleepMin,
            deepSleepMinutes: deep,
            remSleepMinutes: rem,
            lightSleepMinutes: light,
            awakeMinutes: awake
        )
    }

    func testEmptyRecordsHaveNoData() {
        let p = VitalsTrendPresentation(records: [])
        XCTAssertFalse(p.hasData)
        XCTAssertNil(p.latestHRV)
        XCTAssertNil(p.sleepStages)
        XCTAssertTrue(p.hrvSeries.points.isEmpty)
        XCTAssertNil(p.hrvSeries.average)
    }

    func testLatestSnapshotPicksMostRecentDateRegardlessOfInputOrder() {
        // Out-of-order input; latest = 05-30.
        let p = VitalsTrendPresentation(records: [
            record("2026-05-28", hrv: 40, rhr: 55, sleepMin: 420),
            record("2026-05-30", hrv: 48, rhr: 52, avgHR: 62, stress: 30, battery: 80, batteryLow: 20, sleepScore: 88, sleepMin: 465),
            record("2026-05-29", hrv: 44, rhr: 54, sleepMin: 400)
        ])
        XCTAssertTrue(p.hasData)
        XCTAssertEqual(p.latestDate, "2026-05-30")
        XCTAssertEqual(p.latestHRV, 48)
        XCTAssertEqual(p.latestRestingHR, 52)
        XCTAssertEqual(p.latestAvgHR, 62)
        XCTAssertEqual(p.latestStress, 30)
        XCTAssertEqual(p.latestBodyBattery, 80)
        XCTAssertEqual(p.latestBodyBatteryLowest, 20)
        XCTAssertEqual(p.latestSleepScore, 88)
        XCTAssertEqual(p.latestSleepHours ?? 0, 7.75, accuracy: 0.001) // 465 min
    }

    func testSeriesAreChronologicalAndSkipMissingValues() {
        let p = VitalsTrendPresentation(records: [
            record("2026-05-30", hrv: 50),
            record("2026-05-28", hrv: 40),
            record("2026-05-29")               // no hrv → skipped
        ])
        XCTAssertEqual(p.hrvSeries.points, [40, 50])
        XCTAssertEqual(p.hrvSeries.average ?? 0, 45, accuracy: 0.001)
    }

    func testLastDaysScopingKeepsMostRecentWindow() {
        let records = (1...10).map { record(String(format: "2026-05-%02d", $0), hrv: Double($0)) }
        let p = VitalsTrendPresentation(records: records, lastDays: 3)
        // Most recent 3 days: hrv 8, 9, 10.
        XCTAssertEqual(p.hrvSeries.points, [8, 9, 10])
        XCTAssertEqual(p.latestHRV, 10)
    }

    func testSleepStagesPopulatedOnlyWhenPresent() {
        let withStages = VitalsTrendPresentation(records: [
            record("2026-05-30", sleepMin: 460, deep: 90, light: 250, rem: 100, awake: 20)
        ])
        XCTAssertNotNil(withStages.sleepStages)
        XCTAssertEqual(withStages.sleepStages?.totalMinutes, 460)
        XCTAssertTrue(withStages.sleepStages?.hasData ?? false)

        let noStages = VitalsTrendPresentation(records: [record("2026-05-30", sleepMin: 460)])
        XCTAssertNil(noStages.sleepStages)
    }

    func testSleepStageDaysAreChronologicalAndSkipDaysWithoutStages() {
        let p = VitalsTrendPresentation(records: [
            record("2026-05-30", deep: 90, light: 250, rem: 100, awake: 20),
            record("2026-05-28", deep: 80, light: 240, rem: 90, awake: 15),
            record("2026-05-29", sleepMin: 400)   // total sleep but no stage breakdown → skipped
        ])
        XCTAssertEqual(p.sleepStageDays.map(\.date), ["2026-05-28", "2026-05-30"])
        XCTAssertEqual(p.sleepStageDays.first?.deepMinutes, 80)
        XCTAssertEqual(p.sleepStageDays.last?.totalMinutes, 460)
    }

    func testVitalTrendDetailBuildsDatedPointsAndSummaryForKind() {
        let detail = VitalTrendDetail(kind: .restingHR, rangeDays: 30, records: [
            record("2026-05-30", rhr: 50),
            record("2026-05-28", rhr: 54),
            record("2026-05-29")               // no rhr → skipped
        ])
        XCTAssertEqual(detail.points.map(\.date), ["2026-05-28", "2026-05-30"])
        XCTAssertEqual(detail.points.map(\.value), [54, 50])
        XCTAssertEqual(detail.average ?? 0, 52, accuracy: 0.001)
        XCTAssertEqual(detail.minValue, 50)
        XCTAssertEqual(detail.maxValue, 54)
        XCTAssertEqual(detail.unit, "bpm")
        XCTAssertTrue(detail.pointSeriesText.contains("2026-05-28=54 bpm"))
    }

    func testVitalTrendDetailScopesToRequestedRange() {
        let records = (1...20).map { record(String(format: "2026-05-%02d", $0), hrv: Double($0)) }
        let detail = VitalTrendDetail(kind: .hrv, rangeDays: 5, records: records)
        XCTAssertEqual(detail.points.count, 5)
        XCTAssertEqual(detail.points.map(\.value), [16, 17, 18, 19, 20])
    }

    func testVitalTrendDetailSleepHoursConvertsMinutes() {
        let detail = VitalTrendDetail(kind: .sleepHours, rangeDays: 7, records: [
            record("2026-05-30", sleepMin: 450)
        ])
        XCTAssertEqual(detail.points.first?.value ?? 0, 7.5, accuracy: 0.001)
        XCTAssertEqual(detail.unit, "h")
    }

    func testVitalAgentContextAndPromptCarryMetricData() {
        let detail = VitalTrendDetail(kind: .hrv, rangeDays: 30, records: [
            record("2026-05-29", hrv: 44),
            record("2026-05-30", hrv: 48)
        ])
        let item = DesktopWorkspaceContextFactory.contextItem(forVital: detail, title: "心率变异性")
        XCTAssertEqual(item.sourceKind, "vital_trend")
        XCTAssertEqual(item.sourceID, "vital_trend:hrv:30d")
        XCTAssertEqual(item.payload["kind"], "hrv")
        XCTAssertEqual(item.payload["unit"], "ms")
        XCTAssertTrue(item.payload["points"]?.contains("2026-05-30=48 ms") ?? false)

        let prompt = DesktopWorkspaceContextFactory.prompt(forVital: detail, title: "心率变异性")
        XCTAssertTrue(prompt.contains("心率变异性"))
        XCTAssertTrue(prompt.contains("30 天"))
        XCTAssertTrue(prompt.contains("2026-05-29=44 ms"))
    }

    func testDecodesGarminDailyRecordFromBackendSnakeCaseJSON() throws {
        let json = """
        [{
          "id": 12, "record_date": "2026-05-30",
          "hrv": 47.5, "resting_heart_rate": 53, "avg_heart_rate": 64,
          "stress_level": 28, "body_battery_current": 76, "body_battery_lowest": 18,
          "sleep_score": 82, "total_sleep_duration": 455,
          "deep_sleep_duration": 88, "rem_sleep_duration": 95,
          "light_sleep_duration": 252, "awake_duration": 20, "steps": 9123
        }]
        """.data(using: .utf8)!
        let records = try JSONDecoder().decode([GarminDailyRecord].self, from: json)
        XCTAssertEqual(records.count, 1)
        let r = records[0]
        XCTAssertEqual(r.hrv, 47.5)
        XCTAssertEqual(r.restingHeartRate, 53)
        XCTAssertEqual(r.stressLevel, 28)
        XCTAssertEqual(r.bodyBatteryCurrent, 76)
        XCTAssertEqual(r.totalSleepMinutes, 455)
        XCTAssertEqual(r.deepSleepMinutes, 88)
        XCTAssertEqual(r.steps, 9123)
    }
}
