import XCTest
@testable import HealthAgentMacCore

final class AppFontScaleTests: XCTestCase {
    func testFontScaleIncreasesDecreasesAndClamps() {
        XCTAssertEqual(AppFontScale(level: 0).increased().level, 1)
        XCTAssertEqual(AppFontScale(level: 1).decreased().level, 0)
        XCTAssertEqual(AppFontScale(level: 99).level, AppFontScale.maxLevel)
        XCTAssertEqual(AppFontScale(level: -99).level, AppFontScale.minLevel)
    }

    func testFontScaleResetReturnsDefaultReadableSize() {
        XCTAssertEqual(AppFontScale(level: 3).reset().level, AppFontScale.defaultLevel)
        XCTAssertEqual(AppFontScale(level: 0).displayPercent, 100)
        XCTAssertEqual(AppFontScale(level: 2).displayPercent, 125)
    }
}
