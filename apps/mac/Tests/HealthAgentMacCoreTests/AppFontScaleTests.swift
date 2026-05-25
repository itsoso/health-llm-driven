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
        XCTAssertEqual(AppFontScale(level: 0).displayPercent, 112)
        XCTAssertEqual(AppFontScale(level: 2).displayPercent, 140)
        XCTAssertEqual(AppFontScale(level: 4).displayPercent, 190)
    }

    func testFontScaleMapsDefaultToReadableDynamicTypeSize() {
        XCTAssertEqual(AppFontScale(level: -1).dynamicTypeSizeName, "medium")
        XCTAssertEqual(AppFontScale(level: 0).dynamicTypeSizeName, "large")
        XCTAssertEqual(AppFontScale(level: 4).dynamicTypeSizeName, "accessibility1")
    }

    func testFontScaleMapsPointSizesRelativeToDefaultLevel() {
        XCTAssertEqual(AppFontScale(level: 0).pointSize(base: 15), 15, accuracy: 0.001)
        XCTAssertEqual(AppFontScale(level: 1).pointSize(base: 15), 16.741, accuracy: 0.001)
        XCTAssertEqual(AppFontScale(level: 4).pointSize(base: 15), 25.446, accuracy: 0.001)
        XCTAssertEqual(AppFontScale(level: -1).pointSize(base: 15), 13.393, accuracy: 0.001)
    }

    func testFontScaleKeyboardShortcutsMapCommandPlusMinusAndZero() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "=", command: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "=", command: true, shift: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "+", command: true, shift: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "-", command: true), .decrease)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "0", command: true), .reset)

        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "=", command: false))
        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "-", command: true, option: true))
        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "0", command: true, control: true))
    }

    func testFontScaleKeyboardShortcutsMapMacKeyCodesWhenCharactersAreUnreliable() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 24, command: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 69, command: true), .increase)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 27, command: true), .decrease)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 29, command: true), .reset)

        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 24, command: false))
        XCTAssertNil(AppFontScaleKeyboardShortcut.action(forKeyEquivalent: "", keyCode: 24, command: true, option: true))
    }

    func testFontScaleKeyboardShortcutAppliesToScale() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.increase.apply(to: AppFontScale(level: 0)).level, 1)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.decrease.apply(to: AppFontScale(level: 0)).level, -1)
        XCTAssertEqual(AppFontScaleKeyboardShortcut.reset.apply(to: AppFontScale(level: 3)).level, AppFontScale.defaultLevel)
    }

    func testFontScaleNativeMenuShortcutsUseMacKeyEquivalents() {
        XCTAssertEqual(AppFontScaleKeyboardShortcut.nativeMenuShortcuts(for: .increase), [
            AppFontScaleNativeMenuShortcut(keyEquivalent: "=", command: true, shift: false),
            AppFontScaleNativeMenuShortcut(keyEquivalent: "=", command: true, shift: true)
        ])
        XCTAssertEqual(AppFontScaleKeyboardShortcut.nativeMenuShortcuts(for: .decrease), [
            AppFontScaleNativeMenuShortcut(keyEquivalent: "-", command: true, shift: false)
        ])
        XCTAssertEqual(AppFontScaleKeyboardShortcut.nativeMenuShortcuts(for: .reset), [
            AppFontScaleNativeMenuShortcut(keyEquivalent: "0", command: true, shift: false)
        ])
    }
}
