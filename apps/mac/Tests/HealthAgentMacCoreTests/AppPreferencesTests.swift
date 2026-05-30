import Foundation
import XCTest
@testable import HealthAgentMacCore

final class AppPreferencesTests: XCTestCase {
    private func makeDefaults() -> UserDefaults {
        let suite = "AppPreferences-\(UUID().uuidString)"
        return UserDefaults(suiteName: suite)!
    }

    func testUnsetKeysReturnDocumentedDefaults() {
        let defaults = makeDefaults()
        XCTAssertEqual(AppPreferences.safetyAlertsEnabled(defaults), true)
        XCTAssertEqual(AppPreferences.safetyAlertSound(defaults), true)
        XCTAssertEqual(AppPreferences.safetyAlertMinSeverity(defaults), 3)
        XCTAssertEqual(AppPreferences.safetyPollMinutes(defaults), 5)
    }

    func testRegisterDefaultsMakesBoolAndIntReadConsistently() {
        let defaults = makeDefaults()
        AppPreferences.registerDefaults(defaults)
        XCTAssertTrue(defaults.bool(forKey: AppPreferences.Keys.safetyAlertsEnabled))
        XCTAssertEqual(defaults.integer(forKey: AppPreferences.Keys.safetyPollMinutes), 5)
    }

    func testSeverityIsClampedToValidRange() {
        let defaults = makeDefaults()
        defaults.set(99, forKey: AppPreferences.Keys.safetyAlertMinSeverity)
        XCTAssertEqual(AppPreferences.safetyAlertMinSeverity(defaults), 5)
        defaults.set(0, forKey: AppPreferences.Keys.safetyAlertMinSeverity)
        XCTAssertEqual(AppPreferences.safetyAlertMinSeverity(defaults), 1)
    }

    func testPollMinutesIsClampedToValidRange() {
        let defaults = makeDefaults()
        defaults.set(9999, forKey: AppPreferences.Keys.safetyPollMinutes)
        XCTAssertEqual(AppPreferences.safetyPollMinutes(defaults), 60)
        defaults.set(0, forKey: AppPreferences.Keys.safetyPollMinutes)
        XCTAssertEqual(AppPreferences.safetyPollMinutes(defaults), 1)
    }

    func testUserSetValuesAreHonored() {
        let defaults = makeDefaults()
        defaults.set(false, forKey: AppPreferences.Keys.safetyAlertsEnabled)
        defaults.set(4, forKey: AppPreferences.Keys.safetyAlertMinSeverity)
        defaults.set(15, forKey: AppPreferences.Keys.safetyPollMinutes)
        XCTAssertFalse(AppPreferences.safetyAlertsEnabled(defaults))
        XCTAssertEqual(AppPreferences.safetyAlertMinSeverity(defaults), 4)
        XCTAssertEqual(AppPreferences.safetyPollMinutes(defaults), 15)
    }
}
