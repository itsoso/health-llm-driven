import Foundation
import Observation

public enum AgentChatRole: String, Codable, Equatable, Sendable {
    case user
    case assistant
}

public struct AgentChatMessage: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public let role: AgentChatRole
    public var content: String

    public init(id: UUID = UUID(), role: AgentChatRole, content: String) {
        self.id = id
        self.role = role
        self.content = content
    }
}

public enum AgentProposedActionStatus: String, Codable, Equatable, Sendable {
    case pending
    case confirmed
    case dismissed
}

public struct AgentProposedAction: Codable, Equatable, Identifiable, Sendable {
    public let id: String
    public let messageID: UUID
    public let toolName: String
    public let title: String
    public let summary: String
    public let rawCommand: String
    public let parameters: [String: String]
    public var status: AgentProposedActionStatus

    public init(
        id: String,
        messageID: UUID,
        toolName: String,
        title: String,
        summary: String,
        rawCommand: String,
        parameters: [String: String],
        status: AgentProposedActionStatus = .pending
    ) {
        self.id = id
        self.messageID = messageID
        self.toolName = toolName
        self.title = title
        self.summary = summary
        self.rawCommand = rawCommand
        self.parameters = parameters
        self.status = status
    }

    public var contextItem: AgentContextItem {
        var payload = parameters
        payload["tool_name"] = toolName
        payload["raw_command"] = rawCommand
        payload["status"] = status.rawValue
        return AgentContextItem(
            sourceID: id,
            sourceKind: "agent_proposed_action",
            title: title,
            summary: summary,
            payload: payload
        )
    }
}

public enum AgentStructuredCommandParser {
    public static func proposedActions(in content: String, messageID: UUID) -> [AgentProposedAction] {
        structuredCommands(in: content).enumerated().map { index, command in
            AgentProposedAction(
                id: "\(messageID.uuidString):\(index)",
                messageID: messageID,
                toolName: command.toolName,
                title: title(for: command),
                summary: summary(for: command),
                rawCommand: command.rawCommand,
                parameters: command.parameters
            )
        }
    }

    public static func displayText(for content: String) -> String {
        var result = content
        for range in structuredCommands(in: content).map(\.range).reversed() {
            result.removeSubrange(range)
        }
        return result
            .components(separatedBy: .newlines)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && $0 != "```" && $0 != "```json" }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private struct StructuredCommand {
        let toolName: String
        let parameters: [String: String]
        let rawCommand: String
        let range: Range<String.Index>
    }

    private static func structuredCommands(in content: String) -> [StructuredCommand] {
        var commands: [StructuredCommand] = []
        var index = content.startIndex
        while index < content.endIndex {
            guard content[index] == "{" else {
                index = content.index(after: index)
                continue
            }
            guard let range = balancedJSONObjectRange(in: content, from: index) else {
                index = content.index(after: index)
                continue
            }
            let rawCommand = String(content[range]).trimmingCharacters(in: .whitespacesAndNewlines)
            if let command = parseCommand(rawCommand: rawCommand, range: range) {
                commands.append(command)
                index = range.upperBound
            } else {
                index = content.index(after: index)
            }
        }
        return commands
    }

    private static func balancedJSONObjectRange(in content: String, from start: String.Index) -> Range<String.Index>? {
        var index = start
        var depth = 0
        var isInString = false
        var isEscaped = false
        while index < content.endIndex {
            let character = content[index]
            if isInString {
                if isEscaped {
                    isEscaped = false
                } else if character == "\\" {
                    isEscaped = true
                } else if character == "\"" {
                    isInString = false
                }
            } else if character == "\"" {
                isInString = true
            } else if character == "{" {
                depth += 1
            } else if character == "}" {
                depth -= 1
                if depth == 0 {
                    return start..<content.index(after: index)
                }
            }
            index = content.index(after: index)
        }
        return nil
    }

    private static func parseCommand(rawCommand: String, range: Range<String.Index>) -> StructuredCommand? {
        guard let data = rawCommand.data(using: .utf8),
              let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let toolName = object["name"] as? String,
              !toolName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let parameters = object["parameters"] as? [String: Any] else {
            return nil
        }

        return StructuredCommand(
            toolName: toolName,
            parameters: parameters.mapValues(stringValue),
            rawCommand: rawCommand,
            range: range
        )
    }

