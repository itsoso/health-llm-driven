import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ShoppingLoginPolicyTests: XCTestCase {
    func testLoginNavigationRejectsNonOfficialAndCredentialURLs() {
        for value in ["https://www.kuaishou.com/new-reco", "https://id.kuaishou.com/", "https://passport.kuaishou.com/"] {
            XCTAssertTrue(ShoppingLoginPolicy.allowsNavigation(URL(string: value)!))
        }
        for value in ["http://www.kuaishou.com", "https://www.kuaishou.com.evil.com", "https://www.kuaishou.com:8443", "https://user:pass@www.kuaishou.com", "javascript:alert(1)", "kwai://home"] {
            XCTAssertFalse(ShoppingLoginPolicy.allowsNavigation(URL(string: value)!))
        }
    }

    func testProductLinkDoesNotAllowCredentialsPortsOrCustomSchemes() {
        XCTAssertTrue(ShoppingLoginPolicy.allowsProductLink(URL(string: "https://www.kuaishou.com/item/1")!))
        for value in ["https://kuaishou.com.evil.com/", "https://user@www.kuaishou.com", "http://www.kuaishou.com", "kwai://item/1", "file:///tmp/secret", "https://www.kuaishou.com:8443/"] {
            XCTAssertFalse(ShoppingLoginPolicy.allowsProductLink(URL(string: value)!))
        }
    }
}
