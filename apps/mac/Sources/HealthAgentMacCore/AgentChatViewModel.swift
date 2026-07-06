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
        cardType: String? = nil,
        cardRender: AgentDynamicCardRenderDescriptor? = nil,
        cardData: AgentDynamicCardValue? = nil,
        cardActions: [AgentDynamicCardActionDescriptor] = [],
        remoteImageURLs: [String] = []
    ) {
        self.id = id
        self.role = role
        self.content = content
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
    }

    // 显式 Codable:历史快照(老版本无这些字段)用 decodeIfPresent 容错;数组缺失 → 空。
    private enum CodingKeys: String, CodingKey {
        case id, role, content, remoteImageURLs, model, selectedModel, answerModel, toolModels, fallbackReasons, elapsedMs, llmRounds, llmUsage, sourcesUsed, toolsUsed, completionStatus, perf, cardType, cardRender, cardData, cardActions
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
        let out: String
        if segments.contains(where: { if case .revaUI = $0 { return true } else { return false } }) {
            var pieces: [String] = []
            for segment in segments {
                switch segment {
                case .revaUI(let rawJSON):
                    // 原样重建闭合围栏(split 切掉了围栏标记本身,这里补回)。
                    pieces.append("```reva-ui\n" + rawJSON + "\n```")
                case .markdown(let text):
                    let cleaned = cleanDisplayLines(text)
                    if !cleaned.isEmpty { pieces.append(cleaned) }
                }
            }
            out = pieces.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        } else {
            out = cleanDisplayLines(result)
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

@Observable
@MainActor
public final class AgentChatViewModel {
    public var isStreaming = false
    private var streamingTask: Task<Void, Never>?
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
    @ObservationIgnored private var _transcriptCacheProposed: [AgentProposedAction] = []

    /// Set when the backend history list/detail fetch fell back to the local
    /// cache (offline / 401 / server error). The UI surfaces this so a stale
    /// local view is never silently presented as authoritative. nil = backend
    /// data is current.
    public var historyNotice: String?
    /// True while a backend history list or detail fetch is in flight.
    public var isLoadingHistory = false

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
        labUploadService: LabUploadServicing? = nil
    ) {
        self.selectedModelID = selectedModelID
        self.streamService = streamService
        self.contextBundleStore = contextBundleStore
        self.conversationStore = conversationStore
        self.remoteSource = remoteSource
        self.labUploadService = labUploadService
        self.savedContextBundles = contextBundleStore?.loadContextBundles() ?? []
        // Seed from the local cache so the list isn't empty before the first
        // backend fetch returns; `refreshConversationHistory()` replaces it.
        self.conversationHistory = conversationStore?.loadConversations() ?? []
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

    /// Fire-and-forget entry point for the UI: wraps `send` in a tracked Task so
    /// the composer's Stop button can cancel an in-flight stream via
    /// `cancelStreaming()`. Cancelling the task unwinds the `for try await` loop,
    /// which terminates the AsyncThrowingStream and cancels the URLSession task.
    public func submit(_ text: String) {
        streamingTask?.cancel()
        streamingTask = Task { [weak self] in
            await self?.send(text)
        }
    }

    /// Stops the current stream. Partial content already received stays on screen
    /// (send()'s CancellationError path leaves isStreaming=false without wiping it).
    public func cancelStreaming() {
        streamingTask?.cancel()
        streamingTask = nil
        isStreaming = false
        clearLiveStatus()
    }

    public func send(_ text: String) async {
        let message = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, let streamService else {
            return
        }

        errorMessage = nil
        toolActivities = []
        clearLiveStatus()
        isStreaming = true
        runState = .preparing
        lastPrompt = message
        messages.append(.init(role: .user, content: message))
        messages.append(.init(role: .assistant, content: ""))
        // Track the streaming assistant message by its stable id, not a captured
        // index: New Chat / loading a conversation / sending again resets `messages`
        // mid-stream, which would make a captured index stale and crash on next token.
        let assistantID = messages[messages.index(before: messages.endIndex)].id

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
                extraContext: buildExtraContext()
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
                case .token(let content):
                    runState = .streaming
                    // First real token → drop the live status line; the transcript
                    // now streams actual content and ThinkingStatusLine is torn down.
                    clearLiveStatus()
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
                case .done(let id, _, let completionStatus, let model, let selectedModel, let answerModel, let toolModels, let fallbackReasons, let sourcesUsed, let toolsUsed, let elapsedMs, let llmRounds, let cards, let perf, let llmUsage):
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
                        // perf 缺失(老后端)→ 保留 nil,footer 行为不变。
                        if let perf { messages[idx].perf = perf }
                        if messages[idx].cardType == nil, let firstCard = cards.first {
                            messages[idx].cardType = firstCard.type
                            messages[idx].cardRender = firstCard.render
                            messages[idx].cardData = firstCard.data
                            messages[idx].cardActions = firstCard.actions
                        }
                    }
                    livePreLLMPerf = nil
                    clearLiveStatus()
                    runState = .completed
                case .error(let message):
                    errorMessage = message
                    clearLiveStatus()
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
        labReportImports = []
        contextItems = []
        preparedDraft = nil
        clearLiveStatus()
    }

    /// Refreshes the history list from the backend (`GET /agent/conversations`),
    /// matching web/mobile. On success the backend list becomes authoritative and
    /// is written to the local cache as an offline fallback. On failure (offline /
    /// 401 / 5xx) the existing cache is kept and `historyNotice` is set so the UI
    /// can tell the user it's showing a possibly-stale local copy — never silently
    /// cleared. No-op when no remote source is wired (e.g. unit tests, previews).
    public func refreshConversationHistory(limit: Int = 30) async {
        guard let remoteSource else { return }
        isLoadingHistory = true
        defer { isLoadingHistory = false }
        do {
            let remote = try await remoteSource.fetchConversations(limit: limit, offset: 0)
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
            conversationStore?.saveConversations(merged)
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
            // 401 already cleared the token + posted authSessionExpired; the app
            // root drops to login. Keep the cache visible meanwhile.
            historyNotice = "登录已过期，下面是本地缓存的历史。"
        } catch {
            AppLogger.agent.error("conversation history refresh failed: \(error.localizedDescription, privacy: .public)")
            historyNotice = "离线或服务不可用，显示本地缓存的历史。"
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
        conversationStore?.saveConversations(conversationHistory)
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

    /// WebView transcript 喂入的安全 HTML 信封(带内容缓存,见上面缓存字段说明)。
    /// 在 View.body 里调用:读 messages/isStreaming/proposedActions 建立 Observation 依赖,
    /// 这三者真正变化才重渲;打字(只改 View 的 draft)命中缓存,不再每键重 parse markdown。
    /// 流式中的最后一条助手消息走 plain text(streaming=true);其余走富 markdown。
    public func renderedTranscript() -> [ChatTranscriptHTML.RenderedMessage] {
        if isStreaming == _transcriptCacheStreaming
            && messages == _transcriptCacheMessages
            && proposedActions == _transcriptCacheProposed {
            return _transcriptCache
        }
        let lastID = messages.last?.id
        let rendered = messages.compactMap { message -> ChatTranscriptHTML.RenderedMessage? in
            let isStreamingThis = isStreaming && message.id == lastID && message.role == .assistant
            let content = displayContent(for: message)
            let cardHTML = message.role == .assistant
                ? ChatTranscriptHTML.dynamicCardHTML(
                    type: message.cardType,
                    render: message.cardRender,
                    data: message.cardData,
                    actions: message.cardActions
                ) ?? ""
                : ""
            // Pre-first-token: while the streaming assistant reply has no text (and
            // no dynamic card yet), skip emitting its bubble entirely so the WebView
            // shows nothing — the SwiftUI ThinkingStatusLine ("正在整理思路…") is the
            // sole waiting cue. Without this the empty bubble renders a lone clay
            // caret block AND the status line stacked = redundant/alarming. Once the
            // first token arrives, content is non-empty → the bubble renders normally
            // with the trailing caret. Completed messages are unaffected.
            if isStreamingThis && content.isEmpty && cardHTML.isEmpty {
                return nil
            }
            let bodyHTML: String
            if message.role == .user {
                // 用户消息纯文本:转义 + 换行保留,不解析 markdown。
                bodyHTML = "<p class=\"streaming-text\">" + ChatTranscriptHTML.escape(content) + "</p>"
                    + ChatTranscriptHTML.imageGalleryHTML(urls: message.remoteImageURLs)
            } else if isStreamingThis {
                // 流式态:plain 文本(避免每 60ms 用更长全文重 parse markdown 的 O(n²))。
                bodyHTML = cardHTML + "<div class=\"streaming-text\">" + ChatTranscriptHTML.escape(content) + "</div>"
            } else {
                let textHTML = content.isEmpty ? "" : ChatTranscriptHTML.renderMessageBody(markdown: content)
                bodyHTML = cardHTML + textHTML
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
            return ChatTranscriptHTML.RenderedMessage(
                id: message.id.uuidString,
                role: message.role == .user ? "user" : "assistant",
                bodyHTML: bodyHTML,
                isStreaming: isStreamingThis,
                showCopy: showCopy,
                footerHTML: footerHTML
            )
        }
        _transcriptCacheMessages = messages
        _transcriptCacheStreaming = isStreaming
        _transcriptCacheProposed = proposedActions
        _transcriptCache = rendered
        return rendered
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

    /// Clears the real-stage live status (both key and dynamic detail) so the
    /// ThinkingStatusLine falls back to its time-based rotation until the next
    /// `status` event, and no stale label survives into the next turn.
    private func clearLiveStatus() {
        liveStatusText = nil
        liveStatusDetail = nil
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
            let result = try await labUploadService.importReport(fileURL: attachment.url)
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
        messages[idx].cardData = card.data
        messages[idx].cardActions = card.actions
        if let toolName {
            messages[idx].toolsUsed = Self.mergedToolNames(
                existing: messages[idx].toolsUsed,
                incoming: [toolName]
            )
        }
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

    private static let medicalExamImportSafetyNote = "OCR/AI 解析结果需要复核后再用于判断。"

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
