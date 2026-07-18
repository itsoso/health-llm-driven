import Foundation

/// Owner-scoped projection for a Xiaoba AIGC task. The backend returns only a
/// signed private result URL; prompt text and provider URLs are never included.
public struct AIGCMediaJobProjection: Decodable, Equatable, Sendable {
    public struct Result: Decodable, Equatable, Sendable {
        public let mediaType: String?
        public let url: String?

        enum CodingKeys: String, CodingKey {
            case mediaType = "media_type"
            case url
        }
    }

    public let id: String
    public let kind: String
    public let status: String
    public let progress: Int
    public let result: Result?
    public let errorMessage: String?

    enum CodingKeys: String, CodingKey {
        case id, kind, status, progress, result
        case errorMessage = "error_message"
    }

    public var isTerminal: Bool {
        ["succeeded", "failed", "cancelled", "submission_unknown"].contains(status.lowercased())
    }

    /// This URL is an owner-scoped short-lived capability. It must stay in
    /// memory and never be copied into an AgentChatMessage/UserDefaults card.
    public var resultURL: String? { result?.url }

    public func persistedCardData(title: String = "小巴创作") -> AgentDynamicCardValue {
        var values: [String: AgentDynamicCardValue] = [
            "job_id": .string(id),
            "kind": .string(kind),
            "status": .string(status),
            "progress": .int(progress),
            "title": .string(title),
        ]
        if let result {
            values["result"] = .object([
                "media_type": result.mediaType.map(AgentDynamicCardValue.string) ?? .null,
                "url": .null,
            ])
        }
        if let errorMessage, !errorMessage.isEmpty {
            values["error_message"] = .string(errorMessage)
        }
        return .object(values)
    }
}

public protocol AIGCMediaJobLoading: Sendable {
    func getJob(id: String) async throws -> AIGCMediaJobProjection
    func confirmDraft(id: String) async throws -> AIGCMediaJobProjection
}

public final class AIGCMediaJobClient: AIGCMediaJobLoading, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func getJob(id: String) async throws -> AIGCMediaJobProjection {
        try await apiClient.get("aigc/media/jobs/\(id)")
    }

    public func confirmDraft(id: String) async throws -> AIGCMediaJobProjection {
        try await apiClient.post("aigc/media/confirmations/\(id)/confirm", body: EmptyRequest())
    }
}

private struct EmptyRequest: Encodable {}
