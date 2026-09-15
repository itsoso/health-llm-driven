import Foundation

/// Cookie selection preserves the scope granted by the login service.
/// A candidate credential is not proof that the shopping gateway accepted the login.
public enum ShoppingCookiePolicy {
    public static func matches(cookie: HTTPCookie, url: URL, now: Date = Date()) -> Bool {
        guard url.scheme?.lowercased() == "https", let host = url.host?.lowercased(),
              cookie.expiresDate.map({ $0 > now }) ?? true,
              isSafeHeaderName(cookie.name), isSafeHeaderValue(cookie.value) else { return false }
        let domain = cookie.domain.lowercased()
        let domainMatches: Bool
        if domain.hasPrefix(".") {
            let bare = String(domain.dropFirst())
            domainMatches = host == bare || host.hasSuffix("." + bare)
        } else {
            domainMatches = host == domain
        }
        guard domainMatches else { return false }
        let requestPath = url.path.isEmpty ? "/" : url.path
        let cookiePath = cookie.path.isEmpty ? "/" : cookie.path
        return requestPath == cookiePath || (requestPath.hasPrefix(cookiePath) &&
            (cookiePath.hasSuffix("/") || requestPath.dropFirst(cookiePath.count).hasPrefix("/")))
    }

    public static func matchingCookies(_ cookies: [HTTPCookie], for url: URL, now: Date = Date()) -> [HTTPCookie] {
        cookies.filter { matches(cookie: $0, url: url, now: now) }
            .sorted { $0.path.count > $1.path.count }
    }

    public static func hasServiceCredential(_ cookies: [HTTPCookie], for url: URL, now: Date = Date()) -> Bool {
        matchingCookies(cookies, for: url, now: now).contains {
            ($0.name == "token" || $0.name == "kuaishou.api_st") && !$0.value.isEmpty
        }
    }

    private static func isSafeHeaderName(_ name: String) -> Bool {
        let separators = CharacterSet(charactersIn: "()<>@,;:\\\"/[]?={} \t")
        return !name.isEmpty && name.unicodeScalars.allSatisfy { $0.value > 32 && $0.value < 127 && !separators.contains($0) }
    }

    private static func isSafeHeaderValue(_ value: String) -> Bool {
        value.unicodeScalars.allSatisfy { $0.value >= 33 && $0.value < 127 && $0 != ";" && $0 != "," && $0 != "\"" && $0 != "\\" }
    }
}
