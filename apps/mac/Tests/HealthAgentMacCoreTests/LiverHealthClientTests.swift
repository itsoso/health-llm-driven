import XCTest
@testable import HealthAgentMacCore

final class LiverHealthClientTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    // MARK: - Full report decoding

    func testDecodesFullAvailableReport() throws {
        let json = """
        {
          "available": true,
          "reason": null,
          "alt_latest": 42.0,
          "ast_latest": 35.5,
          "ggt_latest": 88.0,
          "platelets_latest": 210.0,
          "tg_latest": 1.8,
          "ast_alt_ratio": 0.85,
          "alt_trend": {
            "n": 4,
            "first_value": 60.0,
            "last_value": 42.0,
            "first_date": "2025-01-01",
            "last_date": "2026-01-01",
            "pct_change": -30.0,
            "direction": "down",
            "verdict": "improving"
          },
          "ggt_trend": {
            "n": 3,
            "first_value": 70.0,
            "last_value": 88.0,
            "first_date": "2025-03-01",
            "last_date": "2026-01-01",
            "pct_change": 25.7,
            "direction": "up",
            "verdict": "worsening"
          },
          "fib4": 1.12,
          "fib4_band": "low",
          "fatty_liver_risk": "偏高",
          "summary_lines": ["ALT 一年内从 60 降到 42", "GGT 略有上升"],
          "advice": ["减少饮酒", "复查腹部超声"]
        }
        """
        let report = try decode(LiverHealthReport.self, json)

        XCTAssertTrue(report.available)
        XCTAssertNil(report.reason)
        XCTAssertEqual(report.altLatest, 42.0)
        XCTAssertEqual(report.astAltRatio, 0.85)
        XCTAssertEqual(report.altTrend?.normalizedVerdict, .improving)
        XCTAssertEqual(report.ggtTrend?.normalizedVerdict, .worsening)
        XCTAssertEqual(report.altTrend?.n, 4)
        XCTAssertEqual(report.ggtTrend?.pctChange, 25.7)
        XCTAssertTrue(report.hasFib4)
        XCTAssertEqual(report.fib4, 1.12)
        XCTAssertEqual(report.fib4Band, "low")
        XCTAssertTrue(report.fattyLiverRiskElevated)
        XCTAssertEqual(report.summaryLines.count, 2)
        XCTAssertEqual(report.advice.count, 2)
    }

    // MARK: - Unavailable / empty

    func testDecodesUnavailableReport() throws {
        let json = """
        { "available": false, "reason": "需要至少两次肝功能化验" }
        """
        let report = try decode(LiverHealthReport.self, json)
        XCTAssertFalse(report.available)
        XCTAssertEqual(report.reason, "需要至少两次肝功能化验")
        XCTAssertNil(report.altTrend)
        XCTAssertNil(report.fib4)
        XCTAssertTrue(report.summaryLines.isEmpty)
        XCTAssertTrue(report.advice.isEmpty)
    }

    func testEmptyPayloadDecodesToSafeDefaults() throws {
        // Missing fields must never throw — decode to a safe empty report.
        let report = try decode(LiverHealthReport.self, "{}")
        XCTAssertFalse(report.available)
        XCTAssertNil(report.reason)
        XCTAssertNil(report.astAltRatio)
        XCTAssertFalse(report.hasFib4)
        XCTAssertFalse(report.fattyLiverRiskElevated)
        XCTAssertTrue(report.summaryLines.isEmpty)
        XCTAssertTrue(report.advice.isEmpty)
    }

    // MARK: - FIB-4 missing platelets path

    func testFib4NullWhenPlateletsMissing() throws {
        let json = """
        {
          "available": true,
          "alt_latest": 50.0,
          "fib4": null,
          "fib4_band": null,
          "summary_lines": ["ALT 偏高"],
          "advice": []
        }
        """
        let report = try decode(LiverHealthReport.self, json)
        XCTAssertTrue(report.available)
        XCTAssertFalse(report.hasFib4)
        XCTAssertNil(report.fib4Band)
    }

    // MARK: - Verdict normalization

    func testVerdictNormalizationHandlesCaseAndWhitespace() throws {
        let json = """
        { "n": 2, "first_value": 1.0, "last_value": 1.0, "verdict": "  STABLE  " }
        """
        let trend = try decode(LiverTrend.self, json)
        XCTAssertEqual(trend.normalizedVerdict, .stable)
    }

    func testUnknownVerdictNormalizesToNil() throws {
        let json = """
        { "n": 2, "verdict": "mysterious" }
        """
        let trend = try decode(LiverTrend.self, json)
        XCTAssertNil(trend.normalizedVerdict)
        XCTAssertEqual(trend.n, 2)
    }

    func testMissingVerdictNormalizesToNil() throws {
        let trend = try decode(LiverTrend.self, "{}")
        XCTAssertNil(trend.normalizedVerdict)
        XCTAssertEqual(trend.n, 0)
        XCTAssertNil(trend.firstValue)
    }

    // MARK: - Fatty liver risk elevation

    func testFattyLiverRiskElevationDetection() throws {
        XCTAssertTrue(try decode(LiverHealthReport.self, #"{ "fatty_liver_risk": "偏高" }"#).fattyLiverRiskElevated)
        XCTAssertTrue(try decode(LiverHealthReport.self, #"{ "fatty_liver_risk": "High" }"#).fattyLiverRiskElevated)
        XCTAssertTrue(try decode(LiverHealthReport.self, #"{ "fatty_liver_risk": "elevated" }"#).fattyLiverRiskElevated)
        XCTAssertFalse(try decode(LiverHealthReport.self, #"{ "fatty_liver_risk": "低" }"#).fattyLiverRiskElevated)
        XCTAssertFalse(try decode(LiverHealthReport.self, "{}").fattyLiverRiskElevated)
    }
}
