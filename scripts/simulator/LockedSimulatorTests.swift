import XCTest

// Infrastructure probe only. This does not certify Reva's business flows.
final class LockedSimulatorTests: XCTestCase {
    func testNativeNavigationWithoutDesktopInput() {
        let app = XCUIApplication(bundleIdentifier: "com.apple.Preferences")
        app.launch()
        XCTAssertTrue(app.wait(for: .runningForeground, timeout: 20))
        for _ in 0..<8 { app.swipeDown() }
        let general = app.staticTexts.matching(NSPredicate(format: "label == 'General' OR label == '通用' OR identifier == 'General'")).firstMatch
        for _ in 0..<8 {
            if general.exists && general.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(general.waitForExistence(timeout: 10), "General settings must be present")
        general.tap()
        XCTAssertTrue(app.navigationBars.matching(NSPredicate(format: "identifier == 'General' OR identifier == '通用'")).firstMatch.waitForExistence(timeout: 10))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.lifetime = .keepAlways
        add(screenshot)
        app.terminate()
    }
}
