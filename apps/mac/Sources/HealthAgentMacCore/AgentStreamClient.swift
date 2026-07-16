import Foundation

/// A chat image forwarded to the agent's multimodal/vision path. Mirrors the
/// backend `ImageItem` contract (`{base64, type}`); `type` is a bare subtype such
/// as "jpeg" / "png" (no `image/` prefix), matching mobile's client (`chat.ts`).
public struct AgentChatImage: Encodable, Equatable, Sendable {
    public let base64: String
    public let type: String

    public init(base64: String, type: String) {
        self.base64 = base64
        self.type = type
    }
}

public struct AgentClientTimeContext: Encodable, Equatable, Sendable {
    public let clientNowISO: String
    public let timezone: String?
    public let timezoneOffsetMinutes: Int
    public let locale: String?

    public init(
        clientNowISO: String,
        timezone: String? = TimeZone.current.identifier,
        timezoneOffsetMinutes: Int = TimeZone.current.secondsFromGMT() / 60,
        locale: String? = Locale.current.identifier
    ) {
        self.clientNowISO = clientNowISO
        self.timezone = timezone
        self.timezoneOffsetMinutes = timezoneOffsetMinutes
        self.locale = locale
    }

    public static func current(now: Date = Date()) -> AgentClientTimeContext {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return AgentClientTimeContext(
            clientNowISO: formatter.string(from: now),
            timezone: TimeZone.current.identifier,
            timezoneOffsetMinutes: TimeZone.current.secondsFromGMT(for: now) / 60,
            locale: Locale.current.identifier
        )
    }

    enum CodingKeys: String, CodingKey {
        case clientNowISO = "client_now_iso"
        case timezone
        case timezoneOffsetMinutes = "timezone_offset_minutes"
        case locale
    }
}

public struct AgentStreamRequest: Encodable, Equatable, Sendable {
    public let message: String
    public let conversationID: Int?
    public let extraContext: String?
    /// 输入通道声明(传输层,非 LLM 参数):mac 助手是打字输入 → "typed"。
    /// 后端据此对症状类记录免二次确认;语音/未声明通道 fail-closed 保留确认。
    public let channel: String
    /// Chat images for the agent's vision path. Encoded to match the backend
    /// `AgentRequest` schema: a single image → `image_base64` + `image_type`;
    /// two or more → `images: [{base64, type}]`. Same shape mobile sends.
    public let images: [AgentChatImage]
    /// Device-local current time for this turn. The backend still generates the
    /// authoritative server timestamp; this helps resolve user-local time zone.
    public let clientTimeContext: AgentClientTimeContext

    public init(
        message: String,
        conversationID: Int? = nil,
        extraContext: String? = nil,
        channel: String = "typed",
        images: [AgentChatImage] = [],
        clientTimeContext: AgentClientTimeContext = .current()
    ) {
        self.message = message
        self.conversationID = conversationID
        self.extraContext = extraContext
        self.channel = channel
        self.images = images
        self.clientTimeContext = clientTimeContext
    }

    enum CodingKeys: String, CodingKey {
        case message
        case conversationID = "conversation_id"
        case extraContext = "extra_context"
        case channel
        case clientTimeContext = "client_time_context"
        case imageBase64 = "image_base64"
        case imageType = "image_type"
        case images
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(message, forKey: .message)
        try container.encodeIfPresent(conversationID, forKey: .conversationID)
        try container.encodeIfPresent(extraContext, forKey: .extraContext)
        try container.encode(channel, forKey: .channel)
        try container.encode(clientTimeContext, forKey: .clientTimeContext)
        // Match the backend contract exactly: single image on the legacy
        // image_base64/image_type fields, multiple on images[]. Zero images ⇒
        // neither key is emitted (byte-identical to the old request).
        if images.count == 1, let only = images.first {
            try container.encode(only.base64, forKey: .imageBase64)
            try container.encode(only.type, forKey: .imageType)
        } else if images.count > 1 {
            try container.encode(images, forKey: .images)
        }
    }
}

public protocol AgentStreamServicing: Sendable {
    func stream(
        message: String,
        conversationID: Int?,
        extraContext: String?,
        images: [AgentChatImage]
    ) -> AsyncThrowingStream<AgentStreamEvent, Error>
}

public extension AgentStreamServicing {
    /// Back-compat convenience: callers that don't attach images keep the
    /// original 3-argument call site.
    func stream(
        message: String,
        conversationID: Int?,
        extraContext: String?
    ) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream(
            message: message,
            conversationID: conversationID,
            extraContext: extraContext,
            images: []
        )
    }
}

