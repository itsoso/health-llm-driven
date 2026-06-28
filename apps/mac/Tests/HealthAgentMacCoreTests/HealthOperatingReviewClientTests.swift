import Foundation
import XCTest
@testable import HealthAgentMacCore

final class HealthOperatingReviewClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    func testDecodesPredictionNextStepAndConfidenceHistory() throws {
        let json = """
        {
          "window_days": 30,
          "start_date": "2026-05-30",
          "end_date": "2026-06-28",
          "execution": {
            "total_events": 10,
            "completed_events": 7,
            "completion_rate": 0.7,
            "by_status": {"completed": 7},
            "by_domain": {"sleep": 3}
          },
          "metrics": {},
          "completed_action_keys": ["sleep_routine"],
          "prediction_backtest": {
            "version": "prediction_backtest_v1",
            "status": "ready",
            "window_days": 30,
            "candidate_count": 1,
            "ready_candidate_count": 1,
            "results": [
              {
                "prediction_id": "pred-1",
                "action_key": "sleep_routine",
                "action_title": "睡前放松",
                "metric": "sleep_score",
                "observed_delta": 4,
                "evidence_count": 3,
                "verdict": "met",
                "confidence_before": "medium",
                "confidence_after": "medium",
                "confidence_change": {
                  "before": "medium",
                  "after": "medium",
                  "direction": "same"
                },
                "confidence_history": [
                  {"stage": "predicted", "confidence": "medium", "reason": "预测生成时的置信度"},
                  {"stage": "reviewed", "confidence": "medium", "reason": "复盘后的置信度"}
                ],
                "inconclusive_reason": null,
                "requires_clinician": false,
                "next_step": {
                  "action": "continue_observe",
                  "label": "继续当前策略并观察",
                  "reason": "预测方向被观察数据支持, 但只作为观察性复盘。",
                  "replan_hint": null,
                  "requires_clinician": false
                }
              }
            ],
            "summary": {
              "met": 1,
              "not_met": 0,
              "inconclusive": 0
            }
          }
        }
        """

        let review = try decode(HealthOperatingReview.self, json)
        let result = try XCTUnwrap(review.predictionBacktest?.results.first)

        XCTAssertEqual(review.windowDays, 30)
        XCTAssertEqual(result.nextStep?.action, "continue_observe")
        XCTAssertEqual(result.nextStep?.label, "继续当前策略并观察")
        XCTAssertEqual(result.confidenceChange?.direction, "same")
        XCTAssertEqual(result.confidenceHistory.count, 2)
        XCTAssertNil(result.inconclusiveReason)
        XCTAssertEqual(
            HealthOperatingReviewPresentation.nextStepSummary(for: result),
            "下一步: 继续当前策略并观察 · 置信度 medium → medium · 观察性,非因果"
        )
    }

    func testClientFetchesDailyPlanReviewEndpoint() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/daily-plan/review?window_days=30")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token-123")
            let data = #"{"window_days":30,"start_date":"2026-05-30","end_date":"2026-06-28","execution":{"total_events":2,"completed_events":1,"completion_rate":0.5,"by_status":{},"by_domain":{}},"metrics":{},"completed_action_keys":[]}"#
                .data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let apiClient = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        )
        let client = HealthOperatingReviewClient(apiClient: apiClient)

        let review = try await client.fetchReview(windowDays: 30)

        XCTAssertEqual(review.windowDays, 30)
        XCTAssertEqual(review.execution.completionRate, 0.5)
    }
}
