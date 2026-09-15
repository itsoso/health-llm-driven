import Foundation

public enum ShoppingLoginPolicy {
    public static let loginURL = URL(string: "https://www.kuaishou.com/new-reco")!
    private static let loginHosts: Set<String> = ["www.kuaishou.com", "id.kuaishou.com", "passport.kuaishou.com"]

    public static func allowsNavigation(_ url: URL) -> Bool {
        isHTTPS(url) && loginHosts.contains(url.host?.lowercased() ?? "")
    }

    public static func allowsProductLink(_ url: URL) -> Bool {
        guard isHTTPS(url), let host = url.host?.lowercased() else { return false }
        return host == "kuaishou.com" || host.hasSuffix(".kuaishou.com")
    }

    private static func isHTTPS(_ url: URL) -> Bool {
        url.scheme?.lowercased() == "https" && url.user == nil && url.password == nil
            && (url.port == nil || url.port == 443)
    }
}

/// Implementations must return only this shopping browser's cookies, never the
/// health Token or another browser's credential store.
@MainActor
public protocol ShoppingCredentialSource: AnyObject {
    func cookies() async -> [HTTPCookie]
    func reset()
}