public final class AgentStreamClient: AgentStreamServicing, @unchecked Sendable {
    /// Inter-byte timeout for the SSE stream: the max silence allowed between
    /// chunks, NOT the total duration. An agentic turn goes quiet while a tool
    /// runs and the next LLM round generates; the backend's per-round read
    /// timeout is 120s, so the client must tolerate gaps comfortably beyond it
    /// or a single tool call trips a spurious "请求超时" (the shared default is 60s).
    private static let streamGapTimeout: TimeInterval = 300

    /// GenUI 能力协商基线(契约 v0 §3.3):Mac 能原生渲染 reva-ui 折线图 + 空态组件块。
    /// 这一段永远声明——它是本端稳定支持的既有能力。
    static let baseClientCapsHeader = "genui-v1, genui-components-v1"

    /// `X-Reva-Client-Caps` 头值。`tableCapEnabled` 为 true 才追加 `genui-table-v1`
    /// (rank1 metric_table),后端据此才对本端发结构化表格块。默认 false ⇒ 与历史逐字节一致。
    /// 拆成纯函数便于两分支各自确定性测试(编译期常量翻不了,测 builder)。
    static func clientCapsHeaderValue(tableCapEnabled: Bool) -> String {
        tableCapEnabled ? baseClientCapsHeader + ", genui-table-v1" : baseClientCapsHeader
    }

    /// 当前生效头值:读编译期暗开关 `RevaUIFeatureFlags.tableCapEnabled`。
    static var clientCapsHeaderValue: String {
        clientCapsHeaderValue(tableCapEnabled: RevaUIFeatureFlags.tableCapEnabled)
    }

    private let baseURL: URL
    private let tokenProvider: AuthTokenProviding
    private let session: URLSession
    private let encoder = JSONEncoder()

    public init(
        baseURL: URL = APIEndpoint.defaultBaseURL,
        tokenProvider: AuthTokenProviding,
        session: URLSession? = nil
    ) {
        self.baseURL = baseURL
        self.tokenProvider = tokenProvider
        self.session = session ?? Self.makeDefaultSession()
    }

    private static func makeDefaultSession() -> URLSession {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = streamGapTimeout
        // Whole-transfer ceiling: a long multi-tool turn can legitimately run
        // several minutes end to end.
        config.timeoutIntervalForResource = 600
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }

    public func stream(
        message: String,
        conversationID: Int? = nil,
        extraContext: String? = nil,
        images: [AgentChatImage] = []
    ) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream(request: AgentStreamRequest(
            message: message,
            conversationID: conversationID,
            extraContext: extraContext,
            images: images
        ))
    }

    public func stream(request: AgentStreamRequest) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let urlRequest = try await makeRequest(body: request)
                    let (bytes, response) = try await session.bytes(for: urlRequest)
                    try await validate(response: response)

                    var buffer = ""
                    for try await line in bytes.lines {
                        try Task.checkCancellation()
                        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
                        if trimmed.isEmpty {
                            try yieldParsed(buffer, continuation: continuation)
                            buffer = ""
                        } else if trimmed.hasPrefix("data:") && buffer.isEmpty {
                            try yieldParsed(trimmed + "\n\n", continuation: continuation)
                        } else {
                            buffer += line + "\n"
                        }
                    }
                    if !buffer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        try yieldParsed(buffer, continuation: continuation)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func makeRequest(body: AgentStreamRequest) async throws -> URLRequest {
        let normalizedBaseURL = baseURL.absoluteString.hasSuffix("/")
            ? baseURL
            : baseURL.appendingPathComponent("")
        guard let url = URL(string: "agent/stream", relativeTo: normalizedBaseURL)?.absoluteURL else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = Self.streamGapTimeout
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // GenUI 能力协商(契约 v0 §3.3):声明 Mac 能原生渲染 `reva-ui` 图表与空态组件块,
        // 后端仅对声明者发结构化块,旧端零回归。metric_table cap 走 `RevaUIFeatureFlags` 暗开关。
        request.setValue(Self.clientCapsHeaderValue, forHTTPHeaderField: "X-Reva-Client-Caps")
        request.httpBody = try encoder.encode(body)
        if let token = await tokenProvider.getToken(), !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func validate(response: URLResponse) async throws {
        guard let http = response as? HTTPURLResponse else {
            throw APIError.emptyResponse
        }
        if http.statusCode == 401 {
            await tokenProvider.clearToken()
            throw APIError.unauthorized
        }
        guard (200..<300).contains(http.statusCode) else {
            throw APIError.httpStatus(http.statusCode, nil)
        }
    }

    private func yieldParsed(
        _ payload: String,
        continuation: AsyncThrowingStream<AgentStreamEvent, Error>.Continuation
    ) throws {
        for event in try AgentStreamParser.parse(payload) {
            continuation.yield(event)
        }
    }
}
