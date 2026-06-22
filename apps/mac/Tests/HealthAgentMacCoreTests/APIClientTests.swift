import Foundation
import XCTest
@testable import HealthAgentMacCore

final class APIClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testAPIClientAddsBearerTokenAndDecodesBootstrap() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/desktop/bootstrap")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token-123")
            let data = """
            {
              "user": {"id": 3, "name": "itsoso", "email": "i@example.com"},
              "model_preference": {"llm_model_id": "claude-opus-4.7"},
              "daily_plan": {"plan_date": "2026-05-23", "actions": [{"action_key": "walk", "title": "晚饭后散步", "domain": "movement"}]},
              "trajectory": {"focus_domains": ["metabolic_health"]},
              "action_cards": [{"id": 8, "title": "复查 LDL", "status": "active", "priority": 5}],
              "recent_memory": [{"id": 9, "object_value": "晚上训练"}],
              "recent_records_summary": {"diet": {"today_count": 1, "today_calories": 520}, "water": {"today_total_ml": 500}},
              "active_jobs": [{"id": 10, "job_type": "gene_reanalysis", "status": "queued", "progress": 0}]
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let session = URLSession(configuration: .ephemeralWithStub)
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: session
        )

        let bootstrap: DesktopBootstrap = try await client.get("desktop/bootstrap")

        XCTAssertEqual(bootstrap.user.id, 3)
        XCTAssertEqual(bootstrap.modelPreference.llmModelID, "claude-opus-4.7")
        XCTAssertEqual(bootstrap.dailyPlan.actions.first?.title, "晚饭后散步")
        XCTAssertEqual(bootstrap.actionCards.first?.title, "复查 LDL")
        XCTAssertEqual(bootstrap.activeJobs.first?.jobType, "gene_reanalysis")
    }

    func testAPIClientClearsTokenOnUnauthorized() async throws {
        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!, Data())
        }
        let tokenProvider = StaticTokenProvider(token: "expired")
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: tokenProvider,
            session: URLSession(configuration: .ephemeralWithStub)
        )

        do {
            let _: DesktopBootstrap = try await client.get("desktop/bootstrap")
            XCTFail("Expected unauthorized error")
        } catch APIError.unauthorized {
            XCTAssertNil(tokenProvider.token)
        }
    }

    func testAPIClientSurfacesServerDetailOnHTTPError() async throws {
        URLProtocolStub.handler = { request in
            let data = #"{"detail":"无法识别体重记录"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 400, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        do {
            let _: DesktopBootstrap = try await client.get("desktop/bootstrap")
            XCTFail("Expected HTTP status error")
        } catch APIError.httpStatus(let status, let message) {
            XCTAssertEqual(status, 400)
            XCTAssertEqual(message, "无法识别体重记录")
        }
    }

    func testAPIClientPutEncodesJSONBody() async throws {
        struct Patch: Encodable {
            let syncEnabled: Bool

            enum CodingKeys: String, CodingKey {
                case syncEnabled = "sync_enabled"
            }
        }
        struct Response: Decodable, Equatable {
            let ok: Bool
        }

        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "PUT")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/calendar/sources/7")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            let body = try XCTUnwrap(request.bodyDataForTesting)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(object["sync_enabled"] as? Bool, false)
            let data = #"{"ok":true}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let response: Response = try await client.put("calendar/sources/7", body: Patch(syncEnabled: false))

        XCTAssertEqual(response, Response(ok: true))
    }

    func testServerErrorNeverLeaksRawHTMLBody() async throws {
        // A 502 from nginx returns an HTML page; the user must never see it.
        URLProtocolStub.handler = { request in
            let html = "<html><head><title>502 Bad Gateway</title></head><body>nginx</body></html>"
            return (HTTPURLResponse(url: request.url!, statusCode: 502, httpVersion: nil, headerFields: nil)!,
                    html.data(using: .utf8)!)
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "t"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        do {
            let _: DesktopBootstrap = try await client.get("desktop/bootstrap")
            XCTFail("Expected httpStatus error")
        } catch let error as APIError {
            let message = error.errorDescription ?? ""
            XCTAssertFalse(message.contains("<"), "Raw HTML leaked: \(message)")
            XCTAssertFalse(message.contains("nginx"), "Raw body leaked: \(message)")
            XCTAssertEqual(message, "服务暂时不可用，请稍后再试。")
        }
    }

    func testUnauthorizedPostsSessionExpiredNotification() async throws {
        URLProtocolStub.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!, Data())
        }
        let client = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "expired"),
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let expectation = expectation(forNotification: .authSessionExpired, object: nil)
        do {
            let _: DesktopBootstrap = try await client.get("desktop/bootstrap")
            XCTFail("Expected unauthorized error")
        } catch APIError.unauthorized {
            // expected
        }
        await fulfillment(of: [expectation], timeout: 1.0)
    }
}
