import Foundation
import XCTest
@testable import HealthAgentMacCore

final class ErrorPresentationTests: XCTestCase {
    func testAPIErrorUsesItsFriendlyMessageNotRawBody() {
        // 5xx must be generic; HTML body must never appear.
        let html = "<html><body>502 Bad Gateway nginx</body></html>"
        let msg = ErrorPresentation.detail(APIError.httpStatus(502, html), language: .zh)
        XCTAssertFalse(msg.contains("<"))
        XCTAssertFalse(msg.contains("nginx"))
        XCTAssertEqual(msg, "服务暂时不可用，请稍后再试。")
    }

    func testNonAPIErrorWithMarkupFallsBackToGeneric() {
        struct HTMLErr: LocalizedError { var errorDescription: String? { "<html>boom</html>" } }
        let msg = ErrorPresentation.detail(HTMLErr(), language: .zh)
        XCTAssertFalse(msg.contains("<"))
        XCTAssertEqual(msg, "出了点问题，请稍后再试。")
    }

    func testNonAPIErrorWithOverlongTextFallsBackToGeneric() {
        struct LongErr: LocalizedError { var errorDescription: String? { String(repeating: "x", count: 300) } }
        let msg = ErrorPresentation.detail(LongErr(), language: .zh)
        XCTAssertEqual(msg, "出了点问题，请稍后再试。")
    }

    func testShortPlainErrorIsPassedThrough() {
        struct ShortErr: LocalizedError { var errorDescription: String? { "文件无法读取" } }
        let msg = ErrorPresentation.detail(ShortErr(), language: .zh)
        XCTAssertEqual(msg, "文件无法读取")
    }
}