    private static func stringValue(_ value: Any) -> String {
        switch value {
        case let value as String:
            return value
        case let value as Int:
            return "\(value)"
        case let value as Double:
            return value.formatted(.number.precision(.fractionLength(0...2)))
        case let value as Bool:
            return value ? "true" : "false"
        default:
            if JSONSerialization.isValidJSONObject([value]) {
                let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
                return data.flatMap { String(data: $0, encoding: .utf8) } ?? "\(value)"
            }
            return "\(value)"
        }
    }

    private static func title(for command: StructuredCommand) -> String {
        guard command.toolName == "health_manage" else {
            return "确认 \(command.toolName) 动作"
        }
        let action = command.parameters["action"] ?? "execute"
        let recordType = command.parameters["record_type"] ?? command.parameters["type"] ?? "record"
        let recordID = command.parameters["record_id"] ?? command.parameters["id"]
        let verb: String
        switch action {
        case "delete": verb = "删除"
        case "update": verb = "更新"
        case "create", "add": verb = "新增"
        default: verb = "执行"
        }
        let noun = recordTypeTitle(recordType)
        if let recordID, !recordID.isEmpty {
            return "\(verb)\(noun)记录 #\(recordID)"
        }
        return "\(verb)\(noun)记录"
    }

    private static func summary(for command: StructuredCommand) -> String {
        let parametersText = command.parameters
            .sorted { $0.key < $1.key }
            .map { "\($0.key)=\($0.value)" }
            .joined(separator: " · ")
        return "\(command.toolName) · \(parametersText)"
    }

    private static func recordTypeTitle(_ recordType: String) -> String {
        switch recordType {
        case "diet", "meal", "food": "饮食"
        case "water", "drink": "饮水"
        case "supplement", "supplements": "补剂"
        case "weight": "体重"
        case "blood_pressure", "bp": "血压"
        case "symptom", "symptoms": "症状"
        default: recordType
        }
    }
}

public struct AgentConversationSnapshot: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public let conversationID: Int?
    public let title: String
    public let messages: [AgentChatMessage]
    public let updatedAt: Date

    public init(
        id: UUID = UUID(),
        conversationID: Int? = nil,
        title: String,
        messages: [AgentChatMessage],
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.conversationID = conversationID
        self.title = title
        self.messages = messages
        self.updatedAt = updatedAt
    }
}

public protocol AgentConversationStoring: Sendable {
    func loadConversations() -> [AgentConversationSnapshot]
    func saveConversations(_ conversations: [AgentConversationSnapshot])
}

public final class UserDefaultsAgentConversationStore: AgentConversationStoring, @unchecked Sendable {
    private let defaults: UserDefaults
    private let key: String

    public init(defaults: UserDefaults = .standard, key: String = "agentConversationHistory") {
        self.defaults = defaults
        self.key = key
    }

    public func loadConversations() -> [AgentConversationSnapshot] {
        guard let data = defaults.data(forKey: key) else {
            return []
        }
        return (try? JSONDecoder().decode([AgentConversationSnapshot].self, from: data)) ?? []
    }

    public func saveConversations(_ conversations: [AgentConversationSnapshot]) {
        guard let data = try? JSONEncoder().encode(conversations) else {
            return
        }
        defaults.set(data, forKey: key)
    }
}

public struct AgentContextItem: Codable, Equatable, Identifiable, Sendable {
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

public struct AgentContextBundle: Codable, Equatable, Identifiable, Sendable {
    public let id: UUID
    public let name: String
    public let items: [AgentContextItem]
    public let createdAt: Date

    public var itemCount: Int { items.count }

    public init(id: UUID = UUID(), name: String, items: [AgentContextItem], createdAt: Date = Date()) {
        self.id = id
        self.name = name
        self.items = items
        self.createdAt = createdAt
    }
}

public protocol AgentContextBundleStoring: Sendable {
    func loadContextBundles() -> [AgentContextBundle]
    func saveContextBundles(_ bundles: [AgentContextBundle])
}

public final class UserDefaultsAgentContextBundleStore: AgentContextBundleStoring, @unchecked Sendable {
    private let defaults: UserDefaults
    private let key: String

    public init(defaults: UserDefaults = .standard, key: String = "agentContextBundles") {
        self.defaults = defaults
        self.key = key
    }

    public func loadContextBundles() -> [AgentContextBundle] {
        guard let data = defaults.data(forKey: key) else {
            return []
        }
        return (try? JSONDecoder().decode([AgentContextBundle].self, from: data)) ?? []
    }

