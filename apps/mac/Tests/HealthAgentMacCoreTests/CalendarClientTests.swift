import Foundation
import XCTest
@testable import HealthAgentMacCore

final class CalendarClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testListSourcesDecodesSafeCalendarSources() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/calendar/sources")
            let data = """
            [
              {
                "id": 3,
                "provider": "ics",
                "name": "工作日历",
                "color": "#34C759",
                "writable": false,
                "sync_enabled": true,
                "last_sync_at": "2026-06-22T08:00:00+08:00",
                "last_error": null
              }
            ]
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = makeClient()

        let sources = try await client.listSources()

        XCTAssertEqual(sources.count, 1)
        XCTAssertEqual(sources[0].id, 3)
        XCTAssertEqual(sources[0].provider, "ics")
        XCTAssertTrue(sources[0].syncEnabled)
    }

    func testAddICSCalendarSourcePostsExpectedBody() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/calendar/sources")
            let body = try XCTUnwrap(request.bodyDataForTesting)
            let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(object["provider"] as? String, "ics")
            XCTAssertEqual(object["name"] as? String, "家庭")
            XCTAssertEqual(object["url"] as? String, "https://example.test/family.ics")
            XCTAssertNil(object["password"])
            let data = """
            {"id":4,"provider":"ics","name":"家庭","color":null,"writable":false,"sync_enabled":true,"last_sync_at":null,"last_error":null}
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = makeClient()

        let source = try await client.addSource(.init(provider: "ics", name: "家庭", url: "https://example.test/family.ics"))

        XCTAssertEqual(source.id, 4)
        XCTAssertEqual(source.name, "家庭")
    }

    func testUpdateSourceUsesPutAndSyncPostsEmptyBody() async throws {
        var requests: [URLRequest] = []
        URLProtocolStub.handler = { request in
            requests.append(request)
            if request.httpMethod == "PUT" {
                let body = try XCTUnwrap(request.bodyDataForTesting)
                let object = try XCTUnwrap(JSONSerialization.jsonObject(with: body) as? [String: Any])
                XCTAssertEqual(object["sync_enabled"] as? Bool, false)
                let data = """
                {"id":5,"provider":"caldav","name":"公司","color":"#0A84FF","writable":false,"sync_enabled":false,"last_sync_at":null,"last_error":null}
                """.data(using: .utf8)!
                return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
            }
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/calendar/sync")
            let data = #"{"sources":{"5":{"synced":12},"6":{"error":"unauthorized"}},"count":2}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let client = makeClient()

        let updated = try await client.updateSource(id: 5, patch: .init(syncEnabled: false))
        let sync = try await client.sync()

        XCTAssertEqual(updated.syncEnabled, false)
        XCTAssertEqual(sync.count, 2)
        XCTAssertEqual(sync.sources["5"]?.synced, 12)
        XCTAssertEqual(sync.sources["6"]?.error, "unauthorized")
        XCTAssertEqual(requests.map(\.httpMethod), ["PUT", "POST"])
    }

    private func makeClient() -> CalendarClient {
        CalendarClient(apiClient: APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        ))
    }
}
