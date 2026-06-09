import XCTest
@testable import HealthAgentMacCore

final class DeviceSourcesClientTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    // MARK: - /sources/summary decoding

    func testDecodesMultipleSourcesWithFullMetrics() throws {
        let json = """
        {
          "window_days": 30,
          "sources": [
            {
              "data_source": "apple-watch",
              "days_covered": 22,
              "latest_date": "2026-06-09",
              "metrics": {
                "steps": 8800,
                "resting_heart_rate": 54,
                "hrv": 61.0,
                "total_sleep_duration": 430,
                "sleep_score": 82,
                "spo2_avg": 97.0,
                "spo2_min": 93.0,
                "avg_heart_rate": 72,
                "active_calories": 540,
                "distance_meters": 6200.0
              }
            },
            {
              "data_source": "ringconn",
              "days_covered": 14,
              "latest_date": "2026-06-08",
              "metrics": {
                "steps": 7200,
                "resting_heart_rate": 56,
                "hrv": 58.5,
                "total_sleep_duration": 410
              }
            }
          ]
        }
        """
        let response = try decode(DeviceSourcesResponse.self, json)
        XCTAssertEqual(response.windowDays, 30)
        XCTAssertEqual(response.sources.count, 2)

        let apple = response.sources[0]
        XCTAssertEqual(apple.dataSource, "apple-watch")
        XCTAssertEqual(apple.daysCovered, 22)
        XCTAssertEqual(apple.latestDate, "2026-06-09")
        XCTAssertEqual(apple.metrics.steps, 8800)
        XCTAssertEqual(apple.metrics.restingHeartRate, 54)
        XCTAssertEqual(apple.metrics.hrv, 61.0)
        XCTAssertEqual(apple.metrics.totalSleepDuration, 430)
        XCTAssertEqual(apple.metrics.spo2Avg, 97.0)
        XCTAssertEqual(apple.metrics.activeCalories, 540)
        XCTAssertEqual(apple.metrics.distanceMeters, 6200.0)
        // id mirrors data_source for SwiftUI ForEach.
        XCTAssertEqual(apple.id, "apple-watch")

        let ring = response.sources[1]
        XCTAssertEqual(ring.dataSource, "ringconn")
        XCTAssertEqual(ring.metrics.steps, 7200)
        // Absent metrics stay nil — never fabricated.
        XCTAssertNil(ring.metrics.spo2Avg)
        XCTAssertNil(ring.metrics.activeCalories)
        XCTAssertNil(ring.metrics.distanceMeters)
    }

    func testDecodesNullAndAbsentMetricsGracefully() throws {
        let json = """
        {
          "window_days": 7,
          "sources": [
            {
              "data_source": "garmin",
              "days_covered": 3,
              "latest_date": null,
              "metrics": {
                "steps": null,
                "resting_heart_rate": 50,
                "hrv": null
              }
            }
          ]
        }
        """
        let response = try decode(DeviceSourcesResponse.self, json)
        let garmin = response.sources[0]
        XCTAssertNil(garmin.latestDate)
        XCTAssertNil(garmin.metrics.steps)
        XCTAssertEqual(garmin.metrics.restingHeartRate, 50)
        XCTAssertNil(garmin.metrics.hrv)
    }

    func testDecodesSourceWithMissingMetricsBlock() throws {
        // metrics entirely absent must not blow up the whole decode.
        let json = """
        { "window_days": 30, "sources": [ { "data_source": "unknown", "days_covered": 1 } ] }
        """
        let response = try decode(DeviceSourcesResponse.self, json)
        XCTAssertEqual(response.sources.count, 1)
        XCTAssertNil(response.sources[0].latestDate)
        XCTAssertNil(response.sources[0].metrics.steps)
    }

    func testDecodesEmptySourcesList() throws {
        let response = try decode(DeviceSourcesResponse.self, #"{"window_days":30,"sources":[]}"#)
        XCTAssertTrue(response.sources.isEmpty)
        XCTAssertEqual(response.windowDays, 30)
    }

    // MARK: - /compare decoding

    func testDecodesComparisonResponse() throws {
        let json = """
        {
          "window_days": 7,
          "sources": ["apple-watch", "ringconn"],
          "comparisons": [
            {
              "metric": "resting_heart_rate",
              "label": "静息心率",
              "unit": "bpm",
              "by_source": {"apple-watch": 54.0, "ringconn": 56.0},
              "diff": 2.0,
              "agreement": "high"
            }
          ],
          "note": ""
        }
        """
        let response = try decode(DeviceComparisonResponse.self, json)
        XCTAssertEqual(response.windowDays, 7)
        XCTAssertEqual(response.sources, ["apple-watch", "ringconn"])
        XCTAssertEqual(response.comparisons.count, 1)

        let row = response.comparisons[0]
        XCTAssertEqual(row.metric, "resting_heart_rate")
        XCTAssertEqual(row.label, "静息心率")
        XCTAssertEqual(row.unit, "bpm")
        XCTAssertEqual(row.bySource["apple-watch"], 54.0)
        XCTAssertEqual(row.bySource["ringconn"], 56.0)
        XCTAssertEqual(row.diff, 2.0)
        XCTAssertEqual(row.agreement, "high")
        XCTAssertEqual(row.id, "resting_heart_rate")
    }

    func testComparisonLabelFallsBackToMetricWhenMissing() throws {
        let json = """
        { "comparisons": [ { "metric": "hrv", "by_source": {} } ] }
        """
        let response = try decode(DeviceComparisonResponse.self, json)
        XCTAssertEqual(response.comparisons[0].label, "hrv")
        XCTAssertNil(response.comparisons[0].unit)
        XCTAssertTrue(response.comparisons[0].bySource.isEmpty)
    }

    // MARK: - Display name mapping

    func testDisplayNameMapping() {
        XCTAssertEqual(DeviceSourceDisplay.name(for: "apple-watch"), "Apple Watch")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "ringconn"), "RingConn Gen3")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "garmin"), "Garmin")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "oura"), "Oura Ring")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "withings-app"), "Withings")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "unknown"), "未知来源")
        // Unrecognized tags pass through verbatim — never guess a model.
        XCTAssertEqual(DeviceSourceDisplay.name(for: "fitbit"), "fitbit")
    }

    func testDisplayNameIsCaseInsensitive() {
        XCTAssertEqual(DeviceSourceDisplay.name(for: "Apple-Watch"), "Apple Watch")
        XCTAssertEqual(DeviceSourceDisplay.name(for: "GARMIN"), "Garmin")
    }

    func testSystemImageMapping() {
        XCTAssertEqual(DeviceSourceDisplay.systemImage(for: "apple-watch"), "applewatch")
        XCTAssertEqual(DeviceSourceDisplay.systemImage(for: "garmin"), "figure.run")
        XCTAssertEqual(DeviceSourceDisplay.systemImage(for: "ringconn"), "circle.circle")
        XCTAssertEqual(DeviceSourceDisplay.systemImage(for: "anything-else"), "dot.radiowaves.left.and.right")
    }

    // MARK: - min → hour formatting

    func testMinutesToHoursFormatting() {
        XCTAssertEqual(DurationFormat.minutesToHours(430), "7h 10m")
        XCTAssertEqual(DurationFormat.minutesToHours(420), "7h")
        XCTAssertEqual(DurationFormat.minutesToHours(45), "45m")
        XCTAssertEqual(DurationFormat.minutesToHours(60), "1h")
    }

    func testMinutesToHoursReturnsNilForMissingOrZero() {
        XCTAssertNil(DurationFormat.minutesToHours(nil))
        XCTAssertNil(DurationFormat.minutesToHours(0))
        XCTAssertNil(DurationFormat.minutesToHours(-10))
    }
}
