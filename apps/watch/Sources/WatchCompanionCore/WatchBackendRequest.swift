import Foundation

public enum WatchBackendRequest {
    public enum Error: Swift.Error, Equatable {
        case invalidBaseURL
        case routeNotAllowed
        case invalidJSONBody
    }

    public static let defaultAPIBase = "https://health.executor.life/api/v1"

    private static let allowedRoutes: [String: Set<String>] = [
        "/water/records/quick": ["POST"],
        "/daily-health/exercise": ["POST"],
        "/diet/voice/parse": ["POST"],
        "/diet/records": ["POST"],
        "/client-events": ["POST"],
        "/watch/ask": ["POST"],
        "/watch/symptoms": ["POST"],
    ]
    private static let watchActionPrefix = "/watch/actions/"
    private static let watchActionSuffixes = ["/complete", "/skip", "/snooze"]

    public static func summary(apiBase: String = defaultAPIBase, token: String) throws -> URLRequest {
        try request(path: "/watch/summary", method: "GET", query: [:], body: nil, apiBase: apiBase, token: token)
    }

    public static func quickRecord(
        _ quick: QuickRecordRequest,
        apiBase: String = defaultAPIBase,
        token: String
    ) throws -> URLRequest {
        guard isRouteAllowed(path: quick.path, method: quick.method) else { throw Error.routeNotAllowed }
        return try request(
            path: quick.path,
            method: quick.method,
            query: quick.query,
            body: quick.body.isEmpty ? nil : quick.body,
            apiBase: apiBase,
            token: token
        )
    }

    public static func event(
        name: String,
        meta: [String: String],
        apiBase: String = defaultAPIBase,
        token: String
    ) throws -> URLRequest {
        guard isRouteAllowed(path: "/client-events", method: "POST") else { throw Error.routeNotAllowed }
        var envelope: [String: Any] = ["event_name": name]
        if !meta.isEmpty { envelope["meta"] = meta }
        return try request(path: "/client-events", method: "POST", query: [:], body: envelope, apiBase: apiBase, token: token)
    }

    public static func watchAsk(
        _ ask: WatchAskRequest,
        apiBase: String = defaultAPIBase,
        token: String
    ) throws -> URLRequest {
        guard isRouteAllowed(path: "/watch/ask", method: "POST") else { throw Error.routeNotAllowed }
        return try request(path: "/watch/ask", method: "POST", query: [:], body: ask.body, apiBase: apiBase, token: token)
    }

    public static func isRouteAllowed(path: String, method: String) -> Bool {
        let method = method.uppercased()
        if allowedRoutes[path]?.contains(method) == true { return true }
        return isWatchActionMutation(path: path, method: method)
    }

    private static func isWatchActionMutation(path: String, method: String) -> Bool {
        guard method == "POST" else { return false }
        guard !path.contains("..") else { return false }
        guard path.hasPrefix(watchActionPrefix),
              let suffix = watchActionSuffixes.first(where: { path.hasSuffix($0) }) else { return false }
        let actionId = String(path.dropFirst(watchActionPrefix.count).dropLast(suffix.count))
        guard !actionId.contains("/") else { return false }
        return isValidActionID(actionId)
    }

    private static func isValidActionID(_ value: String) -> Bool {
        guard value.hasPrefix("agenda-") else { return false }
        let parts = value.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3, parts[0] == "agenda" else { return false }
        guard !parts[1].isEmpty, !parts[2].isEmpty else { return false }
        let objectTypeOK = parts[1].allSatisfy { $0 == "_" || ("a"..."z").contains($0) }
        let objectIdOK = parts[2].allSatisfy { ("0"..."9").contains($0) }
        return objectTypeOK && objectIdOK
    }

    private static func request(
        path: String,
        method: String,
        query: [String: String],
        body: Any?,
        apiBase: String,
        token: String
    ) throws -> URLRequest {
        guard var comps = URLComponents(string: apiBase + path) else { throw Error.invalidBaseURL }
        if !query.isEmpty {
            comps.queryItems = query.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        guard let url = comps.url else { throw Error.invalidBaseURL }
        var req = URLRequest(url: url)
        req.httpMethod = method.uppercased()
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            guard JSONSerialization.isValidJSONObject(body),
                  let data = try? JSONSerialization.data(withJSONObject: body) else {
                throw Error.invalidJSONBody
            }
            req.httpBody = data
        }
        return req
    }
}
