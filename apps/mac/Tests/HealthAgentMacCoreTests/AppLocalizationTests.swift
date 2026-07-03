import XCTest
@testable import HealthAgentMacCore

final class AppLocalizationTests: XCTestCase {
    func testChineseLoginIdentifierCopyMentionsPhone() {
        XCTAssertEqual(
            L10n.text("Phone, email, or username", language: .zh),
            "手机号、邮箱或用户名"
        )
    }
}
