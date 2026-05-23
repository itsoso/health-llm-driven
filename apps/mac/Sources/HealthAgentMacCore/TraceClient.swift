import Foundation

public struct ConversationTrace: Decodable, Equatable, Sendable {
    public let conversation: TraceConversation
    public let messages: [TraceMessage]
    public let assistantMessage: TraceAssistantMessage
    public let sourcesUsed: [String]
    public let toolCalls: [TraceToolCall]
    public let evidenceCards: [TraceEvidenceCard]

    enum CodingKeys: String, CodingKey {
        case conversation
        case messages
        case assistantMessage = "assistant_message"
        case sourcesUsed = "sources_used"
        case toolCalls = "tool_calls"
        case evidenceCards = "evidence_cards"
    }
}

public struct TraceConversation: Decodable, Equatable, Sendable {
    public let id: Int
    public let title: String?
}

public struct TraceMessage: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let role: String
    public let content: String
}

public struct TraceAssistantMessage: Decodable, Equatable, Sendable {
    public let id: Int?
    public let model: String?
    public let finishReason: String?
    public let completionStatus: String?

    enum CodingKeys: String, CodingKey {
        case id
        case model
        case finishReason = "finish_reason"
        case completionStatus = "completion_status"
    }
}

public struct TraceToolCall: Decodable, Equatable, Sendable {
    public let name: String?
}

public struct TraceEvidenceCard: Decodable, Equatable, Sendable {
    public let title: String?
}

public final class TraceClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchTrace(conversationID: Int) async throws -> ConversationTrace {
        try await apiClient.get("desktop/traces/\(conversationID)")
    }
}
