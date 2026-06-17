import Foundation

public struct WatchSummaryCache {
    public static let defaultKey = "reva.watch.summary.latest"

    private let defaults: UserDefaults
    private let key: String

    public init(
        defaults: UserDefaults = UserDefaults(suiteName: ComplicationCache.appGroup) ?? .standard,
        key: String = Self.defaultKey
    ) {
        self.defaults = defaults
        self.key = key
    }

    public func save(_ summary: WatchSummary) {
        guard let data = try? JSONEncoder().encode(summary) else { return }
        defaults.set(data, forKey: key)
    }

    public func load() -> WatchSummary? {
        guard let data = defaults.data(forKey: key) else { return nil }
        return try? JSONDecoder().decode(WatchSummary.self, from: data)
    }

    public func clear() {
        defaults.removeObject(forKey: key)
    }
}
