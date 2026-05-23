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

    func testFontScaleKeyboardShortcutsMapCommandPlusMinusAndZero() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "=", command: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "+", command: true, shift: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "-", command: true), .decrease)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "0", command: true), .reset)

        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "=", command: false))
        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "-", command: true, option: true))
        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "0", command: true, control: true))
    }

    func testFontScaleKeyboardShortcutAppliesToScale() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.increase.apply(to: AppFontScale(level: 0)).level, 1)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.decrease.apply(to: AppFontScale(level: 0)).level, -1)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.reset.apply(to: AppFontScale(level: 3)).level, AppFontScale.defaultLevel)
    }
}
