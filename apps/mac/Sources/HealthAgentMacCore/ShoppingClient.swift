import Foundation

public enum ShoppingClientError: Error, LocalizedError, Equatable, Sendable {
    case invalidConfiguration, missingCredential, invalidRequest, authenticationRequired
    case httpStatus(Int), invalidResponse, responseTooLarge, malformedFrame, emptyResponse
    case completionUnconfirmed, networkFailure

    public var errorDescription: String? {
        switch self {
        case .invalidConfiguration: "请配置已确认的快手 HTTPS 网关和入口标识。"
        case .missingCredential: "当前网页登录态尚不能用于这个购物服务。"
        case .invalidRequest: "购物请求参数不完整或无效。"
        case .authenticationRequired: "购物服务未接受当前登录态，请重新确认授权。"
        case .httpStatus(let status): "购物服务请求失败（HTTP \(status)）。"
        case .invalidResponse: "购物服务返回了无法识别的响应。"
        case .responseTooLarge: "购物响应超出当前客户端处理范围。"
        case .malformedFrame: "购物消息格式尚不兼容，已停止接收。"
        case .emptyResponse: "购物服务没有返回消息。"
        case .completionUnconfirmed: "连接已结束；尚未确认服务端回复完成。"
        case .networkFailure: "购物服务暂时无法连接，请检查网络与接入配置。"
        }
    }
}

public struct ShoppingConfiguration: Equatable, Sendable {
    public let gateway: URL
    public let entrySource: String
    public let carrierType: String?
    public let sourceID: String?
    public var chatURL: URL { gateway.appendingPathComponent(Self.apiPath + "/chat") }
    private static let apiPath = "rest/app/kwaishop/intelligent/guide/assistant"
    // Explicit native merchant hosts from KSCommonParamsImpl. Cookie domains
    // remain enforced independently; adding a host never rewrites credentials.
    private static let merchantHosts: Set<String> = ["api1.kwaishop.com", "api2.kwaishop.com"]

    public init(gateway: URL, entrySource: String, carrierType: String? = nil, sourceID: String? = nil) throws {
        guard let parts = URLComponents(url: gateway, resolvingAgainstBaseURL: false),
              parts.scheme?.lowercased() == "https", let host = parts.host?.lowercased(),
              (host == "kuaishou.com" || host.hasSuffix(".kuaishou.com") || Self.merchantHosts.contains(host)),
              parts.user == nil, parts.password == nil, parts.port == nil || parts.port == 443,
              parts.path.isEmpty || parts.path == "/", parts.query == nil, parts.fragment == nil,
              Self.validParameter(entrySource),
              carrierType.map(Self.validParameter) ?? true, sourceID.map(Self.validParameter) ?? true else {
            throw ShoppingClientError.invalidConfiguration
        }
        self.gateway = gateway
        self.entrySource = entrySource
        self.carrierType = carrierType
        self.sourceID = sourceID
    }

    private static func validParameter(_ value: String) -> Bool {
        !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && value.utf8.count <= 512 &&
        value.unicodeScalars.allSatisfy { !CharacterSet.controlCharacters.contains($0) }
    }

    func url(endpoint: String, extraQuery: [URLQueryItem] = []) throws -> URL {
        guard ["load", "chat", "questions", "session/history", "feedback"].contains(endpoint),
              var components = URLComponents(url: gateway.appendingPathComponent(Self.apiPath + "/" + endpoint), resolvingAgainstBaseURL: false) else {
            throw ShoppingClientError.invalidRequest
        }
        components.queryItems = [URLQueryItem(name: "entrySrc", value: entrySource)]
        if let carrierType { components.queryItems?.append(URLQueryItem(name: "carrierType", value: carrierType)) }
        if let sourceID { components.queryItems?.append(URLQueryItem(name: "sourceId", value: sourceID)) }
        components.queryItems?.append(contentsOf: extraQuery)
        guard let url = components.url else { throw ShoppingClientError.invalidConfiguration }
        return url
    }
}

@MainActor public protocol ShoppingService {
    func load(cookies: [HTTPCookie]) async throws -> Data
    func questions(cookies: [HTTPCookie]) async throws -> Data
    func history(pcursor: String, cookies: [HTTPCookie]) async throws -> Data
    func feedback(messageID: String, sessionID: String?, type: Int, cookies: [HTTPCookie]) async throws -> Data
    func chat(content: String, messageID: String, globalParams: [String: ShoppingJSONValue], cookies: [HTTPCookie]) -> AsyncThrowingStream<Data, Error>
}

