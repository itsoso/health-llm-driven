import XCTest
@testable import HealthAgentMacCore

final class HealthExtrasClientTests: XCTestCase {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    // MARK: - ① Deprescribing review

    func testDecodesFullDeprescribingReview() throws {
        let json = """
        {
          "active_count": 6,
          "is_polypharmacy": true,
          "flags": [
            {"code": "polypharmacy", "detail": "当前在用 6 种药", "suggestion": "请医生梳理。"},
            {"code": "duplicate_class", "detail": "他汀同类 2 种", "suggestion": "确认是否保留。"}
          ],
          "disclaimer": "以上为减药候选提示,非建议停药。"
        }
        """
        let review = try decode(DeprescribingReview.self, json)
        XCTAssertEqual(review.activeCount, 6)
        XCTAssertTrue(review.isPolypharmacy)
        XCTAssertEqual(review.flags.count, 2)
        XCTAssertEqual(review.flags.first?.code, "polypharmacy")
        XCTAssertEqual(review.flags[1].detail, "他汀同类 2 种")
        XCTAssertTrue(review.disclaimer.contains("非建议停药"))
        // 稳定 id 用 code+detail。
        XCTAssertEqual(review.flags.first?.id, "polypharmacy|当前在用 6 种药")
    }

    func testEmptyDeprescribingPayloadDecodesToSafeDefaults() throws {
        let review = try decode(DeprescribingReview.self, "{}")
        XCTAssertEqual(review.activeCount, 0)
        XCTAssertFalse(review.isPolypharmacy)
        XCTAssertTrue(review.flags.isEmpty)
        XCTAssertEqual(review.disclaimer, "")
    }

    // MARK: - ② Social connection

    func testDecodesConnectionStatusWithCheckin() throws {
        let json = """
        {
          "has_checkin": true,
          "due": false,
          "days_since": 12,
          "last_date": "2026-06-01",
          "ucla_score": 5,
          "has_confidant": true,
          "in_stable_group": false,
          "interpretation": "连接质量中等。"
        }
        """
        let status = try decode(ConnectionStatus.self, json)
        XCTAssertTrue(status.hasCheckin)
        XCTAssertFalse(status.due)
        XCTAssertEqual(status.daysSince, 12)
        XCTAssertEqual(status.lastDate, "2026-06-01")
        XCTAssertEqual(status.uclaScore, 5)
        XCTAssertEqual(status.hasConfidant, true)
        XCTAssertEqual(status.inStableGroup, false)
        XCTAssertEqual(status.interpretation, "连接质量中等。")
    }

    func testDecodesConnectionStatusNoCheckin() throws {
        let json = """
        { "has_checkin": false, "due": true, "days_since": null,
          "interpretation": "还没做过社会连接自评。" }
        """
        let status = try decode(ConnectionStatus.self, json)
        XCTAssertFalse(status.hasCheckin)
        XCTAssertTrue(status.due)
        XCTAssertNil(status.daysSince)
        XCTAssertNil(status.uclaScore)
        XCTAssertNil(status.hasConfidant)
        XCTAssertEqual(status.interpretation, "还没做过社会连接自评。")
    }

    func testConnectionCheckinRequestEncodesSnakeCase() throws {
        let body = ConnectionCheckinRequest(uclaScore: 7, hasConfidant: false, inStableGroup: true, notes: "x")
        let data = try JSONEncoder().encode(body)
        let object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        XCTAssertEqual(object["ucla_score"] as? Int, 7)
        XCTAssertEqual(object["has_confidant"] as? Bool, false)
        XCTAssertEqual(object["in_stable_group"] as? Bool, true)
        XCTAssertEqual(object["notes"] as? String, "x")
    }

    func testDecodesConnectionCheckinResponseWithNestedStatus() throws {
        let json = """
        {
          "id": 42,
          "checkin_date": "2026-06-13",
          "status": { "has_checkin": true, "due": false, "ucla_score": 4,
                      "interpretation": "不错。" }
        }
        """
        let response = try decode(ConnectionCheckinResponse.self, json)
        XCTAssertEqual(response.id, 42)
        XCTAssertEqual(response.checkinDate, "2026-06-13")
        XCTAssertEqual(response.status?.uclaScore, 4)
        XCTAssertTrue(response.status?.hasCheckin ?? false)
    }

    // MARK: - ③ Causal links

    func testDecodesCausalLinks() throws {
        let json = """
        {
          "intervention_effects": [
            {
              "medication": "二甲双胍",
              "metric_label": "空腹血糖",
              "before_mean": 7.2,
              "after_mean": 6.1,
              "delta": -1.1,
              "pct": -15.3,
              "n_before": 8,
              "n_after": 10
            }
          ],
          "note": "观察到的关联,非严格因果。"
        }
        """
        let report = try decode(CausalLinksReport.self, json)
        XCTAssertEqual(report.interventionEffects.count, 1)
        let effect = try XCTUnwrap(report.interventionEffects.first)
        XCTAssertEqual(effect.medication, "二甲双胍")
        XCTAssertEqual(effect.metricLabel, "空腹血糖")
        XCTAssertEqual(effect.beforeMean, 7.2)
        XCTAssertEqual(effect.afterMean, 6.1)
        XCTAssertEqual(effect.delta, -1.1)
        XCTAssertEqual(effect.pct, -15.3)
        XCTAssertEqual(effect.nBefore, 8)
        XCTAssertEqual(effect.nAfter, 10)
        XCTAssertTrue(effect.isDecrease)
        XCTAssertEqual(report.note, "观察到的关联,非严格因果。")
    }

