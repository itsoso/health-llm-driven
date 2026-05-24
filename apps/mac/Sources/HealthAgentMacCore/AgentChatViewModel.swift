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

public struct AgentContextItem: Equatable, Identifiable, Sendable {
    public let sourceID: String
    public let sourceKind: String
    public let title: String
    public let summary: String
    public let payload: [String: String]

    public var id: String { "\(sourceKind):\(sourceID)" }

    public init(
        sourceID: String,
        sourceKind: String,
        title: String,
        summary: String,
        payload: [String: String] = [:]
    ) {
        self.sourceID = sourceID
        self.sourceKind = sourceKind
        self.title = title
        self.summary = summary
        self.payload = payload
    }
}

public enum AgentRunState: String, Equatable, Sendable {
    case idle
    case preparing
    case streaming
    case completed
    case partial
    case failed
}

public enum AgentToolActivityStatus: Equatable, Sendable {
    case running
    case succeeded
    case failed
}

public struct AgentToolActivity: Equatable, Identifiable, Sendable {
    public let id: UUID
    public let name: String
    public let status: AgentToolActivityStatus

    public var displayTitle: String {
        switch status {
        case .running:
            "\(name) running"
        case .succeeded:
            "\(name) succeeded"
        case .failed:
            "\(name) failed"
        }
    }

    public init(id: UUID = UUID(), name: String, status: AgentToolActivityStatus) {
        self.id = id
        self.name = name
        self.status = status
    }
}

@Observable
@MainActor
public final class AgentChatViewModel {
    public var isStreaming = false
    public var runState: AgentRunState = .idle
    public var selectedModelID: String?
    public var webSearchEnabled = false
    public var attachments: [FileIntakeItem] = []
    public var conversationID: Int?
    public var messages: [AgentChatMessage] = []
    public var errorMessage: String?
    public var lastCompletionStatus: String?
    public var lastModel: String?
    public var lastSourcesUsed: [String] = []
    public var lastPrompt: String?
    public var preparedDraft: String?
    public var contextItems: [AgentContextItem] = []
    public var toolActivities: [AgentToolActivity] = []

    @ObservationIgnored
    private let streamService: AgentStreamServicing?

    public var canRetry: Bool {
        !isStreaming && lastPrompt != nil && (runState == .failed || runState == .partial)
    }

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

    public func prepareDraft(_ text: String) {
        preparedDraft = text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func consumePreparedDraft() -> String? {
        defer { preparedDraft = nil }
        guard let preparedDraft, !preparedDraft.isEmpty else {
            return nil
        }
        return preparedDraft
    }

    public func canSubmit(_ text: String) -> Bool {
        !isStreaming && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func addAttachment(_ item: FileIntakeItem) {
        if !attachments.contains(where: { $0.sha256 == item.sha256 }) {
            attachments.append(item)
        }
    }

    public func removeAttachment(_ item: FileIntakeItem) {
        attachments.removeAll { $0.id == item.id }
    }

    public func addContextItem(_ item: AgentContextItem) {
        if !contextItems.contains(where: { $0.id == item.id }) {
            contextItems.append(item)
        }
    }

    public func removeContextItem(_ item: AgentContextItem) {
        contextItems.removeAll { $0.id == item.id }
    }

    public func clearContextItems() {
        contextItems = []
    }

    public func send(_ text: String) async {
        let message = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, let streamService else {
            return
        }

        errorMessage = nil
        toolActivities = []
        isStreaming = true
        runState = .preparing
        lastPrompt = message
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
                    runState = .streaming
                    messages[assistantIndex].content += content
                case .tool(let name, let success):
                    toolActivities.append(
                        AgentToolActivity(
                            name: name ?? "tool",
                            status: success.map { $0 ? .succeeded : .failed } ?? .running
                        )
                    )
                case .done(let id, _, let completionStatus, let model, let sourcesUsed):
                    conversationID = id ?? conversationID
                    lastCompletionStatus = completionStatus
                    lastModel = model
                    lastSourcesUsed = sourcesUsed
                    runState = .completed
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
        if errorMessage != nil {
            runState = messages[assistantIndex].content == errorMessage ? .failed : .partial
        } else if runState != .completed {
            runState = messages[assistantIndex].content.isEmpty ? .failed : .completed
        }
        if errorMessage == nil {
            attachments = []
        }
        isStreaming = false
    }

    public func retryLastMessage() async {
        guard canRetry, let lastPrompt else {
            return
        }
        await send(lastPrompt)
    }

    private func buildExtraContext() -> String? {
        var context: [String: Any] = [:]
        if let selectedModelID {
            context["model_id"] = selectedModelID
        }
        if webSearchEnabled {
            context["web_search_requested"] = true
        }
        if !attachments.isEmpty {
            context["attachments"] = attachments.map {
                [
                    "name": $0.name,
                    "source_kind": $0.sourceKind.rawValue,
                    "source_hash": $0.sha256,
                ]
            }
        }
        if !contextItems.isEmpty {
            context["context_items"] = contextItems.map {
                [
                    "source_id": $0.sourceID,
                    "source_kind": $0.sourceKind,
                    "title": $0.title,
                    "summary": $0.summary,
                    "payload": $0.payload
                ] as [String: Any]
            }
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
