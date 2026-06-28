import Foundation
import XCTest
@testable import HealthAgentMacCore

final class DataConnectionsClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    func testDecodesConnectionsWithHealthAndPolicy() throws {
        let json = """
        {
          "connections": [
            {
              "id": 12,
              "provider": "apple_health",
              "provider_type": "wearable",
              "display_name": "Apple Health",
              "connection_status": "active",
              "token_status": "valid",
              "scopes": ["steps", "heart_rate"],
              "last_sync_at": "2026-06-28T08:10:00Z",
              "policy": {
                "degraded_behavior": "read_only",
                "retry_interval_minutes": 60,
                "rate_limit_per_hour": 120
              },
              "connection_health": {
                "status": "healthy",
                "severity": "ok",
                "message_code": "connection_healthy",
                "can_attempt_sync": true,
                "can_use_cached_data": true,
                "needs_reconnect": false,
                "user_action": "none",
                "connection_status": "active",
                "token_status": "valid",
                "degraded_behavior": "read_only",
                "last_success_at": "2026-06-28T08:10:00Z",
                "last_attempt_at": "2026-06-28T08:11:00Z",
                "sync_error": null
              }
            }
          ]
        }
        """

        let response = try decode(DataConnectionsResponse.self, json)

        XCTAssertEqual(response.connections.count, 1)
        let connection = response.connections[0]
        XCTAssertEqual(connection.id, 12)
        XCTAssertEqual(connection.displayName, "Apple Health")
        XCTAssertEqual(connection.scopes, ["steps", "heart_rate"])
        XCTAssertEqual(connection.policy?.degradedBehavior, "read_only")
        XCTAssertEqual(connection.connectionHealth?.status, "healthy")
        XCTAssertEqual(connection.connectionHealth?.userAction, "none")
        XCTAssertEqual(connection.connectionHealth?.canUseCachedData, true)
        XCTAssertEqual(connection.health.status, "healthy")
    }

    func testConnectionHealthFallbackUsesRawStatusWhenBackendOmitsHealth() throws {
        let json = """
        {
          "connections": [
            {
              "id": 13,
              "provider": "garmin",
              "provider_type": "wearable",
              "display_name": "Garmin",
              "connection_status": "revoked",
              "token_status": "none",
              "scopes": []
            }
          ]
        }
        """

        let response = try decode(DataConnectionsResponse.self, json)
        let health = response.connections[0].health

        XCTAssertEqual(health.status, "revoked")
        XCTAssertEqual(health.severity, "blocked")
        XCTAssertEqual(health.userAction, "reconnect")
        XCTAssertFalse(health.canAttemptSync)
        XCTAssertFalse(health.canUseCachedData)
        XCTAssertTrue(health.needsReconnect)
    }

    func testDisplayMappingPrioritizesConnectionHealth() {
        let degraded = DataConnectionHealth(
            status: "degraded",
            severity: "warning",
            messageCode: "connector_auth_failed_read_only",
            canAttemptSync: false,
            canUseCachedData: true,
            needsReconnect: true,
            userAction: "reconnect",
            connectionStatus: "active",
            tokenStatus: "auth_failed",
            degradedBehavior: "read_only",
            lastSuccessAt: nil,
            lastAttemptAt: nil,
            syncError: nil
        )
        let connection = DataConnection(
            id: 1,
            provider: "garmin",
            providerType: "wearable",
            displayName: "Garmin",
            connectionStatus: "active",
            tokenStatus: "auth_failed",
            scopes: ["activity", "sleep"],
            lastSyncAt: nil,
            sourceRef: nil,
            policy: nil,
            connectionHealth: degraded
        )

        let display = DataConnectionHealthDisplay.display(for: connection)

        XCTAssertEqual(display.statusLabel, "需重连")
        XCTAssertEqual(display.actionLabel, "重新授权")
        XCTAssertEqual(display.tint, "warning")
        XCTAssertEqual(display.cachedDataLabel, "缓存可只读使用")
    }

    func testClientFetchesMyDataConnectionsEndpoint() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/data-connections/me")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer token-123")
            let data = #"{"connections":[]}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let apiClient = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: StaticTokenProvider(token: "token-123"),
            session: URLSession(configuration: .ephemeralWithStub)
        )
        let client = DataConnectionsClient(apiClient: apiClient)

        let response = try await client.fetchMyConnections()

        XCTAssertTrue(response.connections.isEmpty)
    }
}