    public func saveContextBundles(_ bundles: [AgentContextBundle]) {
        guard let data = try? JSONEncoder().encode(bundles) else {
            return
        }
        defaults.set(data, forKey: key)
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
    public var savedContextBundles: [AgentContextBundle] = []
    public var conversationHistory: [AgentConversationSnapshot] = []
    public var toolActivities: [AgentToolActivity] = []
    public var proposedActions: [AgentProposedAction] = []

    @ObservationIgnored
    private let streamService: AgentStreamServicing?
    @ObservationIgnored
    private let contextBundleStore: AgentContextBundleStoring?
    @ObservationIgnored
    private let conversationStore: AgentConversationStoring?
    @ObservationIgnored
    private var currentConversationSnapshotID: UUID?

    public var canRetry: Bool {
        !isStreaming && lastPrompt != nil && (runState == .failed || runState == .partial)
    }

    public var isModelPickerEnabled: Bool {
        true
    }

    public var currentConversationID: UUID? {
        currentConversationSnapshotID
    }

    public init(
        selectedModelID: String? = nil,
        streamService: AgentStreamServicing? = nil,
        contextBundleStore: AgentContextBundleStoring? = nil,
        conversationStore: AgentConversationStoring? = nil
    ) {
        self.selectedModelID = selectedModelID
        self.streamService = streamService
        self.contextBundleStore = contextBundleStore
        self.conversationStore = conversationStore
        self.savedContextBundles = contextBundleStore?.loadContextBundles() ?? []
        self.conversationHistory = conversationStore?.loadConversations() ?? []
        if let latest = conversationHistory.first {
            self.currentConversationSnapshotID = latest.id
            self.conversationID = latest.conversationID
            self.messages = latest.messages
        }
        rebuildProposedActions()
    }

    public func selectModel(_ id: String?) {
        selectedModelID = id
    }

    public func prepareDraft(_ text: String) {
        preparedDraft = text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    public func prepareDraftForNewConversation(_ text: String, contextItem: AgentContextItem? = nil) {
        prepareDraftForNewConversation(text, contextItems: contextItem.map { [$0] } ?? [])
    }

    public func prepareDraftForNewConversation(_ text: String, contextItems: [AgentContextItem]) {
        startNewConversation()
        for contextItem in contextItems {
            addContextItem(contextItem)
        }
        prepareDraft(Self.visibleDraft(text: text, contextItems: self.contextItems))
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

    @discardableResult
    public func saveCurrentContextBundle(named name: String) -> AgentContextBundle {
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let bundle = AgentContextBundle(
            name: trimmedName.isEmpty ? "Context Bundle \(savedContextBundles.count + 1)" : trimmedName,
            items: contextItems
        )
        savedContextBundles.removeAll { $0.name == bundle.name }
        savedContextBundles.insert(bundle, at: 0)
        persistContextBundles()
        return bundle
    }

    public func applyContextBundle(_ bundle: AgentContextBundle) {
        for item in bundle.items {
            addContextItem(item)
        }
    }

    public func deleteContextBundle(_ bundle: AgentContextBundle) {
        savedContextBundles.removeAll { $0.id == bundle.id }
        persistContextBundles()
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
        rebuildProposedActions()
        if errorMessage == nil {
            attachments = []
        }
        persistCurrentConversation()
        isStreaming = false
    }

    public func startNewConversation() {
        messages = []
        conversationID = nil
        errorMessage = nil
        lastCompletionStatus = nil
        lastModel = nil
        lastSourcesUsed = []
        lastPrompt = nil
        toolActivities = []
        currentConversationSnapshotID = nil
        proposedActions = []
        attachments = []
        contextItems = []
        preparedDraft = nil
    }

    public func loadConversation(_ conversation: AgentConversationSnapshot) {
        currentConversationSnapshotID = conversation.id
        conversationID = conversation.conversationID
        messages = conversation.messages
        errorMessage = nil
        lastCompletionStatus = nil
        lastModel = nil
        lastSourcesUsed = []
        toolActivities = []
        lastPrompt = conversation.messages.last(where: { $0.role == .user })?.content
        rebuildProposedActions()
    }

    public func deleteConversation(_ conversation: AgentConversationSnapshot) {
        conversationHistory.removeAll { $0.id == conversation.id }
        conversationStore?.saveConversations(conversationHistory)
        if currentConversationSnapshotID == conversation.id {
            startNewConversation()
        }
    }

    public func retryLastMessage() async {
        guard canRetry, let lastPrompt else {
            return
        }
        await send(lastPrompt)
    }

    public func displayContent(for message: AgentChatMessage) -> String {
        guard message.role == .assistant else {
            return message.content
        }
        let displayText = AgentStructuredCommandParser.displayText(for: message.content)
        return displayText.isEmpty && !proposedActions(for: message).isEmpty
            ? "已生成需要确认的结构化动作。"
            : displayText
    }

    public func proposedActions(for message: AgentChatMessage) -> [AgentProposedAction] {
        proposedActions.filter { $0.messageID == message.id && $0.status != .dismissed }
    }

    public func dismissProposedAction(_ action: AgentProposedAction) {
        updateProposedAction(action, status: .dismissed)
    }

    public func confirmProposedAction(_ action: AgentProposedAction) async {
        guard !isStreaming else {
            return
        }
        updateProposedAction(action, status: .confirmed)
        var confirmedAction = action
        confirmedAction.status = .confirmed
        addContextItem(confirmedAction.contextItem)
        await send("请执行我刚确认的健康管理动作。请使用上下文里的 agent_proposed_action；执行成功或失败都用自然语言说明，不要再次只输出 JSON。")
    }

    private func persistContextBundles() {
        contextBundleStore?.saveContextBundles(savedContextBundles)
    }

    private func persistCurrentConversation() {
        guard !messages.isEmpty else {
            return
        }
        let snapshotID = currentConversationSnapshotID ?? UUID()
        currentConversationSnapshotID = snapshotID
        let snapshot = AgentConversationSnapshot(
            id: snapshotID,
            conversationID: conversationID,
            title: conversationTitle(from: messages),
            messages: messages,
            updatedAt: Date()
        )
        conversationHistory.removeAll { $0.id == snapshot.id }
        conversationHistory.insert(snapshot, at: 0)
        conversationHistory = Array(conversationHistory.prefix(30))
        conversationStore?.saveConversations(conversationHistory)
    }

    private func rebuildProposedActions() {
        let existingStatuses = Dictionary(uniqueKeysWithValues: proposedActions.map { ($0.id, $0.status) })
        proposedActions = messages
            .filter { $0.role == .assistant }
            .flatMap { message in
                AgentStructuredCommandParser.proposedActions(in: message.content, messageID: message.id)
            }
            .map { action in
                var mutableAction = action
                if let status = existingStatuses[action.id] {
                    mutableAction.status = status
                }
                return mutableAction
            }
    }

    private func updateProposedAction(_ action: AgentProposedAction, status: AgentProposedActionStatus) {
        guard let index = proposedActions.firstIndex(where: { $0.id == action.id }) else {
            return
        }
        proposedActions[index].status = status
    }

    private func conversationTitle(from messages: [AgentChatMessage]) -> String {
        let firstUserMessage = messages.first(where: { $0.role == .user })?.content ?? "New Analysis"
        let trimmed = firstUserMessage.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.count <= 28 {
            return trimmed.isEmpty ? "New Analysis" : trimmed
        }
        return "\(trimmed.prefix(28))…"
    }

    private func buildExtraContext() -> String? {
        var context: [String: Any] = [
            "client": "mac",
            "response_format": "markdown",
            "desktop_markdown_response_instruction": Self.desktopMarkdownResponseInstruction,
        ]
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
        guard let data = try? JSONSerialization.data(withJSONObject: context) else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    private static let desktopMarkdownResponseInstruction = """
    请用适合桌面阅读的中文 Markdown 回复：先给 2-3 条关键结论；再用二级/三级标题分段；比较或分项判断优先用表格；行动建议用编号列表；关键数值和结论加粗。每段最多 3 行，标题、段落、列表之间必须留空行。不要输出密集长段落，不要用长破折号把所有判断串成一段。最后必须包含「不确定性边界」和「下一步」；不要把基因风险当诊断，不要直接给用药决定。若需要执行结构化动作，自然语言说明后再给可确认动作。
    """

    private static func visibleDraft(text: String, contextItems: [AgentContextItem]) -> String {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !contextItems.isEmpty else {
            return trimmed
        }

        let contextLines = contextItems.enumerated().map { index, item in
            [
                "\(index + 1). \(item.title)",
                "   - 类型：\(item.sourceKind)",
                "   - 摘要：\(item.summary)",
                payloadSummary(for: item).map { "   - 关键字段：\($0)" }
            ].compactMap { $0 }.joined(separator: "\n")
        }.joined(separator: "\n")

        return """
        \(trimmed)

        ### 当前上下文
        \(contextLines)
        """
    }

    private static func payloadSummary(for item: AgentContextItem) -> String? {
        let pairs = item.payload
            .filter { !$0.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
            .sorted { $0.key < $1.key }
            .prefix(6)
            .map { "\($0.key)=\($0.value)" }
        guard !pairs.isEmpty else {
            return nil
        }
        return pairs.joined(separator: "; ")
    }
}