/// Each request uses only scoped, memory-resident shopping cookies. Never accepts a health token.
@MainActor public final class ShoppingClient: ShoppingService {
    public let configuration: ShoppingConfiguration
    private let session: URLSession

    public init(configuration: ShoppingConfiguration) {
        self.configuration = configuration
        session = URLSession(configuration: Self.isolatedSessionConfiguration(), delegate: ShoppingRedirectBlocker(), delegateQueue: nil)
    }

    // Injection is internal and used only by request-level tests.
    init(configuration: ShoppingConfiguration, sessionConfiguration: URLSessionConfiguration) {
        self.configuration = configuration
        let isolated = sessionConfiguration.copy() as! URLSessionConfiguration
        Self.removeAmbientCredentials(from: isolated)
        session = URLSession(configuration: isolated, delegate: ShoppingRedirectBlocker(), delegateQueue: nil)
    }

    deinit { session.invalidateAndCancel() }

    public nonisolated static func isolatedSessionConfiguration() -> URLSessionConfiguration {
        let configuration = URLSessionConfiguration.ephemeral
        removeAmbientCredentials(from: configuration)
        return configuration
    }

    private nonisolated static func removeAmbientCredentials(from configuration: URLSessionConfiguration) {
        configuration.httpCookieStorage = nil
        configuration.urlCredentialStorage = nil
        configuration.urlCache = nil
        configuration.httpShouldSetCookies = false
        configuration.httpAdditionalHeaders = nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 120
        configuration.timeoutIntervalForResource = 180
    }

    public func load(cookies: [HTTPCookie]) async throws -> Data {
        try await perform(makeRequest(endpoint: "load", cookies: cookies))
    }
    public func questions(cookies: [HTTPCookie]) async throws -> Data {
        try await perform(makeRequest(endpoint: "questions", cookies: cookies))
    }
    public func history(pcursor: String, cookies: [HTTPCookie]) async throws -> Data {
        guard !pcursor.isEmpty, pcursor.allSatisfy({ $0.isASCII && $0.isNumber }), let cursor = Int32(pcursor), cursor >= 0 else {
            throw ShoppingClientError.invalidRequest
        }
        return try await perform(makeRequest(endpoint: "session/history", cookies: cookies, extraQuery: [URLQueryItem(name: "pcursor", value: pcursor)]))
    }
    public func feedback(messageID: String, sessionID: String?, type: Int, cookies: [HTTPCookie]) async throws -> Data {
        guard !messageID.isEmpty, (1...3).contains(type) else { throw ShoppingClientError.invalidRequest }
        var body: [String: ShoppingJSONValue] = ["messageId": .string(messageID), "feedbackType": .number(Decimal(type))]
        if let sessionID { body["sessionId"] = .string(sessionID) }
        return try await perform(makeRequest(endpoint: "feedback", method: "POST", cookies: cookies, body: JSONEncoder().encode(body)))
    }

    public func chat(content: String, messageID: String, globalParams: [String: ShoppingJSONValue], cookies: [HTTPCookie]) -> AsyncThrowingStream<Data, Error> {
        AsyncThrowingStream(bufferingPolicy: .bufferingOldest(256)) { continuation in
            let task = Task { @MainActor [self] in
                do {
                    guard !content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, content.utf8.count <= 64 * 1024,
                          !messageID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, messageID.utf8.count <= 128,
                          messageID.unicodeScalars.allSatisfy({ !CharacterSet.controlCharacters.contains($0) }) else {
                        throw ShoppingClientError.invalidRequest
                    }
                    // The service preserves a supplied ID when recording history.
                    let body: [String: ShoppingJSONValue] = ["messageId": .string(messageID), "content": .string(content), "contentType": .string("text"), "globalParams": .object(globalParams)]
                    let request = try makeRequest(endpoint: "chat", method: "POST", cookies: cookies, body: JSONEncoder().encode(body))
                    let (bytes, response) = try await session.bytes(for: request)
                    try Self.validate(response)
                    var framer = ShoppingJSONLineFramer()
                    var count = 0
                    var frames = 0
                    for try await byte in bytes {
                        try Task.checkCancellation()
                        count += 1
                        guard count <= 32 * 1024 * 1024 else { throw ShoppingClientError.responseTooLarge }
                        if let frame = try framer.append(byte) {
                            try Self.yield(frame, to: continuation)
                            frames += 1
                        }
                    }
                    try Task.checkCancellation()
                    if let frame = try framer.finish() {
                        try Self.yield(frame, to: continuation)
                        frames += 1
                    }
                    // HTTP EOF is not a documented business completion marker in the available contract.
                    throw frames == 0 ? ShoppingClientError.emptyResponse : ShoppingClientError.completionUnconfirmed
                } catch {
                    continuation.finish(throwing: Self.safeError(error))
                }
            }
            continuation.onTermination = { @Sendable _ in task.cancel() }
        }
    }

