import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ShoppingCookiePolicyTests: XCTestCase {
    private let url = URL(string: "https://shop.kuaishou.com/rest/app/chat")!
    private func cookie(_ name: String = "token", domain: String = ".kuaishou.com", path: String = "/", expires: Date? = nil) -> HTTPCookie {
        var properties: [HTTPCookiePropertyKey: Any] = [.name: name, .value: "test-value", .domain: domain, .path: path, .secure: "TRUE"]
        if let expires { properties[.expires] = expires }
        return HTTPCookie(properties: properties)!
    }

    func testCookieScopeIsNeverWidened() {
        XCTAssertTrue(ShoppingCookiePolicy.matches(cookie: cookie(), url: url))
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: cookie(domain: "kuaishou.com"), url: url))
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: cookie(), url: URL(string: "https://notkuaishou.com/rest")!))
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: cookie(), url: URL(string: "http://shop.kuaishou.com/rest")!))
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: cookie(path: "/rest/app/c"), url: url))
        XCTAssertTrue(ShoppingCookiePolicy.matches(cookie: cookie(path: "/rest/app"), url: url))
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: cookie(expires: Date(timeIntervalSince1970: 1)), url: url))
    }

    func testWebsiteSessionIsNotShoppingAuthentication() {
        XCTAssertFalse(ShoppingCookiePolicy.hasServiceCredential([cookie("kuaishou.server.webday7_st")], for: url))
        XCTAssertFalse(ShoppingCookiePolicy.hasServiceCredential([cookie(domain: "www.kuaishou.com")], for: url))
        XCTAssertTrue(ShoppingCookiePolicy.hasServiceCredential([cookie("kuaishou.api_st")], for: url))
    }

    func testInvalidHeaderValuesCannotBeInjected() {
        let injected = HTTPCookie(properties: [.name: "token", .value: "value; other=secret", .domain: ".kuaishou.com", .path: "/"])!
        XCTAssertFalse(ShoppingCookiePolicy.matches(cookie: injected, url: url))
    }
}
