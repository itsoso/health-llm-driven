import Foundation

public struct AgentStreamRequest: Encodable, Equatable, Sendable {
    public let message: String
    public let conversationID: Int?
    public let extraContext: String?

    public init(message: String, conversationID: Int? = nil, extraContext: String? = nil) {
        self.message = message
        self.conversationID = conversationID
        self.extraContext = extraContext
    }

    enum CodingKeys: String, CodingKey {
        case message
        case conversationID = "conversation_id"
        case extraContext = "extra_context"
    }
}

public protocol AgentStreamServicing: Sendable {
    func stream(
        message: String,
        conversationID: Int?,
        extraContext: String?
    ) -> AsyncThrowingStream<AgentStreamEvent, Error>
}

public final class AgentStreamClient: AgentStreamServicing, @unchecked Sendable {
    private let baseURL: URL
    private let tokenProvider: AuthTokenProviding
    private let session: URLSession
    private let encoder = JSONEncoder()

    public init(
        baseURL: URL = APIEndpoint.defaultBaseURL,
        tokenProvider: AuthTokenProviding,
        session: URLSession = .shared
    ) {
        self.baseURL = baseURL
        self.tokenProvider = tokenProvider
        self.session = session
    }

    public func stream(
        message: String,
        conversationID: Int? = nil,
        extraContext: String? = nil
    ) -> AsyncThrowingStream<AgentStreamEvent, Error> {
        stream(request: AgentStreamRequest(
            message: message,
            conversationID: conversationID,
            extraContext: extraContext
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
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
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
