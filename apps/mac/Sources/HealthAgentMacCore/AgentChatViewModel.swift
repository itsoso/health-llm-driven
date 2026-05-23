import Foundation
import Observation

public enum AgentChatRole: Equatable, Sendable {
    case user
    case assistant
}

public struct AgentChatMessage: Equatable, Identifiable, Sendable {
    public let id: UUID
    public let role: AgentChatRole
    public var content: String

    public init(id: UUID = UUID(), role: AgentChatRole, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }
}

@Observable
@MainActor
public final class AgentChatViewModel {
    public var isStreaming = false
    public var selectedModelID: String?
    public var webSearchEnabled = false
    public var conversationID: Int?
    public var messages: [AgentChatMessage] = []
    public var errorMessage: String?
    public var lastCompletionStatus: String?
    public var lastModel: String?
    public var lastSourcesUsed: [String] = []

    @ObservationIgnored
    private let streamService: AgentStreamServicing?

    public var isModelPickerEnabled: Bool {
        true
    }

    public init(selectedModelID: String? = nil, streamService: AgentStreamServicing? = nil) {
        self.selectedModelID = selectedModelID
        self.streamService = streamService
    }

    public func selectModel(_ id: String?) {
        selectedModelID = id
    }

    public func canSubmit(_ text: String) -> Bool {
        !isStreaming && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func send(_ text: String) async {
        let message = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, let streamService else {
            return
        }

        errorMessage = nil
        isStreaming = true
        messages.append(.init(role: .user, content: message))
        messages.append(.init(role: .assistant, content: ""))
        let assistantIndex = messages.index(before: messages.endIndex)

        do {
            for try await event in streamService.stream(
                message: message,
                conversationID: conversationID,
                extraContext: buildExtraContext()
            ) {
                switch event {
                case .start(let id):
                    conversationID = id ?? conversationID
                case .token(let content):
                    messages[assistantIndex].content += content
                case .tool:
                    break
                case .done(let id, _, let completionStatus, let model, let sourcesUsed):
                    conversationID = id ?? conversationID
                    lastCompletionStatus = completionStatus
                    lastModel = model
                    lastSourcesUsed = sourcesUsed
                case .error(let message):
                    errorMessage = message
                }
            }
        } catch {
            errorMessage = error.localizedDescription
        }

        if messages[assistantIndex].content.isEmpty, let errorMessage {
            messages[assistantIndex].content = errorMessage
        }
        isStreaming = false
    }

    private func buildExtraContext() -> String? {
        var context: [String: Any] = [:]
        if let selectedModelID {
            context["model_id"] = selectedModelID
        }
        if webSearchEnabled {
            context["web_search_requested"] = true
        }
        guard !context.isEmpty else {
            return nil
        }
        guard let data = try? JSONSerialization.data(withJSONObject: context) else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }
}