    func testCausalLinksNullPctAndEmptyDecode() throws {
        let json = """
        {
          "intervention_effects": [
            {"medication": "X", "metric_label": "Y", "before_mean": 1.0,
             "after_mean": 2.0, "delta": 1.0, "pct": null, "n_before": 3, "n_after": 4}
          ]
        }
        """
        let report = try decode(CausalLinksReport.self, json)
        let effect = try XCTUnwrap(report.interventionEffects.first)
        XCTAssertNil(effect.pct)
        XCTAssertFalse(effect.isDecrease)
        XCTAssertEqual(report.note, "")
        // 完全空 payload 安全降级。
        let empty = try decode(CausalLinksReport.self, "{}")
        XCTAssertTrue(empty.interventionEffects.isEmpty)
    }

    // MARK: - ④ Data integrity

    func testDecodesHealthyIntegrityReport() throws {
        let json = """
        { "healthy": true, "issue_count": 0, "issues": [] }
        """
        let report = try decode(IntegrityReport.self, json)
        XCTAssertTrue(report.healthy)
        XCTAssertEqual(report.issueCount, 0)
        XCTAssertTrue(report.issues.isEmpty)
    }

    func testDecodesIntegrityReportWithIssues() throws {
        let json = """
        {
          "healthy": false,
          "issue_count": 2,
          "issues": [
            {"code": "hrv_unit", "severity": "error", "detail": "HRV 量纲错",
             "count": 3, "fix_hint": "按 ms 存"},
            {"code": "spo2_decimal", "severity": "warning", "detail": "SpO2 小数存",
             "count": 1, "fix_hint": "按百分数"}
          ]
        }
        """
        let report = try decode(IntegrityReport.self, json)
        XCTAssertFalse(report.healthy)
        XCTAssertEqual(report.issueCount, 2)
        XCTAssertEqual(report.issues.count, 2)
        XCTAssertEqual(report.issues.first?.normalizedSeverity, .error)
        XCTAssertEqual(report.issues.first?.count, 3)
        XCTAssertEqual(report.issues[1].normalizedSeverity, .warning)
    }

    func testIntegritySeverityNormalizationFallsBackToInfo() throws {
        let json = #"{ "code": "x", "severity": "  WARNING  ", "detail": "d" }"#
        XCTAssertEqual(try decode(IntegrityIssue.self, json).normalizedSeverity, .warning)
        let unknown = #"{ "code": "x", "severity": "weird", "detail": "d" }"#
        XCTAssertEqual(try decode(IntegrityIssue.self, unknown).normalizedSeverity, .info)
        // 缺 count 默认 1。
        XCTAssertEqual(try decode(IntegrityIssue.self, "{}").count, 1)
    }

    // MARK: - Health guardrail summary

    func testBuildsHealthGuardrailSummaryFromMaintenanceSignals() {
        let summary = HealthGuardrailSummaryBuilder.build(
            integrity: IntegrityReport(
                healthy: false,
                issueCount: 2,
                issues: [
                    IntegrityIssue(code: "hrv_unit", severity: "error", detail: "HRV 量纲错", count: 3, fixHint: "按 ms 存"),
                    IntegrityIssue(code: "spo2_decimal", severity: "warning", detail: "SpO2 小数错", count: 1, fixHint: "按百分数存")
                ]
            ),
            deprescribing: DeprescribingReview(
                activeCount: 6,
                isPolypharmacy: true,
                flags: [DeprescribingFlag(code: "polypharmacy", detail: "当前在用 6 种药", suggestion: "请医生梳理")],
                disclaimer: "非建议停药"
            ),
            connection: ConnectionStatus(hasCheckin: true, due: true, daysSince: 45, interpretation: "需要复盘"),
            causalLinks: CausalLinksReport(
                interventionEffects: [
                    InterventionEffect(medication: "阿托伐他汀", metricLabel: "LDL-C", beforeMean: 3.4, afterMean: 2.6, delta: -0.8, pct: -23.5, nBefore: 4, nAfter: 5)
                ],
                note: "描述性关联"
            )
        )

        XCTAssertEqual(summary.attentionCount, 4)
        XCTAssertEqual(summary.title, "健康守门 4 项待处理")
        XCTAssertEqual(summary.items.map(\.label), ["数据自检", "用药梳理", "社会连接", "指标关联"])
        XCTAssertEqual(summary.items.map(\.value), ["2 个问题", "1 条候选", "本周应自评", "1 条可复盘"])
        XCTAssertEqual(summary.items.filter(\.attention).count, 3)
    }

    func testBuildsCalmHealthGuardrailSummaryWhenOnlyInsightExists() {
        let summary = HealthGuardrailSummaryBuilder.build(
            integrity: IntegrityReport(healthy: true, issueCount: 0, issues: []),
            deprescribing: DeprescribingReview(activeCount: 2, isPolypharmacy: false, flags: [], disclaimer: ""),
            connection: ConnectionStatus(hasCheckin: true, due: false, daysSince: 12, interpretation: "连接稳定"),
            causalLinks: CausalLinksReport(
                interventionEffects: [
                    InterventionEffect(medication: "二甲双胍", metricLabel: "空腹血糖"),
                    InterventionEffect(medication: "鱼油", metricLabel: "TG")
                ],
                note: "描述性关联"
            )
        )

        XCTAssertEqual(summary.attentionCount, 0)
        XCTAssertEqual(summary.title, "健康守门正常 · 2 条用药关联")
        XCTAssertEqual(summary.subtitle, "数据可信，已有用药-指标关联可复盘。")
    }
}
