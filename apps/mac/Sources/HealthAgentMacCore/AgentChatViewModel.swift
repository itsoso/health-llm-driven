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
    /// Creation time for this visible chat message. Backend history carries
    /// `created_at`; locally sent messages fill Date() so the transcript can show
    /// WeChat-style message time before the conversation is reloaded.
    public var createdAt: Date?
    /// Public image URLs attached to this historical message. Mobile/web persist
    /// uploaded chat images in the backend; Mac uses these URLs when replaying
    /// the same conversation from `/agent/conversations/{id}`.
    public var remoteImageURLs: [String]
    /// Dynamic UI card descriptor carried by this message. The protocol mirrors
    /// web/mobile: `cardType` selects a renderer, `cardData` is untrusted JSON
    /// that must be escaped before entering the transcript DOM.
    public var cardType: String?
    public var cardRender: AgentDynamicCardRenderDescriptor?
    public var cardData: AgentDynamicCardValue?
    public var cardActions: [AgentDynamicCardActionDescriptor]

    // MARK: 每条消息级 meta(助手回复 footer 用;流式 done 回填)
    /// 实际生成本条回复的模型名(后端 done.model)。
    public var model: String?
    /// 用户本轮选择的模型(后端 done.selected_model;可能与工具模型不同)。
    public var selectedModel: String?
    /// 最终生成用户可见答案的模型(后端 done.answer_model)。
    public var answerModel: String?
    /// 实际产生结构化 tool_calls 的模型列表(后端 done.tool_models)。
    public var toolModels: [String]
    /// 选定模型转向工具模型/fallback provider 的原因(后端 done.fallback_reasons)。
    public var fallbackReasons: [String]
    /// 端到端耗时(毫秒,后端 done.elapsed_ms)。
    public var elapsedMs: Int?
    /// LLM 调用轮数(后端 done.llm_rounds);>1 才有展示意义。
    public var llmRounds: Int?
    /// 本条回复内每次 LLM 调用的 token / 成本摘要(后端 done.llm_usage / message.meta.llm_usage)。
    public var llmUsage: LLMUsageProfile?
    /// 本次引用的数据源标签(后端 done.sources_used)。
    public var sourcesUsed: [String]
    /// 本次调用的 Skill / 工具名(后端 done.tools_used;未上线前为空)。
    public var toolsUsed: [String]
    /// 完成状态(后端 done.completion_status,如 "complete" / "partial")。
    public var completionStatus: String?
    /// 每回复级阶段耗时(后端 done.perf,持久化在 message.meta.perf)。用于渲染延迟瀑布图。
    /// 老消息缺失 → nil → footer 行为不变(完整向后兼容)。
    public var perf: MessagePerf?
    /// Backend persisted thinking trace for this assistant message. Older cache
    /// rows omit it; decode as empty so transcript replay stays compatible.
    public var thinkingSteps: [String]

    /// 是否有任何可展示的 meta(footer 是否需要渲染)。
    public var hasMeta: Bool {
        model != nil || elapsedMs != nil || (llmRounds ?? 0) > 1
            || selectedModel != nil || answerModel != nil
            || !toolModels.isEmpty || !fallbackReasons.isEmpty
            || !sourcesUsed.isEmpty || !toolsUsed.isEmpty
            || llmUsage != nil
            || (perf?.isRenderable ?? false)
    }

    public init(
        id: UUID = UUID(),
        role: AgentChatRole,
        content: String,
        createdAt: Date? = nil,
        model: String? = nil,
        selectedModel: String? = nil,
        answerModel: String? = nil,
        toolModels: [String] = [],
        fallbackReasons: [String] = [],
        elapsedMs: Int? = nil,
        llmRounds: Int? = nil,
        llmUsage: LLMUsageProfile? = nil,
        sourcesUsed: [String] = [],
        toolsUsed: [String] = [],
        completionStatus: String? = nil,
        perf: MessagePerf? = nil,
        thinkingSteps: [String] = [],
        cardType: String? = nil,
        cardRender: AgentDynamicCardRenderDescriptor? = nil,
        cardData: AgentDynamicCardValue? = nil,
        cardActions: [AgentDynamicCardActionDescriptor] = [],
        remoteImageURLs: [String] = []
    ) {
        self.id = id
        self.role = role
        self.content = content
        self.createdAt = createdAt
        self.remoteImageURLs = remoteImageURLs
        self.cardType = cardType
        self.cardRender = cardRender
        self.cardData = cardData
        self.cardActions = cardActions
        self.model = model
        self.selectedModel = selectedModel
        self.answerModel = answerModel
        self.toolModels = toolModels
        self.fallbackReasons = fallbackReasons
        self.elapsedMs = elapsedMs
        self.llmRounds = llmRounds
        self.llmUsage = llmUsage
        self.sourcesUsed = sourcesUsed
        self.toolsUsed = toolsUsed
        self.completionStatus = completionStatus
        self.perf = perf
        self.thinkingSteps = thinkingSteps
    }

    // 显式 Codable:历史快照(老版本无这些字段)用 decodeIfPresent 容错;数组缺失 → 空。
    private enum CodingKeys: String, CodingKey {
        case id, role, content, createdAt, remoteImageURLs, model, selectedModel, answerModel, toolModels, fallbackReasons, elapsedMs, llmRounds, llmUsage, sourcesUsed, toolsUsed, completionStatus, perf, thinkingSteps, cardType, cardRender, cardData, cardActions
        case cardTypeSnake = "card_type"
        case cardRenderSnake = "card_render"
        case cardDataSnake = "card_data"
        case cardActionsSnake = "card_actions"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(UUID.self, forKey: .id)
        self.role = try c.decode(AgentChatRole.self, forKey: .role)
        self.content = try c.decode(String.self, forKey: .content)
        self.createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt)
        self.remoteImageURLs = try c.decodeIfPresent([String].self, forKey: .remoteImageURLs) ?? []
        self.model = try c.decodeIfPresent(String.self, forKey: .model)
        self.selectedModel = try c.decodeIfPresent(String.self, forKey: .selectedModel)
        self.answerModel = try c.decodeIfPresent(String.self, forKey: .answerModel)
        self.toolModels = try c.decodeIfPresent([String].self, forKey: .toolModels) ?? []
        self.fallbackReasons = try c.decodeIfPresent([String].self, forKey: .fallbackReasons) ?? []
        self.elapsedMs = try c.decodeIfPresent(Int.self, forKey: .elapsedMs)
        self.llmRounds = try c.decodeIfPresent(Int.self, forKey: .llmRounds)
        self.llmUsage = try c.decodeIfPresent(LLMUsageProfile.self, forKey: .llmUsage)
        self.sourcesUsed = try c.decodeIfPresent([String].self, forKey: .sourcesUsed) ?? []
        self.toolsUsed = try c.decodeIfPresent([String].self, forKey: .toolsUsed) ?? []
        self.completionStatus = try c.decodeIfPresent(String.self, forKey: .completionStatus)
        self.perf = try c.decodeIfPresent(MessagePerf.self, forKey: .perf)
        self.thinkingSteps = try c.decodeIfPresent([String].self, forKey: .thinkingSteps) ?? []
        self.cardType = try c.decodeIfPresent(String.self, forKey: .cardType)
            ?? c.decodeIfPresent(String.self, forKey: .cardTypeSnake)
        self.cardRender = try c.decodeIfPresent(AgentDynamicCardRenderDescriptor.self, forKey: .cardRender)
            ?? c.decodeIfPresent(AgentDynamicCardRenderDescriptor.self, forKey: .cardRenderSnake)
        self.cardData = try c.decodeIfPresent(AgentDynamicCardValue.self, forKey: .cardData)
            ?? c.decodeIfPresent(AgentDynamicCardValue.self, forKey: .cardDataSnake)
        self.cardActions = try c.decodeIfPresent([AgentDynamicCardActionDescriptor].self, forKey: .cardActions)
            ?? c.decodeIfPresent([AgentDynamicCardActionDescriptor].self, forKey: .cardActionsSnake)
            ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(role, forKey: .role)
        try c.encode(content, forKey: .content)
        try c.encodeIfPresent(createdAt, forKey: .createdAt)
        try c.encode(remoteImageURLs, forKey: .remoteImageURLs)
        try c.encodeIfPresent(model, forKey: .model)
        try c.encodeIfPresent(selectedModel, forKey: .selectedModel)
        try c.encodeIfPresent(answerModel, forKey: .answerModel)
        try c.encode(toolModels, forKey: .toolModels)
        try c.encode(fallbackReasons, forKey: .fallbackReasons)
        try c.encodeIfPresent(elapsedMs, forKey: .elapsedMs)
        try c.encodeIfPresent(llmRounds, forKey: .llmRounds)
        try c.encodeIfPresent(llmUsage, forKey: .llmUsage)
        try c.encode(sourcesUsed, forKey: .sourcesUsed)
        try c.encode(toolsUsed, forKey: .toolsUsed)
        try c.encodeIfPresent(completionStatus, forKey: .completionStatus)
        try c.encodeIfPresent(perf, forKey: .perf)
        try c.encode(thinkingSteps, forKey: .thinkingSteps)
        try c.encodeIfPresent(cardType, forKey: .cardType)
        try c.encodeIfPresent(cardRender, forKey: .cardRender)
        try c.encodeIfPresent(cardData, forKey: .cardData)
        try c.encode(cardActions, forKey: .cardActions)
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

    // displayText 是 content 的纯函数,但内部对整条消息做 O(n) 字符扫描(找内嵌 JSON
    // 命令)。它在每个气泡的 body 里被调(messageContent → displayContent),滚动时
    // LazyVStack 每挂一行就重扫一遍整条长消息 → 掉帧。按 content 全局缓存,滚动 O(1) 命中。
    // NSCache 线程安全;Swift 6 用 nonisolated(unsafe)(同 MarkdownMessageText 的缓存)。
    private final class StringBox { let value: String; init(_ v: String) { self.value = v } }
    nonisolated(unsafe) private static let displayTextCache: NSCache<NSString, StringBox> = {
        let c = NSCache<NSString, StringBox>(); c.countLimit = 256; return c
    }()

    public static func displayText(for content: String) -> String {
        let key = content as NSString
        if let hit = displayTextCache.object(forKey: key) { return hit.value }
        var result = content
        for range in structuredCommands(in: content).map(\.range).reversed() {
            result.removeSubrange(range)
        }
        // 剥离 [claim:xxx] 证据引用标记(内部 claim_id,非用户可见;证据通过
        // sources_used / cards 单独展示)。连同前导空格一起去掉,避免留下空隙。
        result = result.replacingOccurrences(
            of: "\\s*\\[claim:[^\\]]*\\]",
            with: "",
            options: .regularExpression
        )
        // GenUI(契约 v0):```reva-ui 围栏块必须**整段原样保留**——否则下面的逐行清洗会把
        // 闭合 ``` 行当成 legacy 命令围栏删掉,导致 RevaUIBlock.split 把它判为「未闭合」而退回
        // 纯文本,图表占位永远生不出来(线上首个 reva-ui 块只渲染成裸文本的根因)。
        // 用同一个 split 作为围栏识别的唯一真源:reva-ui 段照搬,普通段才走清洗。
        let segments = RevaUIBlock.split(from: result)
        let hasRevaUI = segments.contains { segment in
            if case .revaUI = segment { return true }
            return false
        }
        let markdownJoined = segments.compactMap { segment -> String? in
            if case .markdown(let text) = segment { return text }
            return nil
        }.joined(separator: "\n")
        let normalizedResult = result.replacingOccurrences(of: "\r\n", with: "\n")
        let strippedMenuShare = !hasRevaUI && markdownJoined != normalizedResult
        let out: String
        if hasRevaUI || strippedMenuShare {
            var pieces: [String] = []
            for segment in segments {
                switch segment {
                case .revaUI(let rawJSON):
                    // 原样重建闭合围栏(split 切掉了围栏标记本身,这里补回)。
                    pieces.append("```reva-ui\n" + rawJSON + "\n```")
                case .markdown(let text):
                    let cleaned = cleanDisplayLines(RevaUIBlock.stripInlineMenuShareRemnants(text))
                    if !cleaned.isEmpty { pieces.append(cleaned) }
                }
            }
            out = pieces.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        } else {
            out = cleanDisplayLines(RevaUIBlock.stripInlineMenuShareRemnants(result))
        }
        displayTextCache.setObject(StringBox(out), forKey: key)
        return out
    }

    /// 逐行清洗普通文本段:trim 每行、丢空行、剥 legacy `` ``` `` / ``` ```json ``` 围栏标记。
    /// **不得**对 reva-ui 围栏内容调用——那会删掉闭合 ``` 行毁掉图表块(见 displayText)。
    private static func cleanDisplayLines(_ text: String) -> String {
        text
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

    /// Returns a copy carrying `newMessages`, keeping id / conversationID / title /
    /// updatedAt. Used when merging the message-less backend list with cached or
    /// freshly-loaded transcripts.
    public func replacingMessages(_ newMessages: [AgentChatMessage]) -> AgentConversationSnapshot {
        AgentConversationSnapshot(
            id: id,
            conversationID: conversationID,
            title: title,
            messages: newMessages,
            updatedAt: updatedAt
        )
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

public struct LabReportImportContext: Equatable, Sendable {
    public let fileName: String
    public let sourceHash: String
    public let sourceKind: FileSourceKind
    public let result: LabUploadResult

    public init(fileName: String, sourceHash: String, sourceKind: FileSourceKind, result: LabUploadResult) {
        self.fileName = fileName
        self.sourceHash = sourceHash
        self.sourceKind = sourceKind
        self.result = result
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
    public let arguments: String?
    public let preview: String?
    public let result: String?
    public let round: Int?

    public var resultText: String? {
        result ?? preview
    }

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

    public init(
        id: UUID = UUID(),
        name: String,
        status: AgentToolActivityStatus,
        arguments: String? = nil,
        preview: String? = nil,
        result: String? = nil,
        round: Int? = nil
    ) {
        self.id = id
        self.name = name
        self.status = status
        self.arguments = arguments
        self.preview = preview
        self.result = result
        self.round = round
    }
}

/// One visible step in the accumulating "thinking process" trace shown while 小巴
/// streams. Unlike `liveStatusText` (a single line that each new `status` event
/// overwrites), steps accumulate so the user sees the *sequence* of what the
/// agent did. The label is stored as a localization **key** + optional detail
/// (same shape as `AgentChatViewModel.statusText`), so the View resolves it
/// through `appText`/`L10n` and never has raw zh baked into the model.
public enum ThinkingStepState: Equatable, Sendable {
    case running
    case done
}

public struct ThinkingStep: Equatable, Identifiable, Sendable {
    public let id: UUID
    /// L10n key OR, for the `thinking` server-phrase / `tool` detail path, a
    /// verbatim string the View renders as-is (L10n pass-through).
    public let labelKey: String
    /// Chinese tool label spliced into `labelKey` when it is the `"Working: %@…"`
    /// format string; nil for plain (non-format) keys.
    public let labelDetail: String?
    public var state: ThinkingStepState

    public init(
        id: UUID = UUID(),
        labelKey: String,
        labelDetail: String? = nil,
        state: ThinkingStepState = .running
    ) {
        self.id = id
        self.labelKey = labelKey
        self.labelDetail = labelDetail
        self.state = state
    }

    /// Two steps represent "the same activity" when their resolved label pair
    /// matches — used to suppress consecutive duplicate `status` events so the
    /// trace doesn't flicker the same line repeatedly.
    func hasSameLabel(as other: ThinkingStep) -> Bool {
        labelKey == other.labelKey && labelDetail == other.labelDetail
    }
}

public enum AgentTurnRunStatus: Equatable, Sendable {
    case queued
    case streaming
    case completed
    case failed(String)
    case cancelled
}

public struct AgentTurnRun: Identifiable, Equatable, Sendable {
    public let id: UUID
    public let clientTurnID: String
    public let userMessageID: UUID
    public let assistantMessageID: UUID
    public var status: AgentTurnRunStatus
    public var queuedAt: Date
    public var startedAt: Date?

    public init(
        id: UUID = UUID(),
        clientTurnID: String = UUID().uuidString,
        userMessageID: UUID,
        assistantMessageID: UUID,
        status: AgentTurnRunStatus = .queued,
        queuedAt: Date = Date(),
        startedAt: Date? = nil
    ) {
        self.id = id
        self.clientTurnID = clientTurnID
        self.userMessageID = userMessageID
        self.assistantMessageID = assistantMessageID
        self.status = status
        self.queuedAt = queuedAt
        self.startedAt = startedAt
    }
}

private struct PendingAgentTurn: Sendable {
    let prompt: String
    let runID: UUID
    let userMessageID: UUID
    let assistantMessageID: UUID
}

@Observable
@MainActor
public final class AgentChatViewModel {
    public static let maxLiveThinkingSteps = 8

    public var isStreaming = false
    public private(set) var queuedTurnCount = 0
    public private(set) var turnRuns: [AgentTurnRun] = []
    public var streamingAssistantMessageID: UUID?
    private var streamingTask: Task<Void, Never>?
    @ObservationIgnored private var pendingTurns: [PendingAgentTurn] = []
    public var runState: AgentRunState = .idle
    public var selectedModelID: String?
    public var webSearchEnabled = false
    /// 「默认 3 个」模式 → 后端多模型综合分析 (商用三强 panel)。
    public var multiModel = false
    public var attachments: [FileIntakeItem] = []
    public var labReportImports: [LabReportImportContext] = []
    public var conversationID: Int?
    public var messages: [AgentChatMessage] = []
    public var errorMessage: String?
    public var lastCompletionStatus: String?
    public var lastModel: String?
    public var lastSourcesUsed: [String] = []
    /// 流式中的中途 perf 提示(perf_pre_llm);done 到达后清空。目前仅暂存,供未来
    /// 「组装中…」实时提示消费——主瀑布图始终从最终 message.perf 渲染。
    public var livePreLLMPerf: MessagePerf?
    /// 后端真实阶段(`status` 事件)映射出的实时提示 **L10n key**(vision/thinking/
    /// tool/synthesis)。View 用 `appText` 解析成本地化文案。首 token / done / error
    /// 到达即清空 → View 退回时间轮换兜底。nil = 没有真实阶段信号(老后端 / 已进入正文流)。
    /// tool 阶段带 detail 时,key 为格式串 `"Working: %@…"`,由 View 用 `liveStatusDetail`
    /// 插值(detail 是后端给的中文工具名,必须原样显示)。
    public var liveStatusText: String?
    /// tool 阶段的中文工具名(后端 `status.detail`);仅当 `liveStatusText` 是格式串时有值。
    public var liveStatusDetail: String?
    public var lastPrompt: String?
    public var preparedDraft: String?
    public var contextItems: [AgentContextItem] = []
    public var savedContextBundles: [AgentContextBundle] = []
    public var conversationHistory: [AgentConversationSnapshot] = []
    public var toolActivities: [AgentToolActivity] = []
    /// Accumulating "thinking process" trace (vision/thinking/tool/synthesis steps
    /// from the backend `status` SSE stream). Unlike `liveStatusText` — a single
    /// line each new status overwrites — steps are kept so the user sees the full
    /// sequence. Preserved through the first token (NOT wiped like `liveStatusText`)
    /// so the trace stays visible during content streaming; cleared only when a new
    /// turn starts (`send()` / `startNewConversation()` / `cancelStreaming()`).
    public var thinkingSteps: [ThinkingStep] = []
    public var liveThinkingSteps: [String] {
        get { thinkingSteps.map(Self.visibleThinkingStepText) }
        set {
            thinkingSteps = newValue.suffix(Self.maxLiveThinkingSteps).map {
                ThinkingStep(labelKey: $0, labelDetail: nil, state: .done)
            }
        }
    }
    public var proposedActions: [AgentProposedAction] = []

    // MARK: transcript 渲染缓存(按键热点)
    // composer 的 draft 是 View 的 @State,每次按键都重算 AgentChatView.body。旧实现里
    // `renderedMessages` 是计算属性,会对每条助手消息重跑一次 markdown→HTML 解析(O(n) 每键),
    // 一旦对话里有长回复,打字就卡。这里按内容(messages/isStreaming/proposedActions)做缓存:
    // 内容没变就直接返回上次结果,打字命中缓存、零重渲。@ObservationIgnored 确保写缓存不触发
    // Observation 失效(否则会在 body 求值里改观察态 → 重渲循环)。
    @ObservationIgnored private var _transcriptCache: [ChatTranscriptHTML.RenderedMessage] = []
    @ObservationIgnored private var _transcriptCacheMessages: [AgentChatMessage] = []
    @ObservationIgnored private var _transcriptCacheStreaming = false
    @ObservationIgnored private var _transcriptCacheStreamingAssistantID: UUID?
    @ObservationIgnored private var _transcriptCacheProposed: [AgentProposedAction] = []
    @ObservationIgnored private var _transcriptCacheThinkingSteps: [ThinkingStep] = []
    @ObservationIgnored private var _transcriptCacheLanguage = ""
    @ObservationIgnored private var _transcriptCacheAIGCResultURLs: [String: String] = [:]
    /// Per-message snapshot of the finished thinking trace, so a completed answer
    /// keeps a collapsible, reviewable "思考过程" (mobile-style) instead of it
    /// vanishing when the answer streams in. Keyed by assistant message id; session
    /// -only (backend doesn't persist it, so replayed old conversations simply have
    /// none). Not observed — set at turn completion, coincident with a `messages`
    /// change that already invalidates the transcript cache.
    @ObservationIgnored private var _completedThinkingSteps: [UUID: [ThinkingStep]] = [:]

    /// Set when the backend history list/detail fetch fell back to the local
    /// cache (offline / 401 / server error). The UI surfaces this so a stale
    /// local view is never silently presented as authoritative. nil = backend
    /// data is current.
    public var historyNotice: String?
    /// True while a backend history list or detail fetch is in flight.
    public var isLoadingHistory = false
    /// Monotonic request id prevents a slower earlier search response from
    /// replacing the result of the user's latest query.
    @ObservationIgnored private var historyRequestSequence = 0
    /// A filtered list must never be written back as the complete offline cache.
    @ObservationIgnored private var activeHistorySearch: String?

    @ObservationIgnored
    private let streamService: AgentStreamServicing?
    @ObservationIgnored
    private let contextBundleStore: AgentContextBundleStoring?
    @ObservationIgnored
    private let conversationStore: AgentConversationStoring?
    @ObservationIgnored
    private let remoteSource: AgentConversationRemoteSourcing?
    @ObservationIgnored
    private let labUploadService: LabUploadServicing?
    @ObservationIgnored
    private let aigcMediaClient: AIGCMediaJobLoading?
    @ObservationIgnored
    private let dietDraftClient: DietDraftConfirming?
    @ObservationIgnored
    private let medicationBatchClient: MedicationBatchWriteIntentActing?
    /// One server-bound intent is one decision group. Confirm and dismiss are
    /// sibling controls and must never be in flight at the same time.
    @ObservationIgnored
    private var medicationBatchIntentsInFlight: Set<Int> = []
    @ObservationIgnored
    private var aigcRefreshTasks: [String: Task<Void, Never>] = [:]
    /// Owner-scoped signed result URLs stay in memory only. Conversation cards
    /// persist media metadata and re-fetch a fresh URL from the job endpoint.
    @ObservationIgnored
    private var aigcResultURLs: [String: String] = [:]
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
        conversationStore: AgentConversationStoring? = nil,
        remoteSource: AgentConversationRemoteSourcing? = nil,
        labUploadService: LabUploadServicing? = nil,
        aigcMediaClient: AIGCMediaJobLoading? = nil,
        dietDraftClient: DietDraftConfirming? = nil,
        medicationBatchClient: MedicationBatchWriteIntentActing? = nil
    ) {
        self.selectedModelID = selectedModelID
        self.streamService = streamService
        self.contextBundleStore = contextBundleStore
        self.conversationStore = conversationStore
        self.remoteSource = remoteSource
        self.labUploadService = labUploadService
        self.aigcMediaClient = aigcMediaClient
        self.dietDraftClient = dietDraftClient
        self.medicationBatchClient = medicationBatchClient
        self.savedContextBundles = contextBundleStore?.loadContextBundles() ?? []
        // Seed from the local cache so the list isn't empty before the first
        // backend fetch returns; `refreshConversationHistory()` replaces it.
        let cachedConversations = conversationStore?.loadConversations() ?? []
        self.conversationHistory = cachedConversations.map {
            $0.replacingMessages(Self.redactedMessagesForLocalPersistence($0.messages))
        }
        if conversationHistory != cachedConversations {
            conversationStore?.saveConversations(conversationHistory)
        }
        if let latest = conversationHistory.first {
            self.currentConversationSnapshotID = latest.id
            self.conversationID = latest.conversationID
            self.messages = latest.messages
            rehydrateLastAssistantMeta()
        }
        rebuildProposedActions()
    }

    public func selectModel(_ id: String?) {
        selectedModelID = id.map(AgentModelCatalog.canonicalID)
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
        !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    public func addAttachment(_ item: FileIntakeItem) {
        if !attachments.contains(where: { $0.sha256 == item.sha256 }) {
            attachments.append(item)
        }
    }

    public func buildChatImages(excludingImportedHashes importedHashes: Set<String> = []) -> [AgentChatImage] {
        attachments.compactMap { item in
            guard item.sourceKind == .image, !importedHashes.contains(item.sha256) else {
                return nil
            }
            guard let data = try? Data(contentsOf: item.url) else {
                return nil
            }
            return AgentChatImage(base64: data.base64EncodedString(), type: Self.chatImageType(for: item.url))
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

    /// Fire-and-forget entry point for the UI. When a turn is already streaming,
    /// the new prompt is kept visible as a queued turn and runs FIFO after the
    /// current stream finishes.
    public func submit(_ text: String) {
        let message = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty else { return }
        if isStreaming {
            enqueueTurn(message)
            return
        }
        startStreamingTask(prompt: message)
    }

    private func enqueueTurn(_ prompt: String) {
        let now = Date()
        let userID = UUID()
        let assistantID = UUID()
        let run = AgentTurnRun(
            userMessageID: userID,
            assistantMessageID: assistantID,
            status: .queued,
            queuedAt: now
        )
        turnRuns.append(run)
        pendingTurns.append(PendingAgentTurn(
            prompt: prompt,
            runID: run.id,
            userMessageID: userID,
            assistantMessageID: assistantID
        ))
        queuedTurnCount = pendingTurns.count
        messages.append(.init(id: userID, role: .user, content: prompt, createdAt: now))
        messages.append(.init(id: assistantID, role: .assistant, content: "小巴处理中，已加入队列。", createdAt: now))
    }

    private func startStreamingTask(prompt: String) {
        streamingTask = Task { [weak self] in
            await self?.send(prompt)
        }
    }

    private func startStreamingTask(turn: PendingAgentTurn) {
        streamingTask = Task { [weak self] in
            await self?.runTurn(
                turn.prompt,
                precreatedRunID: turn.runID,
                precreatedUserMessageID: turn.userMessageID,
                precreatedAssistantMessageID: turn.assistantMessageID
            )
        }
    }

    private func pumpTurnQueue() {
        guard !isStreaming, streamingTask == nil, !pendingTurns.isEmpty else { return }
        let next = pendingTurns.removeFirst()
        queuedTurnCount = pendingTurns.count
        startStreamingTask(turn: next)
    }

    /// Stops the current stream. Partial content already received stays on screen
    /// (send()'s CancellationError path leaves isStreaming=false without wiping it).
    public func cancelStreaming() {
        streamingTask?.cancel()
        streamingTask = nil
        isStreaming = false
        clearLiveStatus()
        // User pressed Stop: settle the trace (mark running steps done) rather than
        // wiping it, so any partial content stays paired with a completed-looking
        // trace. The next send() clears it wholesale.
        settleThinkingSteps()
    }

    public func send(_ text: String) async {
        await runTurn(text)
    }

    private func runTurn(
        _ text: String,
        precreatedRunID: UUID? = nil,
        precreatedUserMessageID: UUID? = nil,
        precreatedAssistantMessageID: UUID? = nil
    ) async {
        let message = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, let streamService else {
            return
        }

        errorMessage = nil
        toolActivities = []
        clearLiveStatus()
        clearThinkingSteps()
        isStreaming = true
        runState = .preparing
        lastPrompt = message
        let turnStartedAt = Date()
        let assistantID: UUID
        if let precreatedAssistantMessageID {
            assistantID = precreatedAssistantMessageID
            if let precreatedUserMessageID,
               let userIndex = messages.firstIndex(where: { $0.id == precreatedUserMessageID }) {
                messages[userIndex].content = message
                messages[userIndex].createdAt = turnStartedAt
            }
            if let idx = messages.firstIndex(where: { $0.id == precreatedAssistantMessageID }) {
                messages[idx].content = ""
                messages[idx].createdAt = turnStartedAt
            }
            if let precreatedRunID,
               let runIndex = turnRuns.firstIndex(where: { $0.id == precreatedRunID }) {
                turnRuns[runIndex].status = .streaming
                turnRuns[runIndex].startedAt = turnStartedAt
            }
        } else {
            messages.append(.init(role: .user, content: message, createdAt: turnStartedAt))
            messages.append(.init(role: .assistant, content: "", createdAt: turnStartedAt))
            // Track the streaming assistant message by its stable id, not a captured
            // index: New Chat / loading a conversation / sending again resets `messages`
            // mid-stream, which would make a captured index stale and crash on next token.
            assistantID = messages[messages.index(before: messages.endIndex)].id
        }
        streamingAssistantMessageID = assistantID
        defer {
            streamingTask = nil
            if streamingAssistantMessageID == assistantID {
                streamingAssistantMessageID = nil
            }
            pumpTurnQueue()
        }

        // 流式 token 合批:真 token 流式下每个 token 都改 @Published messages 会触发
        // SwiftUI 每 token 全量重排(聊天气泡布局昂贵)→ 每秒数十次重排 → 100% CPU 卡死。
        // 按 ~60ms 节流 flush(重排上限 ~16/s);所有退出路径都要 flush 剩余,不丢字。
        var pendingTokens = ""
        var lastTokenFlush = Date.distantPast
        let tokenFlushInterval: TimeInterval = 0.06
        func flushPendingTokens() {
            guard !pendingTokens.isEmpty,
                  let idx = messages.firstIndex(where: { $0.id == assistantID }) else { return }
            messages[idx].content += pendingTokens
            pendingTokens = ""
        }

        do {
            let importedReports = try await importLabReportAttachmentsIfNeeded()
            let importedHashes = Set(labReportImports.map(\.sourceHash))
            let chatImages = buildChatImages(excludingImportedHashes: importedHashes)
            if let firstImport = importedReports.first {
                attachDynamicCard(
                    medicalExamImportDynamicCard(for: firstImport),
                    to: assistantID,
                    toolName: "medical_exam_import"
                )
            }
            for try await event in streamService.stream(
                message: message,
                conversationID: conversationID,
                extraContext: buildExtraContext(),
                images: chatImages
            ) {
                switch event {
                case .start(let id):
                    conversationID = id ?? conversationID
                case .status(let stage, let detail, let round):
                    // Real backend stage hint. Status events are rare (a handful
                    // before the first token) — apply immediately, bypassing the
                    // 60ms token flush throttle (that throttle only guards token
                    // repaints; status is not batched).
                    let mapped = Self.statusText(stage: stage, detail: detail, round: round)
                    liveStatusText = mapped.key
                    liveStatusDetail = mapped.detail
                    // Accumulate into the visible trace (kept across the first token,
                    // unlike the single-line liveStatusText above). Consecutive same
                    // stage/label is de-duped inside appendThinkingStep.
                    appendThinkingStep(labelKey: mapped.key, labelDetail: mapped.detail)
                case .token(let content):
                    let isFirstToken = runState != .streaming
                    runState = .streaming
                    // First real token → drop the single live status line, but KEEP the
                    // accumulated trace visible during content streaming. Mark any
                    // in-flight step done and add a running "composing" step so the
                    // trace reflects that the model is now writing the answer.
                    clearLiveStatus()
                    if isFirstToken {
                        settleThinkingSteps()
                        if !thinkingSteps.isEmpty {
                            appendThinkingStep(labelKey: "Reva is composing a reply…", labelDetail: nil)
                        }
                    }
                    guard messages.contains(where: { $0.id == assistantID }) else {
                        isStreaming = false
                        return
                    }
                    pendingTokens += content
                    let now = Date()
                    if now.timeIntervalSince(lastTokenFlush) >= tokenFlushInterval {
                        flushPendingTokens()
                        lastTokenFlush = now
                    }
                case .tool(let name, let success):
                    applyToolEvent(AgentToolEvent(
                        name: name,
                        success: success,
                        arguments: nil,
                        preview: nil,
                        result: nil,
                        round: nil
                    ))
                case .toolDetails(let toolEvent):
                    applyToolEvent(toolEvent)
                case .perfPreLLM(let preLLMMs, let stages):
                    // 中途 perf 提示:仅暂存(prompt 组装刚完成,首 token 前)。主瀑布图从
                    // 最终 done.perf 渲染;这里让「组装中…」等实时提示未来有据可依。
                    livePreLLMPerf = MessagePerf(preLLMMs: preLLMMs, preLLMStages: stages)
                case .done(let id, _, let completionStatus, let model, let selectedModel, let answerModel, let toolModels, let fallbackReasons, let sourcesUsed, let toolsUsed, let elapsedMs, let llmRounds, let cards, let perf, let llmUsage, let finalThinkingSteps, let medicationBatchDecision):
                    conversationID = id ?? conversationID
                    lastCompletionStatus = completionStatus
                    lastModel = answerModel ?? model
                    lastSourcesUsed = sourcesUsed
                    // 把 meta 回填到「正在流式的那条消息对象」(按 assistantID 定位),
                    // 不只更全局 —— footer 是每条消息级渲染。先 flush 残留 token 再写 meta。
                    flushPendingTokens()
                    if let idx = messages.firstIndex(where: { $0.id == assistantID }) {
                        messages[idx].model = model
                        messages[idx].selectedModel = selectedModel
                        messages[idx].answerModel = answerModel
                        messages[idx].toolModels = toolModels
                        messages[idx].fallbackReasons = fallbackReasons
                        messages[idx].elapsedMs = elapsedMs
                        messages[idx].llmRounds = llmRounds
                        messages[idx].llmUsage = llmUsage
                        messages[idx].sourcesUsed = sourcesUsed
                        messages[idx].toolsUsed = Self.mergedToolNames(
                            existing: messages[idx].toolsUsed,
                            incoming: toolsUsed
                        )
                        messages[idx].completionStatus = completionStatus
                        if !finalThinkingSteps.isEmpty {
                            messages[idx].thinkingSteps = finalThinkingSteps
                        } else if !liveThinkingSteps.isEmpty {
                            messages[idx].thinkingSteps = liveThinkingSteps
                        }
                        // perf 缺失(老后端)→ 保留 nil,footer 行为不变。
                        if let perf { messages[idx].perf = perf }
                        // `done.cards` is the authoritative atomic-UI composition for
                        // this turn. A streamed tool card can arrive before `done`; do
                        // not let that provisional first card hide the remaining cards.
                        if let card = AgentDynamicCardDescriptor.grouped(cards) {
                            messages[idx].cardType = card.type
                            messages[idx].cardRender = card.render
                            messages[idx].cardData = card.data
                            messages[idx].cardActions = card.actions
                            scheduleAIGCMediaRefreshIfNeeded(for: assistantID)
                        }
                    }
                    // Text confirmation/dismissal creates a fresh assistant turn,
                    // while the actionable medication draft lives on the prior
                    // assistant message. `done.cards` is therefore often empty.
                    // Project the namespaced terminal decision across the existing
                    // transcript (including nested cards_group) without disturbing
                    // sibling cards or borrowing turn-level receipts/alerts.
                    if let medicationBatchDecision {
                        projectMedicationBatchTerminal(
                            intentID: medicationBatchDecision.intentID,
                            outcome: MedicationBatchActionOutcome(
                                decisionStatus: medicationBatchDecision.status,
                                writeReceipts: medicationBatchDecision.writeReceipts,
                                safetyAlerts: medicationBatchDecision.safetyAlerts
                            )
                        )
                    }
                    livePreLLMPerf = nil
                    clearLiveStatus()
                    settleThinkingSteps()
                    // 快照本轮思考轨迹到 side-store,完成后折叠可回溯(mobile 同款;
                    // live thinkingSteps 要下一轮 send 才清,此处仍在)。
                    if !thinkingSteps.isEmpty { _completedThinkingSteps[assistantID] = thinkingSteps }
                    runState = .completed
                case .error(let message):
                    errorMessage = message
                    clearLiveStatus()
                    settleThinkingSteps()
                }
            }
        } catch is CancellationError {
            // View reload / new request cancelled this stream — not a real failure.
            flushPendingTokens()
            clearLiveStatus()
            isStreaming = false
            return
        } catch let urlError as URLError where urlError.code == .cancelled {
            // URLSession's -999 (NSURLErrorCancelled) — same benign case.
            flushPendingTokens()
            clearLiveStatus()
            isStreaming = false
            return
        } catch {
            AppLogger.agent.error("agent stream consumption failed: \(error.localizedDescription, privacy: .public)")
            errorMessage = error.localizedDescription
        }

        flushPendingTokens()  // 收尾:把节流期间缓存的尾部 token 落盘,不丢字

        // The conversation may have been reset while awaiting the stream; if the
        // assistant message is gone, there's nothing left to finalize.
        guard let assistantIndex = messages.firstIndex(where: { $0.id == assistantID }) else {
            isStreaming = false
            return
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
        clearLiveStatus()
        settleThinkingSteps()
        isStreaming = false
    }

    public func startNewConversation() {
        streamingTask?.cancel()
        streamingTask = nil
        pendingTurns = []
        queuedTurnCount = 0
        turnRuns = []
        streamingAssistantMessageID = nil
        isStreaming = false
        messages = []
        _completedThinkingSteps = [:]
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
        labReportImports = []
        contextItems = []
        preparedDraft = nil
        clearLiveStatus()
        clearThinkingSteps()
    }

    /// Refreshes the history list from the backend (`GET /agent/conversations`),
    /// matching web/mobile. On success the backend list becomes authoritative and
    /// is written to the local cache as an offline fallback. On failure (offline /
    /// 401 / 5xx) the existing cache is kept and `historyNotice` is set so the UI
    /// can tell the user it's showing a possibly-stale local copy — never silently
    /// cleared. No-op when no remote source is wired (e.g. unit tests, previews).
    /// Normalizes UI input before sending it to the backend search contract.
    /// Blank input deliberately reloads the complete remote history.
    public func searchConversationHistory(_ rawSearch: String) async {
        let normalized = rawSearch.trimmingCharacters(in: .whitespacesAndNewlines)
        await refreshConversationHistory(search: normalized.isEmpty ? nil : normalized)
    }

    public func refreshConversationHistory(limit: Int = 30, search: String? = nil) async {
        guard let remoteSource else { return }
        let normalizedSearch = search?.trimmingCharacters(in: .whitespacesAndNewlines)
        let activeSearch = normalizedSearch?.isEmpty == false ? normalizedSearch : nil
        historyRequestSequence += 1
        let requestSequence = historyRequestSequence
        isLoadingHistory = true
        defer {
            if requestSequence == historyRequestSequence {
                isLoadingHistory = false
            }
        }
        do {
            let remote = try await remoteSource.fetchConversations(limit: limit, offset: 0, search: activeSearch)
            guard requestSequence == historyRequestSequence else { return }
            // The backend list carries no messages. Don't let it wipe transcripts
            // we already have cached: keep the open chat's live messages, and keep
            // any previously-cached transcript for the rest (so offline-open still
            // works). Backend list is otherwise authoritative for ordering/titles.
            let cachedByID = Dictionary(
                conversationHistory.map { ($0.id, $0.messages) },
                uniquingKeysWith: { first, _ in first }
            )
            let merged = remote.map { snapshot -> AgentConversationSnapshot in
                if snapshot.id == currentConversationSnapshotID, !messages.isEmpty {
                    return snapshot.replacingMessages(messages)
                }
                if let cached = cachedByID[snapshot.id], !cached.isEmpty {
                    return snapshot.replacingMessages(cached)
                }
                return snapshot
            }
            conversationHistory = merged
            activeHistorySearch = activeSearch
            if activeSearch == nil {
                conversationStore?.saveConversations(merged)
            }
            historyNotice = nil

            // Keep the visible transcript in sync with other devices. The list
            // endpoint intentionally omits messages, so after reconciling the
            // list we must load detail for the currently open remote chat. On a
            // fresh Mac install with no local cache, auto-open the newest remote
            // conversation so the phone transcript appears without a manual tap.
            guard !isStreaming else { return }
            let target: AgentConversationSnapshot?
            if let currentConversationSnapshotID,
               let current = merged.first(where: { $0.id == currentConversationSnapshotID }) {
                target = current
            } else if currentConversationSnapshotID == nil, messages.isEmpty, let latest = merged.first {
                loadConversation(latest)
                target = latest
            } else {
                target = nil
            }
            if let target {
                await fetchAndApplyConversationDetail(target, remoteSource: remoteSource)
            }
        } catch APIError.unauthorized {
            guard requestSequence == historyRequestSequence else { return }
            // 401 already cleared the token + posted authSessionExpired; the app
            // root drops to login. Keep the cache visible meanwhile.
            if let activeSearch {
                conversationHistory = localConversationHistory(matching: activeSearch)
                activeHistorySearch = activeSearch
                historyNotice = "登录已过期，显示本机匹配的历史缓存。"
            } else {
                conversationHistory = localConversationHistory()
                activeHistorySearch = nil
                historyNotice = "登录已过期，下面是本地缓存的历史。"
            }
        } catch {
            guard requestSequence == historyRequestSequence else { return }
            AppLogger.agent.error("conversation history refresh failed: \(error.localizedDescription, privacy: .public)")
            if let activeSearch {
                conversationHistory = localConversationHistory(matching: activeSearch)
                activeHistorySearch = activeSearch
                historyNotice = "离线或服务不可用，显示本机匹配的历史缓存。"
            } else {
                conversationHistory = localConversationHistory()
                activeHistorySearch = nil
                historyNotice = "离线或服务不可用，显示本地缓存的历史。"
            }
        }
    }

    private func localConversationHistory(matching search: String? = nil) -> [AgentConversationSnapshot] {
        let cached = (conversationStore?.loadConversations() ?? conversationHistory).map {
            $0.replacingMessages(Self.redactedMessagesForLocalPersistence($0.messages))
        }
        guard let search, !search.isEmpty else { return cached }
        return cached.filter { conversation in
            conversation.title.localizedCaseInsensitiveContains(search)
                || conversation.messages.contains { $0.content.localizedCaseInsensitiveContains(search) }
        }
    }

    /// Loads a conversation a user tapped in the history list. If the snapshot has
    /// no messages (it came from the backend list), the full transcript is fetched
    /// from `GET /agent/conversations/{id}` so other devices' conversations open
    /// correctly. On detail-fetch failure the locally-cached messages (if any) are
    /// used and a notice is shown.
    public func openConversation(_ conversation: AgentConversationSnapshot) async {
        loadConversation(conversation)
        guard conversation.conversationID != nil,
              let remoteSource else {
            return
        }
        isLoadingHistory = true
        defer { isLoadingHistory = false }
        await fetchAndApplyConversationDetail(conversation, remoteSource: remoteSource)
    }

    private func fetchAndApplyConversationDetail(
        _ conversation: AgentConversationSnapshot,
        remoteSource: AgentConversationRemoteSourcing
    ) async {
        guard let conversationID = conversation.conversationID else { return }
        do {
            let detail = try await remoteSource.fetchDetail(conversationID: conversationID)
            // The user may have navigated away while the fetch was in flight.
            guard currentConversationSnapshotID == conversation.id else { return }
            messages = detail
            lastPrompt = detail.last(where: { $0.role == .user })?.content
            rehydrateLastAssistantMeta()
            rebuildProposedActions()
            scheduleAIGCMediaRefreshesForVisibleMessages()
            historyNotice = nil
            cacheLoadedMessages(detail, for: conversation)
        } catch {
            AppLogger.agent.error("conversation detail load failed: \(error.localizedDescription, privacy: .public)")
            // Fall back to whatever the local cache had for this snapshot.
            let cached = cachedMessages(for: conversation)
            if currentConversationSnapshotID == conversation.id {
                messages = cached
                lastPrompt = cached.last(where: { $0.role == .user })?.content
                rebuildProposedActions()
            }
            historyNotice = cached.isEmpty
                ? "无法加载这条对话，请检查网络后重试。"
                : "离线或服务不可用，显示本地缓存的这条对话。"
        }
    }

    public func loadConversation(_ conversation: AgentConversationSnapshot) {
        currentConversationSnapshotID = conversation.id
        conversationID = conversation.conversationID
        messages = conversation.messages
        errorMessage = nil
        toolActivities = []
        lastPrompt = conversation.messages.last(where: { $0.role == .user })?.content
        // 证据面板/状态 chip 从最后一条 assistant 消息回灌 —— 这些是 per-message
        // 持久化的(气泡里"引用 N 项数据"就来自它),此前打开历史对话被硬清空,
        // 造成"气泡有引用、右侧证据面板空占位"的分裂(用户实测截图)。
        rehydrateLastAssistantMeta()
        rebuildProposedActions()
    }

    /// 从当前 messages 的最后一条 assistant 消息恢复"最近一轮"元数据
    /// (lastSourcesUsed / lastModel / lastCompletionStatus)。直播流的 done
    /// 事件仍会覆盖为最新值;无 assistant 消息时回到空态。
    func rehydrateLastAssistantMeta() {
        let lastAssistant = messages.last(where: { $0.role == .assistant })
        lastSourcesUsed = lastAssistant?.sourcesUsed ?? []
        lastModel = lastAssistant?.model
        lastCompletionStatus = lastAssistant?.completionStatus
    }

    /// Writes the freshly-loaded messages back into the cached snapshot so a later
    /// offline open of the same conversation still shows its transcript.
    private func cacheLoadedMessages(_ messages: [AgentChatMessage], for conversation: AgentConversationSnapshot) {
        guard let index = conversationHistory.firstIndex(where: { $0.id == conversation.id }) else { return }
        conversationHistory[index] = conversationHistory[index].replacingMessages(messages)
        guard let conversationStore else { return }
        guard activeHistorySearch != nil else {
            conversationStore.saveConversations(conversationHistory)
            return
        }

        // A detail request may happen while the rail is filtered. Merge the fresh
        // transcript into the durable full cache instead of persisting the search
        // subset as if it were the user's complete history.
        var fullCache = conversationStore.loadConversations()
        let cacheIndex: Int?
        if let remoteConversationID = conversation.conversationID {
            cacheIndex = fullCache.firstIndex(where: {
                $0.id == conversation.id || $0.conversationID == remoteConversationID
            })
        } else {
            cacheIndex = fullCache.firstIndex(where: { $0.id == conversation.id })
        }
        if let cacheIndex {
            fullCache[cacheIndex] = fullCache[cacheIndex].replacingMessages(messages)
        } else {
            fullCache.append(conversation.replacingMessages(messages))
        }
        conversationStore.saveConversations(fullCache)
    }

    private func cachedMessages(for conversation: AgentConversationSnapshot) -> [AgentChatMessage] {
        if !conversation.messages.isEmpty { return conversation.messages }
        let cache = conversationStore?.loadConversations() ?? []
        if let byID = cache.first(where: { $0.id == conversation.id }), !byID.messages.isEmpty {
            return byID.messages
        }
        if let convID = conversation.conversationID,
           let byConvID = cache.first(where: { $0.conversationID == convID }), !byConvID.messages.isEmpty {
            return byConvID.messages
        }
        return []
    }

    public func deleteConversation(_ conversation: AgentConversationSnapshot) {
        // Optimistically drop it locally; if it had a backend id, also delete it
        // server-side so it stays gone across devices. Backend failure surfaces a
        // notice but the local removal stands (the next refresh reconciles).
        if let conversationID = conversation.conversationID, let remoteSource {
            Task { [weak self] in
                do {
                    try await remoteSource.deleteConversation(conversationID: conversationID)
                } catch {
                    await self?.reportDeleteFailure(error)
                }
            }
        }
        conversationHistory.removeAll { $0.id == conversation.id }
        conversationStore?.saveConversations(conversationHistory)
        if currentConversationSnapshotID == conversation.id {
            startNewConversation()
        }
    }

    /// Renames a conversation: pushes the new title to the backend (so it matches
    /// web/mobile), then updates the local list/cache. Backend failure surfaces a
    /// notice and leaves the old title in place rather than faking success.
    public func renameConversation(_ conversation: AgentConversationSnapshot, to newTitle: String) async {
        let trimmed = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        if let conversationID = conversation.conversationID, let remoteSource {
            do {
                try await remoteSource.renameConversation(conversationID: conversationID, title: trimmed)
            } catch {
                AppLogger.agent.error("conversation rename failed: \(error.localizedDescription, privacy: .public)")
                historyNotice = "改名失败，请检查网络后重试。"
                return
            }
        }
        if let index = conversationHistory.firstIndex(where: { $0.id == conversation.id }) {
            let existing = conversationHistory[index]
            conversationHistory[index] = AgentConversationSnapshot(
                id: existing.id,
                conversationID: existing.conversationID,
                title: trimmed,
                messages: existing.messages,
                updatedAt: existing.updatedAt
            )
            conversationStore?.saveConversations(conversationHistory)
        }
    }

    /// Creates a public share link for a conversation and returns the URL for the
    /// caller to copy / open. Returns nil (with a notice) on failure or when the
    /// conversation has no durable backend id yet — never fabricates a link.
    public func shareConversation(_ conversation: AgentConversationSnapshot) async -> URL? {
        guard let conversationID = conversation.conversationID, let remoteSource else {
            historyNotice = "这个对话还没同步到服务器，暂时无法分享。"
            return nil
        }
        do {
            return try await remoteSource.shareConversation(conversationID: conversationID)
        } catch {
            AppLogger.agent.error("conversation share failed: \(error.localizedDescription, privacy: .public)")
            historyNotice = "生成分享链接失败，请检查网络后重试。"
            return nil
        }
    }

    private func reportDeleteFailure(_ error: Error) {
        AppLogger.agent.error("conversation delete failed: \(error.localizedDescription, privacy: .public)")
        historyNotice = "删除未同步到服务器，可能在其它设备仍可见。"
    }

    private func applyToolEvent(_ event: AgentToolEvent) {
        let name = event.name?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false ? event.name! : "tool"
        let status = event.success.map { $0 ? AgentToolActivityStatus.succeeded : .failed } ?? .running

        if event.success != nil,
           let runningIndex = toolActivities.lastIndex(where: { $0.name == name && $0.status == .running }) {
            let running = toolActivities[runningIndex]
            toolActivities[runningIndex] = AgentToolActivity(
                id: running.id,
                name: running.name,
                status: status,
                arguments: running.arguments ?? event.arguments,
                preview: event.preview ?? running.preview,
                result: event.result ?? running.result,
                round: running.round ?? event.round
            )
            return
        }

        toolActivities.append(
            AgentToolActivity(
                name: name,
                status: status,
                arguments: event.arguments,
                preview: event.preview,
                result: event.result,
                round: event.round
            )
        )
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

    /// Removes short-lived image capabilities before a snapshot crosses the
    /// UserDefaults/offline-cache boundary. This is deliberately separate from
    /// transcript rendering, which may attach a fresh in-memory URL.
    static func redactedMessagesForLocalPersistence(_ messages: [AgentChatMessage]) -> [AgentChatMessage] {
        messages.map { message in
            guard let cardType = message.cardType,
                  let cardData = message.cardData,
                  let redactedData = redactedCardDataForLocalPersistence(
                    type: cardType,
                    data: cardData
                  ) else {
                return message
            }
            var redacted = message
            redacted.cardData = redactedData
            return redacted
        }
    }

    private static func redactedCardDataForLocalPersistence(
        type: String,
        data: AgentDynamicCardValue
    ) -> AgentDynamicCardValue? {
        guard case .object(var card) = data else { return nil }
        if type == "aigc_media_job",
           case .object(var result)? = card["result"] {
            result["url"] = .null
            card["result"] = .object(result)
            return .object(card)
        }
        if type == "diet_draft" {
            card["photo_url"] = .null
            return .object(card)
        }
        guard type == "cards_group",
              case .array(let rawCards)? = card["cards"] else {
            return nil
        }
        let redactedCards = rawCards.map { raw in
            guard let descriptor = AgentDynamicCardDescriptor.fromGroupValue(raw) else {
                return raw
            }
            let redactedData = redactedCardDataForLocalPersistence(
                type: descriptor.type,
                data: descriptor.data
            ) ?? descriptor.data
            return AgentDynamicCardDescriptor(
                type: descriptor.type,
                render: descriptor.render,
                data: redactedData,
                actions: descriptor.actions
            ).groupValue() ?? raw
        }
        card["cards"] = .array(redactedCards)
        return .object(card)
    }

    private func cardDataForTranscript(_ message: AgentChatMessage) -> AgentDynamicCardValue? {
        guard let type = message.cardType, let data = message.cardData else {
            return message.cardData
        }
        return Self.hydratingAIGCResultURLs(
            type: type,
            data: data,
            resultURLs: aigcResultURLs
        )
    }

    private static func hydratingAIGCResultURLs(
        type: String,
        data: AgentDynamicCardValue,
        resultURLs: [String: String]
    ) -> AgentDynamicCardValue {
        guard case .object(var card) = data else { return data }
        if type == "aigc_media_job",
           let jobID = card["job_id"]?.stringValue,
           let resultURL = resultURLs[jobID] {
            var result: [String: AgentDynamicCardValue]
            if case .object(let existing)? = card["result"] {
                result = existing
            } else {
                result = [:]
            }
            result["url"] = .string(resultURL)
            card["result"] = .object(result)
            return .object(card)
        }
        guard type == "cards_group",
              case .array(let rawCards)? = card["cards"] else {
            return data
        }
        card["cards"] = .array(rawCards.map { raw in
            guard let descriptor = AgentDynamicCardDescriptor.fromGroupValue(raw) else {
                return raw
            }
            let hydrated = hydratingAIGCResultURLs(
                type: descriptor.type,
                data: descriptor.data,
                resultURLs: resultURLs
            )
            return AgentDynamicCardDescriptor(
                type: descriptor.type,
                render: descriptor.render,
                data: hydrated,
                actions: descriptor.actions
            ).groupValue() ?? raw
        })
        return .object(card)
    }

    private func moveAIGCResultURLToMemory(_ data: AgentDynamicCardValue) -> AgentDynamicCardValue {
        guard case .object(var card) = data,
              let jobID = card["job_id"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
              !jobID.isEmpty,
              case .object(var result)? = card["result"] else {
            return data
        }
        if let url = result["url"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines), !url.isEmpty {
            aigcResultURLs[jobID] = url
        }
        result["url"] = .null
        card["result"] = .object(result)
        return .object(card)
    }

    /// WebView transcript 喂入的安全 HTML 信封(带内容缓存,见上面缓存字段说明)。
    /// 在 View.body 里调用:读 messages/isStreaming/proposedActions 建立 Observation 依赖,
    /// 这三者真正变化才重渲;打字(只改 View 的 draft)命中缓存,不再每键重 parse markdown。
    /// 流式中的最后一条助手消息走 plain text(streaming=true);其余走富 markdown。
    public func renderedTranscript(language: String = AppLanguage.defaultLanguage.rawValue) -> [ChatTranscriptHTML.RenderedMessage] {
        if isStreaming == _transcriptCacheStreaming
            && streamingAssistantMessageID == _transcriptCacheStreamingAssistantID
            && messages == _transcriptCacheMessages
            && proposedActions == _transcriptCacheProposed
            && thinkingSteps == _transcriptCacheThinkingSteps
            && language == _transcriptCacheLanguage
            && aigcResultURLs == _transcriptCacheAIGCResultURLs {
            return _transcriptCache
        }
        let fallbackStreamingAssistantID = messages.last(where: { $0.role == .assistant })?.id
        let streamingTargetID = streamingAssistantMessageID ?? fallbackStreamingAssistantID
        let rendered = messages.map { message -> ChatTranscriptHTML.RenderedMessage in
            let isStreamingThis = isStreaming && message.id == streamingTargetID && message.role == .assistant
            let content = displayContent(for: message)
            let cardHTML = message.role == .assistant
                ? ChatTranscriptHTML.dynamicCardHTML(
                    type: message.cardType,
                    render: message.cardRender,
                    data: cardDataForTranscript(message),
                    actions: message.cardActions
                ) ?? ""
                : ""
            let bodyHTML: String
            if message.role == .user {
                // 用户消息纯文本:转义 + 换行保留,不解析 markdown。
                bodyHTML = "<p class=\"streaming-text\">" + ChatTranscriptHTML.escape(content) + "</p>"
                    + ChatTranscriptHTML.imageGalleryHTML(urls: message.remoteImageURLs)
            } else if isStreamingThis {
                if content.isEmpty {
                    // 等待首 token:在气泡内渲染展开的"思考过程"轨迹,跟随气泡位置(短对话在顶、
                    // 滚动长对话在底),而不是钉在输入框上方。有 status 步骤 → 累积轨迹;老后端
                    // 无步骤 → 单行兜底。首 token 到达后 content 非空,自动切到下面的折叠态 + 正文。
                    let trace = ChatTranscriptHTML.thinkingTraceHTML(steps: thinkingSteps, language: language, open: true)
                    bodyHTML = trace.isEmpty ? cardHTML : cardHTML + trace
                } else {
                    // 答案流式中:轨迹折叠到正文上方(想看过程可点开),plain 文本避免重 parse。
                    let trace = ChatTranscriptHTML.thinkingTraceHTML(steps: thinkingSteps, language: language, open: false)
                    bodyHTML = cardHTML + trace + "<div class=\"streaming-text\">" + ChatTranscriptHTML.escape(content) + "</div>"
                }
            } else {
                // 已完成:把本条回答的思考轨迹以折叠态留在正文上方,用户可展开回溯(mobile 同款)。
                let persistedTrace = message.thinkingSteps.map {
                    ThinkingStep(labelKey: $0, labelDetail: nil, state: .done)
                }
                let finishedTrace = _completedThinkingSteps[message.id] ?? persistedTrace
                let trace = finishedTrace.isEmpty ? "" : {
                    ChatTranscriptHTML.thinkingTraceHTML(steps: finishedTrace, language: language, open: false)
                }()
                let textHTML = content.isEmpty ? "" : ChatTranscriptHTML.renderMessageBody(markdown: content)
                bodyHTML = cardHTML + trace + textHTML
            }
            let showCopy = message.role == .assistant && !isStreamingThis && !content.isEmpty
            let footerHTML: String
            if message.role == .assistant && !isStreamingThis && message.hasMeta {
                footerHTML = ChatTranscriptHTML.metaFooterHTML(
                    model: message.model,
                    selectedModel: message.selectedModel,
                    answerModel: message.answerModel,
                    toolModels: message.toolModels,
                    fallbackReasons: message.fallbackReasons,
                    elapsedMs: message.elapsedMs,
                    llmRounds: message.llmRounds,
                    sourcesUsed: message.sourcesUsed,
                    toolsUsed: message.toolsUsed,
                    perf: message.perf,
                    llmUsage: message.llmUsage
                )
            } else {
                footerHTML = ""
            }
            let timeLabels = ChatTranscriptHTML.messageTimeLabels(for: message.createdAt)
            let sentAtEpochMs = message.createdAt.map { Int64($0.timeIntervalSince1970 * 1000) }
            return ChatTranscriptHTML.RenderedMessage(
                id: message.id.uuidString,
                role: message.role == .user ? "user" : "assistant",
                bodyHTML: bodyHTML,
                isStreaming: isStreamingThis,
                showCopy: showCopy,
                footerHTML: footerHTML,
                sentAtShort: timeLabels?.short ?? "",
                sentAtFull: timeLabels?.full ?? "",
                sentAtEpochMs: sentAtEpochMs
            )
        }
        let visibleRendered = rendered.filter { message in
            !(message.isStreaming
                && message.role == "assistant"
                && message.bodyHTML.isEmpty
                && message.footerHTML.isEmpty)
        }
        _transcriptCacheMessages = messages
        _transcriptCacheStreaming = isStreaming
        _transcriptCacheStreamingAssistantID = streamingAssistantMessageID
        _transcriptCacheProposed = proposedActions
        _transcriptCacheThinkingSteps = thinkingSteps
        _transcriptCacheLanguage = language
        _transcriptCacheAIGCResultURLs = aigcResultURLs
        _transcriptCache = visibleRendered
        return visibleRendered
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
        // Once the backend assigns a conversation id, key the local snapshot by the
        // SAME deterministic UUID the remote list uses. Otherwise a fresh chat keeps
        // a random local UUID and the next backend refresh shows it twice (random +
        // deterministic). Drop any earlier random-id row for this conversation.
        let snapshotID: UUID
        if let conversationID {
            snapshotID = AgentConversationClient.deterministicID(forConversationID: conversationID)
            if let previous = currentConversationSnapshotID, previous != snapshotID {
                conversationHistory.removeAll { $0.id == previous }
            }
        } else {
            snapshotID = currentConversationSnapshotID ?? UUID()
        }
        currentConversationSnapshotID = snapshotID
        let snapshot = AgentConversationSnapshot(
            id: snapshotID,
            conversationID: conversationID,
            title: conversationTitle(from: messages),
            messages: Self.redactedMessagesForLocalPersistence(messages),
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

    /// Clears the real-stage live status (both key and dynamic detail) so the
    /// ThinkingStatusLine falls back to its time-based rotation until the next
    /// `status` event, and no stale label survives into the next turn.
    private func clearLiveStatus() {
        liveStatusText = nil
        liveStatusDetail = nil
    }

    /// Appends a new running step to the trace, first marking the previously
    /// running step done. Consecutive events that resolve to the same label are
    /// suppressed (the last step just stays running) so the trace never flickers
    /// the same line repeatedly. Called from the `.status` handler.
    private func appendThinkingStep(labelKey: String, labelDetail: String?) {
        let candidate = ThinkingStep(labelKey: labelKey, labelDetail: labelDetail, state: .running)
        if let last = thinkingSteps.last, last.hasSameLabel(as: candidate) {
            // Same activity as the current tail — keep it running, don't duplicate.
            if last.state != .running {
                thinkingSteps[thinkingSteps.index(before: thinkingSteps.endIndex)].state = .running
            }
            return
        }
        markRunningThinkingStepsDone()
        thinkingSteps.append(candidate)
        if thinkingSteps.count > Self.maxLiveThinkingSteps {
            thinkingSteps.removeFirst(thinkingSteps.count - Self.maxLiveThinkingSteps)
        }
    }

    /// Flips every still-running step to done (leaves order/labels intact).
    private func markRunningThinkingStepsDone() {
        for index in thinkingSteps.indices where thinkingSteps[index].state == .running {
            thinkingSteps[index].state = .done
        }
    }

    /// First token / completion: keep the trace visible but stop showing any step
    /// as in-flight. The trace is NOT cleared here — it persists through content
    /// streaming until the next turn resets it.
    private func settleThinkingSteps() {
        markRunningThinkingStepsDone()
    }

    /// New turn boundary only (`send()` / `startNewConversation()` /
    /// `cancelStreaming()`): drop the whole trace.
    private func clearThinkingSteps() {
        thinkingSteps = []
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
        if multiModel {
            // 多模型综合分析: 不带 model_id, 后端用商用三强 panel。
            context["multi_model"] = true
        } else if let selectedModelID {
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
        if !labReportImports.isEmpty {
            context["lab_report_imports"] = labReportImports.map(labReportImportPayload)
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

    @discardableResult
    private func importLabReportAttachmentsIfNeeded() async throws -> [LabReportImportContext] {
        guard let labUploadService else { return [] }
        let medicalAttachments = attachments.filter {
            $0.sourceKind == .medicalFile && LabReportUploadMime.isSupported(forExtension: $0.url.pathExtension)
        }
        guard !medicalAttachments.isEmpty else { return [] }

        var imported: [LabReportImportContext] = []
        for attachment in medicalAttachments {
            guard !labReportImports.contains(where: { $0.sourceHash == attachment.sha256 }) else {
                continue
            }
            let result: LabUploadResult
            do {
                result = try await labUploadService.importReport(fileURL: attachment.url)
            } catch {
                continue
            }
            let item = LabReportImportContext(
                fileName: attachment.name,
                sourceHash: attachment.sha256,
                sourceKind: attachment.sourceKind,
                result: result
            )
            labReportImports.append(item)
            imported.append(item)
        }
        return imported
    }

    private func labReportImportPayload(_ item: LabReportImportContext) -> [String: Any] {
        var payload: [String: Any] = [
            "file_name": item.fileName,
            "source_hash": item.sourceHash,
            "source_kind": item.sourceKind.rawValue,
            "exam_id": item.result.examID,
            "message": item.result.message
        ]
        if let examDate = item.result.examDate {
            payload["exam_date"] = examDate
        }
        if let examType = item.result.examType {
            payload["exam_type"] = examType
        }
        if let hospitalName = item.result.hospitalName {
            payload["hospital_name"] = hospitalName
        }
        if let itemsCount = item.result.itemsCount {
            payload["items_count"] = itemsCount
        }
        if let abnormalCount = item.result.abnormalCount {
            payload["abnormal_count"] = abnormalCount
        }
        if let conclusionsCount = item.result.conclusionsCount {
            payload["conclusions_count"] = conclusionsCount
        }
        if let conclusion = item.result.conclusion {
            payload["conclusion"] = conclusion
        }
        return payload
    }

    private func attachDynamicCard(
        _ card: AgentDynamicCardDescriptor,
        to messageID: UUID,
        toolName: String? = nil
    ) {
        guard let idx = messages.firstIndex(where: { $0.id == messageID }) else {
            return
        }
        messages[idx].cardType = card.type
        messages[idx].cardRender = card.render
        messages[idx].cardData = card.type == "aigc_media_job"
            ? moveAIGCResultURLToMemory(card.data)
            : card.data
        messages[idx].cardActions = card.actions
        scheduleAIGCMediaRefreshIfNeeded(for: messageID)
        if let toolName {
            messages[idx].toolsUsed = Self.mergedToolNames(
                existing: messages[idx].toolsUsed,
                incoming: [toolName]
            )
        }
    }

    private func scheduleAIGCMediaRefreshesForVisibleMessages() {
        for message in messages where !Self.aigcMediaJobIDs(in: message).isEmpty {
            scheduleAIGCMediaRefreshIfNeeded(for: message.id)
        }
    }

    private func scheduleAIGCMediaRefreshIfNeeded(for messageID: UUID) {
        guard let aigcMediaClient,
              let message = messages.first(where: { $0.id == messageID }) else {
            return
        }

        for jobID in Self.aigcMediaJobIDs(in: message) where aigcRefreshTasks[jobID] == nil {
            aigcRefreshTasks[jobID] = Task { [weak self, aigcMediaClient] in
                defer { self?.aigcRefreshTasks[jobID] = nil }
                for _ in 0..<80 {
                    guard !Task.isCancelled else { return }
                    do {
                        let projection = try await aigcMediaClient.getJob(id: jobID)
                        guard let self else { return }
                        if let index = self.messages.firstIndex(where: { $0.id == messageID }),
                           let type = self.messages[index].cardType,
                           let data = self.messages[index].cardData,
                           let updated = Self.replacingAIGCMediaJob(
                            type: type,
                            data: data,
                            jobID: jobID,
                            replacement: projection.persistedCardData(
                                title: Self.aigcCardTitle(in: self.messages[index], jobID: jobID) ?? "小巴创作"
                            )
                           ) {
                            self.messages[index].cardData = updated
                            if let resultURL = projection.resultURL {
                                self.aigcResultURLs[jobID] = resultURL
                            } else {
                                self.aigcResultURLs.removeValue(forKey: jobID)
                            }
                            self.persistCurrentConversation()
                        }
                        if projection.isTerminal { return }
                    } catch APIError.unauthorized {
                        return
                    } catch {
                        // Keep the last private projection visible. A later poll may
                        // succeed; the server remains the source of terminal state.
                    }
                    try? await Task.sleep(for: .milliseconds(6000))
                }
            }
        }
    }

    private static func aigcMediaJobIDs(in message: AgentChatMessage) -> [String] {
        guard let type = message.cardType, let data = message.cardData else { return [] }
        if type == "aigc_media_job",
           let jobID = data["job_id"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines),
           !jobID.isEmpty {
            return [jobID]
        }
        guard type == "cards_group",
              case .array(let rawCards)? = data["cards"] else {
            return []
        }
        return rawCards.compactMap(AgentDynamicCardDescriptor.fromGroupValue).compactMap { descriptor in
            guard descriptor.type == "aigc_media_job" else { return nil }
            let jobID = descriptor.data["job_id"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return jobID.isEmpty ? nil : jobID
        }
    }

    private static func aigcCardTitle(in message: AgentChatMessage, jobID: String) -> String? {
        guard let type = message.cardType, let data = message.cardData else { return nil }
        if type == "aigc_media_job", data["job_id"]?.stringValue == jobID {
            return data["title"]?.stringValue
        }
        guard type == "cards_group",
              case .array(let rawCards)? = data["cards"] else {
            return nil
        }
        return rawCards
            .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
            .first(where: { $0.type == "aigc_media_job" && $0.data["job_id"]?.stringValue == jobID })?
            .data["title"]?.stringValue
    }

    private static func replacingAIGCMediaJob(
        type: String,
        data: AgentDynamicCardValue,
        jobID: String,
        replacement: AgentDynamicCardValue
    ) -> AgentDynamicCardValue? {
        if type == "aigc_media_job" {
            return data["job_id"]?.stringValue == jobID ? replacement : nil
        }
        guard type == "cards_group",
              case .object(var group) = data,
              case .array(let rawCards)? = group["cards"] else {
            return nil
        }
        var didUpdate = false
        group["cards"] = .array(rawCards.map { raw in
            guard let descriptor = AgentDynamicCardDescriptor.fromGroupValue(raw),
                  descriptor.type == "aigc_media_job",
                  descriptor.data["job_id"]?.stringValue == jobID else {
                return raw
            }
            didUpdate = true
            return AgentDynamicCardDescriptor(
                type: descriptor.type,
                render: descriptor.render,
                data: replacement,
                actions: descriptor.actions
            ).groupValue() ?? raw
        })
        return didUpdate ? .object(group) : nil
    }

    /// Consume the server-issued AIGC draft after a direct UI gesture. The
    /// client sends only the opaque confirmation ID; prompt/source remain bound
    /// to the encrypted server draft.
    public func confirmAIGCMediaDraft(id: String) async {
        guard let aigcMediaClient, !id.isEmpty else { return }
        do {
            let projection = try await aigcMediaClient.confirmDraft(id: id)
            applyAIGCMediaJobProjection(projection, confirmationID: id)
        } catch {
            // A timeout or lost response may happen after the server accepted
            // the paid task. Resolve the owner-scoped ledger before leaving the
            // draft actionable so another click cannot create false uncertainty.
            guard let confirmation = try? await aigcMediaClient.getConfirmation(id: id),
                  let projection = confirmation.job else {
                return
            }
            applyAIGCMediaJobProjection(projection, confirmationID: id)
        }
    }

    private func applyAIGCMediaJobProjection(
        _ projection: AIGCMediaJobProjection,
        confirmationID: String
    ) {
        guard let index = messages.indices.first(where: {
            Self.containsAIGCMediaConfirmation(
                in: messages[$0],
                confirmationID: confirmationID
            )
        }) else { return }
        let jobData = projection.persistedCardData(title: "小巴创作")
        if messages[index].cardType == "aigc_media_confirmation" {
            messages[index].cardType = "aigc_media_job"
            messages[index].cardData = jobData
            messages[index].cardActions = []
        } else if let type = messages[index].cardType,
                  let data = messages[index].cardData,
                  let updated = Self.replacingAIGCMediaConfirmation(
                    type: type,
                    data: data,
                    confirmationID: confirmationID,
                    jobData: jobData
                  ) {
            messages[index].cardData = updated
        } else {
            return
        }
        if let resultURL = projection.resultURL {
            aigcResultURLs[projection.id] = resultURL
        } else {
            aigcResultURLs.removeValue(forKey: projection.id)
        }
        persistCurrentConversation()
        scheduleAIGCMediaRefreshIfNeeded(for: messages[index].id)
    }

    private static func containsAIGCMediaConfirmation(
        in message: AgentChatMessage,
        confirmationID: String
    ) -> Bool {
        guard let type = message.cardType, let data = message.cardData else { return false }
        if type == "aigc_media_confirmation" {
            return data["confirmation_id"]?.stringValue == confirmationID
        }
        guard type == "cards_group",
              case .array(let rawCards)? = data["cards"] else {
            return false
        }
        return rawCards
            .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
            .contains { descriptor in
                descriptor.type == "aigc_media_confirmation"
                    && descriptor.data["confirmation_id"]?.stringValue == confirmationID
            }
    }

    private static func replacingAIGCMediaConfirmation(
        type: String,
        data: AgentDynamicCardValue,
        confirmationID: String,
        jobData: AgentDynamicCardValue
    ) -> AgentDynamicCardValue? {
        guard type == "cards_group",
              case .object(var group) = data,
              case .array(let rawCards)? = group["cards"] else {
            return nil
        }
        var didUpdate = false
        group["cards"] = .array(rawCards.map { raw in
            guard !didUpdate,
                  let descriptor = AgentDynamicCardDescriptor.fromGroupValue(raw),
                  descriptor.type == "aigc_media_confirmation",
                  descriptor.data["confirmation_id"]?.stringValue == confirmationID else {
                return raw
            }
            didUpdate = true
            return AgentDynamicCardDescriptor(
                type: "aigc_media_job",
                render: descriptor.render,
                data: jobData,
                actions: []
            ).groupValue() ?? raw
        })
        return didUpdate ? .object(group) : nil
    }

    /// Commit a server-issued photo diet draft after an explicit Mac UI gesture.
    /// The action is looked up from the rendered card so arbitrary payloads can
    /// never be forged by the WebView bridge.
    public func confirmDietDraft(actionID: String) async {
        guard let dietDraftClient, !actionID.isEmpty,
              let index = messages.indices.first(where: { index in
                  Self.dietDraftAction(in: messages[index], actionID: actionID) != nil
              }),
              let action = Self.dietDraftAction(in: messages[index], actionID: actionID) else {
            return
        }
        do {
            let receipt = try await dietDraftClient.confirmDietDraft(action: action)
            guard let type = messages[index].cardType,
                  let cardData = messages[index].cardData,
                  let updated = Self.markDietDraftConfirmed(
                    type: type,
                    data: cardData,
                    actionID: actionID,
                    receipt: receipt
                  ) else { return }
            messages[index].cardData = updated
            if type == "diet_draft" {
                messages[index].cardActions = []
            }
            errorMessage = nil
            persistCurrentConversation()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private static func dietDraftAction(
        in message: AgentChatMessage,
        actionID: String
    ) -> AgentDynamicCardActionDescriptor? {
        guard let type = message.cardType else { return nil }
        if type == "diet_draft" {
            return message.cardActions.first(where: { $0.id == actionID })
        }
        guard type == "cards_group",
              case .array(let rawCards)? = message.cardData?["cards"] else {
            return nil
        }
        return rawCards
            .compactMap(AgentDynamicCardDescriptor.fromGroupValue)
            .lazy
            .filter { $0.type == "diet_draft" }
            .compactMap { $0.actions.first(where: { $0.id == actionID }) }
            .first
    }

    private static func markDietDraftConfirmed(
        type: String,
        data: AgentDynamicCardValue,
        actionID: String,
        receipt: DietDraftConfirmationReceipt
    ) -> AgentDynamicCardValue? {
        if type == "diet_draft" {
            guard case .object(var cardData) = data else { return nil }
            cardData["recorded"] = .bool(true)
            cardData["record_id"] = .int(receipt.id)
            if let message = receipt.displayMessage?.trimmingCharacters(in: .whitespacesAndNewlines), !message.isEmpty {
                cardData["receipt_message"] = .string(message)
            }
            return .object(cardData)
        }
        guard type == "cards_group",
              case .object(var group) = data,
              case .array(let rawCards)? = group["cards"] else {
            return nil
        }
        var didUpdate = false
        let updatedCards = rawCards.map { raw in
            guard let descriptor = AgentDynamicCardDescriptor.fromGroupValue(raw) else {
                return raw
            }
            guard !didUpdate,
                  descriptor.type == "diet_draft",
                  descriptor.actions.contains(where: { $0.id == actionID }),
                  let updatedData = markDietDraftConfirmed(
                    type: descriptor.type,
                    data: descriptor.data,
                    actionID: actionID,
                    receipt: receipt
                  ) else {
                return raw
            }
            didUpdate = true
            return AgentDynamicCardDescriptor(
                type: descriptor.type,
                render: descriptor.render,
                data: updatedData,
                actions: []
            ).groupValue() ?? raw
        }
        guard didUpdate else { return nil }
        group["cards"] = .array(updatedCards)
        return .object(group)
    }

    /// Consume a server-issued medication batch control. The WebView passes
    /// only the opaque action id; the model resolves the action from the
    /// persisted card and validates its kernel policy metadata before touching
    /// the write-intent API.
    public func performMedicationBatchAction(actionID: String) async {
        guard let medicationBatchClient,
              !actionID.isEmpty,
              let resolved = medicationBatchAction(actionID: actionID),
              let intentID = MedicationBatchCardProjection.intentID(for: resolved),
              medicationBatchIntentsInFlight.insert(intentID).inserted else {
            return
        }
        let expectedItemCount = messages.lazy.compactMap { message -> Int? in
            guard let descriptor = Self.dynamicCardDescriptor(for: message) else { return nil }
            return MedicationBatchCardProjection.itemCount(
                in: descriptor,
                intentID: intentID
            )
        }.first

        projectMedicationBatchPending(intentID: intentID, pending: true)
        // In-flight is transient UI state. Persisting it would strand an
        // offline restart with both controls hidden if the app quit before the
        // server response; the durable terminal projection is persisted below.
        defer { medicationBatchIntentsInFlight.remove(intentID) }

        do {
            var outcome: MedicationBatchActionOutcome
            switch resolved.action {
            case "write_intent.confirm":
                outcome = try await medicationBatchClient.confirmMedicationBatch(intentID: intentID)
            case "write_intent.dismiss":
                outcome = try await medicationBatchClient.dismissMedicationBatch(intentID: intentID)
            default:
                return
            }

            if outcome.decisionStatus == .executed,
               let expectedItemCount,
               expectedItemCount > 0,
               outcome.writeReceipts.count != expectedItemCount {
                outcome = MedicationBatchActionOutcome(
                    decisionStatus: outcome.decisionStatus,
                    writeReceipts: outcome.writeReceipts,
                    safetyAlerts: outcome.safetyAlerts,
                    reconciliationRequired: true
                )
            }

            if outcome.reconciliationRequired,
               let authoritative = await reconcileMedicationBatchTerminal(intentID: intentID) {
                outcome = authoritative
            }
            projectMedicationBatchTerminal(intentID: intentID, outcome: outcome)
            switch outcome.decisionStatus {
            case .expired:
                errorMessage = "这组用药确认已过期，没有写入；请重新发送完整药名和本次实际服量。"
            case .notWritten:
                errorMessage = "服务端未接受这次确认，没有写入；请刷新对话后重新核对。"
            case .executed where outcome.reconciliationRequired:
                errorMessage = "服务端显示确认已先完成，但逐项回执尚未同步；请刷新对话核对，系统不会重复写入。"
            case .executed, .dismissed:
                errorMessage = nil
            }
            persistCurrentConversation()
        } catch {
            projectMedicationBatchPending(intentID: intentID, pending: false)
            errorMessage = error.localizedDescription
            persistCurrentConversation()
        }
    }

    private func medicationBatchAction(
        actionID: String
    ) -> AgentDynamicCardActionDescriptor? {
        for message in messages {
            guard let descriptor = Self.dynamicCardDescriptor(for: message),
                  let action = MedicationBatchCardProjection.action(
                    in: descriptor,
                    actionID: actionID
                  ) else {
                continue
            }
            return action
        }
        return nil
    }

    private func projectMedicationBatchPending(intentID: Int, pending: Bool) {
        mapMedicationBatchCards(intentID: intentID) { descriptor in
            MedicationBatchCardProjection.settingPending(
                descriptor: descriptor,
                intentID: intentID,
                pending: pending
            )
        }
    }

    private func projectMedicationBatchTerminal(
        intentID: Int,
        outcome: MedicationBatchActionOutcome
    ) {
        mapMedicationBatchCards(intentID: intentID) { descriptor in
            MedicationBatchCardProjection.projectingTerminal(
                descriptor: descriptor,
                intentID: intentID,
                outcome: outcome
            )
        }
    }

    private func mapMedicationBatchCards(
        intentID: Int,
        transform: (AgentDynamicCardDescriptor) -> AgentDynamicCardDescriptor
    ) {
        for index in messages.indices {
            guard let descriptor = Self.dynamicCardDescriptor(for: messages[index]),
                  MedicationBatchCardProjection.targets(
                    descriptor: descriptor,
                    intentID: intentID
                  ) else {
                continue
            }
            let updated = transform(descriptor)
            messages[index].cardType = updated.type
            messages[index].cardRender = updated.render
            messages[index].cardData = updated.data
            messages[index].cardActions = updated.actions
        }
    }

    private func reconcileMedicationBatchTerminal(
        intentID: Int
    ) async -> MedicationBatchActionOutcome? {
        guard let conversationID, let remoteSource,
              let remoteMessages = try? await remoteSource.fetchDetail(
                conversationID: conversationID
              ) else {
            return nil
        }
        return remoteMessages.lazy.compactMap { message in
            guard let descriptor = Self.dynamicCardDescriptor(for: message) else { return nil }
            return MedicationBatchCardProjection.terminalOutcome(
                in: descriptor,
                intentID: intentID
            )
        }.first
    }

    private static func dynamicCardDescriptor(
        for message: AgentChatMessage
    ) -> AgentDynamicCardDescriptor? {
        guard let type = message.cardType, let data = message.cardData else { return nil }
        return AgentDynamicCardDescriptor(
            type: type,
            render: message.cardRender,
            data: data,
            actions: message.cardActions
        )
    }

    private func medicalExamImportDynamicCard(for item: LabReportImportContext) -> AgentDynamicCardDescriptor {
        var data: [String: AgentDynamicCardValue] = [
            "exam_id": .int(item.result.examID),
            "source": .string(Self.labReportCardSource(fileName: item.fileName)),
            "review_required": .bool(true),
            "safety_note": .string(Self.medicalExamImportSafetyNote)
        ]
        if let examDate = item.result.examDate {
            data["exam_date"] = .string(examDate)
        }
        if let examType = item.result.examType {
            data["exam_type"] = .string(examType)
        }
        if let hospitalName = item.result.hospitalName {
            data["hospital_name"] = .string(hospitalName)
        }
        if let itemsCount = item.result.itemsCount {
            data["items_count"] = .int(itemsCount)
        }
        if let abnormalCount = item.result.abnormalCount {
            data["abnormal_count"] = .int(abnormalCount)
        }
        if let conclusionsCount = item.result.conclusionsCount {
            data["conclusions_count"] = .int(conclusionsCount)
        }
        if let conclusion = item.result.conclusion {
            data["conclusion"] = .string(conclusion)
        }
        return AgentDynamicCardDescriptor(type: "medical_exam_import_result", data: .object(data))
    }

    private static func labReportCardSource(fileName: String) -> String {
        let ext = URL(fileURLWithPath: fileName).pathExtension.lowercased()
        if ext == "pdf" {
            return "pdf"
        }
        if ["jpg", "jpeg", "png", "heic", "webp"].contains(ext) {
            return "image"
        }
        return "text"
    }

    private static func mergedToolNames(existing: [String], incoming: [String]) -> [String] {
        var seen = Set<String>()
        var merged: [String] = []
        for tool in existing + incoming {
            let trimmed = tool.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty, seen.insert(trimmed).inserted else {
                continue
            }
            merged.append(trimmed)
        }
        return merged
    }

    /// Maps a real backend `status` stage → an L10n **key** (English fallback) plus
    /// an optional dynamic detail. The View resolves `key` through `appText`/`L10n`
    /// to the localized string; when `detail` is non-nil the key is a `%@` format
    /// string and the View interpolates the (Chinese) tool label verbatim. Keys
    /// (not raw zh) keep this on the same localization pattern as the time-based
    /// fallback copy. Unknown stages → "Reva is thinking…".
    ///
    /// Stage table (backend contract):
    /// - `vision`     → "Recognizing image…"                     (正在识别图片…)
    /// - `thinking`   → detail non-blank: the detail verbatim     (server-provided zh
    ///                  phrase, e.g. 该模型整段生成,需等待完整回答 — non-streaming
    ///                  commercial models via LangBridge). Returned as the `key` with
    ///                  `detail: nil` so the View renders it AS-IS (L10n pass-through,
    ///                  no 正在 prefix, no %@ template).
    ///                  detail nil/blank: round≥2 "Reva is organizing thoughts…" else
    ///                  "Reva is thinking…" (正在整理思路… / 小巴正在思考…)
    /// - `tool`       → detail non-nil "Working: %@…" + detail   (正在<detail>…)
    ///                  detail nil "Calling a tool…"             (正在调用工具…)
    /// - `synthesis`  → "Reva is composing a reply…"             (正在整理回答…)
    nonisolated static func statusText(stage: String, detail: String?, round: Int?) -> (key: String, detail: String?) {
        switch stage {
        case "accepted":
            // P0-1 progress family: stream just opened (before any LLM work). Gives the
            // user deterministic feedback in the 8s before the first token.
            return ("Reva received your message…", nil)
        case "vision":
            return ("Recognizing image…", nil)
        case "thinking":
            // Server-provided complete zh phrase (e.g. non-streaming commercial model
            // notice). Show verbatim: return it as `key` (L10n pass-through renders the
            // raw string) with `detail: nil` so the View skips %@ templating.
            if let detail, !detail.trimmingCharacters(in: .whitespaces).isEmpty {
                return (detail, nil)
            }
            return ((round ?? 1) >= 2 ? "Reva is organizing thoughts…" : "Reva is thinking…", nil)
        case "tool":
            if let detail, !detail.trimmingCharacters(in: .whitespaces).isEmpty {
                // detail is a Chinese tool label from the backend (e.g. 查询健康数据);
                // the View splices it into the localized template so it shows verbatim.
                return ("Working: %@…", detail)
            }
            return ("Calling a tool…", nil)
        case "synthesis":
            return ("Reva is composing a reply…", nil)
        default:
            return ("Reva is thinking…", nil)
        }
    }

    public nonisolated static func liveThinkingStep(stage: String, detail: String?, round: Int?) -> String? {
        let normalizedStage = stage.trimmingCharacters(in: .whitespacesAndNewlines)
        guard ["accepted", "vision", "thinking", "tool", "synthesis"].contains(normalizedStage) else {
            return nil
        }
        return visibleThinkingStepText(statusText(stage: normalizedStage, detail: detail, round: round))
    }

    private nonisolated static func visibleThinkingStepText(_ step: ThinkingStep) -> String {
        visibleThinkingStepText((key: step.labelKey, detail: step.labelDetail))
    }

    private nonisolated static func visibleThinkingStepText(_ mapped: (key: String, detail: String?)) -> String {
        if mapped.key == "Working: %@…", let detail = mapped.detail {
            return "正在\(detail)"
        }
        switch mapped.key {
        case "Reva received your message…":
            return "正在理解你的问题"
        case "Recognizing image…":
            return "识别图片中"
        case "Reva is thinking…":
            return "正在思考"
        case "Reva is organizing thoughts…":
            return "整理思路"
        case "Calling a tool…":
            return "调用工具中"
        case "Reva is composing a reply…":
            return "整理回复中"
        default:
            return mapped.key
        }
    }

    private nonisolated static func chatImageType(for url: URL) -> String {
        let ext = url.pathExtension.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch ext {
        case "jpg", "jpeg":
            return "jpeg"
        case "heic":
            return "heic"
        case "webp":
            return "webp"
        default:
            return ext.isEmpty ? "png" : ext
        }
    }

    private static let medicalExamImportSafetyNote = "OCR/AI 解析结果需要复核后再用于判断。"

    private static let desktopMarkdownResponseInstruction = """
    请用适合桌面阅读的中文 Markdown 回复：先给 2-3 条关键结论；按问题完整展开必要的证据、风险边界和下一步，不要因篇幅主动截断；再用二级/三级标题分段；比较或分项判断优先用表格；行动建议用编号列表；关键数值和结论加粗。每段最多 3 行，标题、段落、列表之间必须留空行。不要输出密集长段落，不要用长破折号把所有判断串成一段。最后必须包含「不确定性边界」和「下一步」；不要把基因风险当诊断，不要直接给用药决定。若需要执行结构化动作，自然语言说明后再给可确认动作。
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
