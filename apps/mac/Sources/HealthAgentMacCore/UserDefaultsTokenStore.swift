import Foundation

public final class UserDefaultsTokenStore: AuthTokenStoring, @unchecked Sendable {
    public static let defaultsKey = "authToken"

    private let defaults: UserDefaults
    private let key: String

    public init(
        defaults: UserDefaults = .standard,
        key: String = UserDefaultsTokenStore.defaultsKey
    ) {
        self.defaults = defaults
        self.key = key
    }

    public func setToken(_ token: String) async throws {
        defaults.set(token, forKey: key)
    }

    public func getToken() async -> String? {
        defaults.string(forKey: key)
    }

    public func clearToken() async {
        defaults.removeObject(forKey: key)
    }
}
