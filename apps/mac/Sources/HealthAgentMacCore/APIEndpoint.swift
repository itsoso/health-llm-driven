import Foundation

public enum APIEndpoint {
    public static let defaultBaseURL = URL(string: "https://health.executor.life/api/v1")!
    public static let baseURLDefaultsKey = "apiBaseURL"

    public static func resolvedBaseURL(defaults: UserDefaults = .standard) -> URL {
        guard
            let rawValue = defaults.string(forKey: baseURLDefaultsKey)?
                .trimmingCharacters(in: .whitespacesAndNewlines),
            !rawValue.isEmpty,
            let url = URL(string: rawValue),
            let scheme = url.scheme,
            ["http", "https"].contains(scheme),
            url.host != nil
        else {
            return defaultBaseURL
        }
        return url
    }
}
