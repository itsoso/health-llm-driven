import Foundation
import XCTest
@testable import HealthAgentMacCore

final class AuthClientTests: XCTestCase {
    override func setUp() {
        super.setUp()
        URLProtocolStub.reset()
    }

    func testAuthClientPostsJSONLoginAndStoresToken() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/auth/login/json")
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting ?? Data()) as? [String: String]
            XCTAssertEqual(body?["username"], "itsoso")
            XCTAssertEqual(body?["password"], "secret")
            let data = """
            {
              "access_token": "jwt-token",
              "token_type": "bearer",
              "user": {"id": 3, "username": "itsoso", "email": "i@example.com", "name": "itsoso"}
            }
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let tokenStore = StaticTokenStore(token: nil)
        let api = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: tokenStore,
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let response = try await AuthClient(apiClient: api, tokenStore: tokenStore).login(username: "itsoso", password: "secret")

        XCTAssertEqual(response.accessToken, "jwt-token")
        XCTAssertEqual(response.user.id, 3)
        XCTAssertEqual(tokenStore.token, "jwt-token")
    }

    func testAuthClientValidatesExistingTokenWithCurrentUserEndpoint() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/auth/me")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer jwt-token")
            let data = """
            {"id": 3, "username": "itsoso", "email": "i@example.com", "name": "itsoso"}
            """.data(using: .utf8)!
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, data)
        }
        let tokenStore = StaticTokenStore(token: "jwt-token")
        let api = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: tokenStore,
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let isValid = await AuthClient(apiClient: api, tokenStore: tokenStore).hasValidSession()

        XCTAssertTrue(isValid)
        XCTAssertEqual(tokenStore.token, "jwt-token")
    }

    func testAuthClientClearsExpiredTokenWhenSessionValidationReturnsUnauthorized() async throws {
        URLProtocolStub.handler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/auth/me")
            return (HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!, Data())
        }
        let tokenStore = StaticTokenStore(token: "expired-token")
        let api = APIClient(
            baseURL: URL(string: "https://example.test/api/v1")!,
            tokenProvider: tokenStore,
            session: URLSession(configuration: .ephemeralWithStub)
        )

        let isValid = await AuthClient(apiClient: api, tokenStore: tokenStore).hasValidSession()

        XCTAssertFalse(isValid)
        XCTAssertNil(tokenStore.token)
    }
}
