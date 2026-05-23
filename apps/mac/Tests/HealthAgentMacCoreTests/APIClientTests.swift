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
}

private final class StaticTokenProvider: AuthTokenProviding, @unchecked Sendable {
    var token: String?

    init(token: String?) {
        self.token = token
    }

    func getToken() async -> String? {
        token
    }

    func clearToken() async {
        token = nil
    }
}

private final class URLProtocolStub: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    static func reset() {
        handler = nil
    }

    override class func canInit(with request: URLRequest) -> Bool {
        true
    }

    override class func canonicalRequest(for request: URLRequest) -> URLRequest {
        request
    }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private extension URLSessionConfiguration {
    static var ephemeralWithStub: URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        return configuration
    }
}