    func makeRequest(endpoint: String, method: String = "GET", cookies: [HTTPCookie], body: Data? = nil, extraQuery: [URLQueryItem] = []) throws -> URLRequest {
        let url = try configuration.url(endpoint: endpoint, extraQuery: extraQuery)
        guard ShoppingCookiePolicy.hasServiceCredential(cookies, for: url) else { throw ShoppingClientError.missingCredential }
        let scoped = ShoppingCookiePolicy.matchingCookies(cookies, for: url)
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.httpShouldHandleCookies = false
        request.setValue(scoped.map { "\($0.name)=\($0.value)" }.joined(separator: "; "), forHTTPHeaderField: "Cookie")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        return request
    }

    private func perform(_ request: URLRequest) async throws -> Data {
        do {
            let (bytes, response) = try await session.bytes(for: request)
            try Self.validate(response)
            var data = Data()
            for try await byte in bytes {
                try Task.checkCancellation()
                guard data.count < 8 * 1024 * 1024 else { throw ShoppingClientError.responseTooLarge }
                data.append(byte)
            }
            guard !data.isEmpty else { throw ShoppingClientError.emptyResponse }
            guard (try? JSONSerialization.jsonObject(with: data)) is [String: Any] else { throw ShoppingClientError.invalidResponse }
            return data
        } catch { throw Self.safeError(error) }
    }

    private static func yield(_ frame: Data, to continuation: AsyncThrowingStream<Data, Error>.Continuation) throws {
        switch continuation.yield(frame) {
        case .enqueued: break
        case .dropped: throw ShoppingClientError.responseTooLarge
        case .terminated: throw CancellationError()
        @unknown default: throw ShoppingClientError.invalidResponse
        }
    }

    private static func validate(_ response: URLResponse) throws {
        guard let response = response as? HTTPURLResponse else { throw ShoppingClientError.invalidResponse }
        if response.statusCode == 401 || response.statusCode == 403 { throw ShoppingClientError.authenticationRequired }
        guard (200..<300).contains(response.statusCode) else { throw ShoppingClientError.httpStatus(response.statusCode) }
    }

    private static func safeError(_ error: Error) -> Error {
        if error is CancellationError || (error as? URLError)?.code == .cancelled { return CancellationError() }
        return (error as? ShoppingClientError) ?? ShoppingClientError.networkFailure
    }
}

/// URLSession removes HTTP transfer chunking; the source Harmony parser then splits JSON by newline.
/// SSE, binary KStreaming or other framing requires a verified adapter, not a heuristic fallback.
struct ShoppingJSONLineFramer {
    private var buffer = Data()
    let maximumFrameBytes: Int
    init(maximumFrameBytes: Int = 2 * 1024 * 1024) { self.maximumFrameBytes = maximumFrameBytes }

    mutating func append(_ byte: UInt8) throws -> Data? {
        if byte == 10 { return try finish() }
        guard buffer.count < maximumFrameBytes else { throw ShoppingClientError.responseTooLarge }
        buffer.append(byte)
        return nil
    }

    mutating func finish() throws -> Data? {
        defer { buffer.removeAll(keepingCapacity: true) }
        guard !buffer.allSatisfy({ $0 == 13 || $0 == 32 || $0 == 9 }) else { return nil }
        guard String(data: buffer, encoding: .utf8) != nil,
              (try? JSONSerialization.jsonObject(with: buffer)) is [String: Any] else { throw ShoppingClientError.malformedFrame }
        return buffer
    }
}

final class ShoppingRedirectBlocker: NSObject, URLSessionTaskDelegate, Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping @Sendable (URLRequest?) -> Void) {
        completionHandler(nil)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        // Keep platform certificate validation; do not offer system HTTP credentials to this service.
        if challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust {
            completionHandler(.performDefaultHandling, nil)
        } else {
            completionHandler(.cancelAuthenticationChallenge, nil)
        }
    }
}
