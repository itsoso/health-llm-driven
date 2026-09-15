import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ShoppingClientTests: XCTestCase {
    @MainActor func testNativeMerchantGatewaysRetainCookieScope() throws {
        for host in ["api1.kwaishop.com", "api2.kwaishop.com"] {
            let config = try ShoppingConfiguration(gateway: URL(string: "https://\(host)")!, entrySource: "confirmed-entry")
            let client = ShoppingClient(configuration: config)
            let webCookie = HTTPCookie(properties: [.name: "token", .value: "never-cross-domain", .domain: ".kuaishou.com", .path: "/"])!
            XCTAssertThrowsError(try client.makeRequest(endpoint: "load", cookies: [webCookie]))
            let merchantCookie = HTTPCookie(properties: [.name: "token", .value: "synthetic-merchant-token", .domain: host, .path: "/", .secure: "TRUE"])!
            let request = try client.makeRequest(endpoint: "load", cookies: [webCookie, merchantCookie])
            XCTAssertEqual(request.url?.host, host)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Cookie"), "token=synthetic-merchant-token")
        }
        for host in ["api1.kwaishop.com.evil.com", "fake.kwaishop.com", "api1-kwaishop.com", "kuaishop.com", "www.kwaishop.com"] {
            XCTAssertThrowsError(try ShoppingConfiguration(gateway: URL(string: "https://\(host)")!, entrySource: "confirmed-entry"))
        }
    }

    func testConfigurationRejectsUntrustedOrAmbiguousOrigin() throws {
        for address in ["http://shop.kuaishou.com", "https://kuaishou.com.evil.com", "https://user@shop.kuaishou.com", "https://shop.kuaishou.com:444", "https://shop.kuaishou.com/api", "https://shop.kuaishou.com?q=1", "https://shop.kuaishou.com/#x"] {
            XCTAssertThrowsError(try ShoppingConfiguration(gateway: URL(string: address)!, entrySource: "approved-entry"), address)
        }
        XCTAssertThrowsError(try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: " "))
    }

    @MainActor func testRequestUsesScopedCookiesAndQueryEntrySource() throws {
        let configuration = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "approved & entry", carrierType: "desktop-confirmed", sourceID: "source")
        let client = ShoppingClient(configuration: configuration)
        let cookie = HTTPCookie(properties: [.name: "token", .value: "fake-test-token", .domain: ".kuaishou.com", .path: "/", .secure: "TRUE"])!
        let unrelated = HTTPCookie(properties: [.name: "private", .value: "never-send", .domain: "www.kuaishou.com", .path: "/"])!
        let request = try client.makeRequest(endpoint: "chat", method: "POST", cookies: [cookie, unrelated], body: Data("{}".utf8))
        let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.queryItems!
        XCTAssertEqual(query.first(where: { $0.name == "entrySrc" })?.value, "approved & entry")
        XCTAssertEqual(query.first(where: { $0.name == "carrierType" })?.value, "desktop-confirmed")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Cookie"), "token=fake-test-token")
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertFalse(request.httpShouldHandleCookies)
        XCTAssertThrowsError(try client.makeRequest(endpoint: "load", cookies: [unrelated]))
    }

    func testFramingHandlesSplitUTF8AndRejectsMalformedData() throws {
        var framer = ShoppingJSONLineFramer()
        let source = Data("{\"result\":1,\"data\":\"你好\"}\r\n{\"result\":1}\n".utf8)
        var frames: [Data] = []
        for byte in source { if let frame = try framer.append(byte) { frames.append(frame) } }
        XCTAssertEqual(frames.count, 2)
        XCTAssertNil(try framer.finish())
        var malformed = ShoppingJSONLineFramer()
        for byte in Data("data: {}".utf8) { _ = try malformed.append(byte) }
        XCTAssertThrowsError(try malformed.finish())
        var limited = ShoppingJSONLineFramer(maximumFrameBytes: 2)
        _ = try limited.append(123)
        _ = try limited.append(32)
        XCTAssertThrowsError(try limited.append(32))
    }

    func testTransportConfigurationDoesNotPersistCredentials() {
        let configuration = ShoppingClient.isolatedSessionConfiguration()
        XCTAssertNil(configuration.httpCookieStorage)
        XCTAssertNil(configuration.urlCredentialStorage)
        XCTAssertNil(configuration.urlCache)
        XCTAssertFalse(configuration.httpShouldSetCookies)
    }

    @MainActor func testHTTPFailuresDoNotExposeServerSecrets() async throws {
        defer { URLProtocolStub.reset() }
        URLProtocolStub.handler = { @Sendable request in
            (HTTPURLResponse(url: request.url!, statusCode: 401, httpVersion: nil, headerFields: nil)!, Data("private-server-error-token".utf8))
        }
        let (client, cookies) = try fixture()
        do {
            _ = try await client.load(cookies: cookies)
            XCTFail("Expected authentication failure")
        } catch {
            XCTAssertEqual(error as? ShoppingClientError, .authenticationRequired)
            XCTAssertFalse(error.localizedDescription.contains("private-server-error-token"))
        }
    }

    @MainActor func testHistoryCursorAndFeedbackUseActualContracts() async throws {
        defer { URLProtocolStub.reset() }
        URLProtocolStub.handler = { @Sendable request in
            if request.url!.path.hasSuffix("history") {
                XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems?.first(where: { $0.name == "pcursor" })?.value, "0")
                XCTAssertEqual(request.httpMethod, "GET")
            } else {
                XCTAssertEqual(request.httpMethod, "POST")
                let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting!) as! [String: Any]
                XCTAssertEqual(body["feedbackType"] as? Int, 2)
                XCTAssertEqual(body["messageId"] as? String, "message-1")
                XCTAssertEqual(body["sessionId"] as? String, "session-1")
            }
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("{\"result\":1}".utf8))
        }
        let (client, cookies) = try fixture()
        _ = try await client.history(pcursor: "0", cookies: cookies)
        _ = try await client.feedback(messageID: "message-1", sessionID: "session-1", type: 2, cookies: cookies)
        do { _ = try await client.history(pcursor: "-1", cookies: cookies); XCTFail("Invalid cursor accepted") }
        catch { XCTAssertEqual(error as? ShoppingClientError, .invalidRequest) }
    }

    @MainActor func testChatEOFCannotClaimBusinessCompletion() async throws {
        defer { URLProtocolStub.reset() }
        URLProtocolStub.handler = { @Sendable request in
            let body = try JSONSerialization.jsonObject(with: request.bodyDataForTesting!) as! [String: Any]
            XCTAssertEqual(body["content"] as? String, "test shopping query")
            XCTAssertEqual(body["contentType"] as? String, "text")
            XCTAssertEqual(body["messageId"] as? String, "mac-test-message", "History must retain the locally displayed message identity")
            XCTAssertNil(body["sessionId"], "Server owns session selection")
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("{\"result\":1,\"data\":{\"result\":1}}\n".utf8))
        }
        let (client, cookies) = try fixture()
        var count = 0
        do {
            for try await _ in client.chat(content: "test shopping query", messageID: "mac-test-message", globalParams: [:], cookies: cookies) { count += 1 }
            XCTFail("EOF must not be marked completed")
        } catch { XCTAssertEqual(error as? ShoppingClientError, .completionUnconfirmed) }
        XCTAssertEqual(count, 1)
    }

    @MainActor func testEmptyAndMalformedStreamsAreErrors() async throws {
        defer { URLProtocolStub.reset() }
        let (client, cookies) = try fixture()
        for (responseBody, expected): (String, ShoppingClientError) in [("", .emptyResponse), ("data: {}\n", .malformedFrame)] {
            URLProtocolStub.handler = { @Sendable request in
                (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data(responseBody.utf8))
            }
            do {
                for try await _ in client.chat(content: "test", messageID: "mac-test-message", globalParams: [:], cookies: cookies) {}
                XCTFail("Invalid stream accepted")
            } catch { XCTAssertEqual(error as? ShoppingClientError, expected) }
        }
    }

    @MainActor func testInvalidMessageIdentityCannotReachTransport() async throws {
        defer { URLProtocolStub.reset() }
        URLProtocolStub.handler = { @Sendable request in
            XCTFail("Invalid message identity reached the network")
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data())
        }
        let (client, cookies) = try fixture()
        for id in ["", "   ", String(repeating: "a", count: 129), "bad\nidentity"] {
            do {
                for try await _ in client.chat(content: "test", messageID: id, globalParams: [:], cookies: cookies) {}
                XCTFail("Invalid ID accepted")
            } catch { XCTAssertEqual(error as? ShoppingClientError, .invalidRequest) }
        }
    }

    func testRedirectsAreDeniedBeforeCookiesCouldFollow() {
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        let request = URLRequest(url: URL(string: "https://shop.kuaishou.com")!)
        let response = HTTPURLResponse(url: request.url!, statusCode: 302, httpVersion: nil, headerFields: nil)!
        let task = session.dataTask(with: request)
        ShoppingRedirectBlocker().urlSession(session, task: task, willPerformHTTPRedirection: response,
            newRequest: URLRequest(url: URL(string: "https://other.example")!)) { redirected in
            XCTAssertNil(redirected)
        }
    }

    @MainActor private func fixture() throws -> (ShoppingClient, [HTTPCookie]) {
        let configuration = try ShoppingConfiguration(gateway: URL(string: "https://shop.kuaishou.com")!, entrySource: "approved-entry")
        let client = ShoppingClient(configuration: configuration, sessionConfiguration: .ephemeralWithStub)
        let cookie = HTTPCookie(properties: [.name: "token", .value: "test-fixture", .domain: ".kuaishou.com", .path: "/", .secure: "TRUE"])!
        return (client, [cookie])
    }
}
