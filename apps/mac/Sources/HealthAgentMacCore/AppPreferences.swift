import Foundation

/// Single source of truth for user-tunable preference keys + defaults that are
/// read in more than one place (the Settings UI via @AppStorage and the
/// SafetyMonitor at poll time). Keeping the keys and defaults here prevents the
/// two sides from silently drifting (e.g. UI default true vs. monitor reading
/// false because UserDefaults had no value registered).
public enum AppPreferences {
    public enum Keys {
        public static let safetyAlertsEnabled = "safetyAlertsEnabled"
        public static let safetyAlertSound = "safetyAlertSound"
        public static let safetyAlertMinSeverity = "safetyAlertMinSeverity"
        public static let safetyPollMinutes = "safetyPollMinutes"
    }

    public static let defaultSafetyAlertsEnabled = true
    public static let defaultSafetyAlertSound = true
    public static let defaultMinSeverity = 3            // 3 = High, 4 = Critical
    public static let defaultPollMinutes = 5
    public static let pollMinutesOptions = [3, 5, 10, 15, 30]

    /// Registers defaults so unset keys read consistently from both @AppStorage
    /// and UserDefaults.standard.bool/integer (which would otherwise return
    /// false/0). Call once at app start.
    public static func registerDefaults(_ defaults: UserDefaults = .standard) {
        defaults.register(defaults: [
            Keys.safetyAlertsEnabled: defaultSafetyAlertsEnabled,
            Keys.safetyAlertSound: defaultSafetyAlertSound,
            Keys.safetyAlertMinSeverity: defaultMinSeverity,
            Keys.safetyPollMinutes: defaultPollMinutes,
        ])
    }

    public static func safetyAlertsEnabled(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: Keys.safetyAlertsEnabled) as? Bool ?? defaultSafetyAlertsEnabled
    }

    public static func safetyAlertSound(_ defaults: UserDefaults = .standard) -> Bool {
        defaults.object(forKey: Keys.safetyAlertSound) as? Bool ?? defaultSafetyAlertSound
    }

    public static func safetyAlertMinSeverity(_ defaults: UserDefaults = .standard) -> Int {
        let raw = defaults.object(forKey: Keys.safetyAlertMinSeverity) as? Int ?? defaultMinSeverity
        return min(max(raw, 1), 5)
    }

    public static func safetyPollMinutes(_ defaults: UserDefaults = .standard) -> Int {
        let raw = defaults.object(forKey: Keys.safetyPollMinutes) as? Int ?? defaultPollMinutes
        return min(max(raw, 1), 60)
    }
}
