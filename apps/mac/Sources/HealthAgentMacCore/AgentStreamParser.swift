import Foundation

public enum AgentStreamEvent: Equatable, Sendable {
    case start(conversationID: Int?)
    case token(String)
    case tool(name: String?, success: Bool?)
    case toolDetails(AgentToolEvent)
    case done(
        conversationID: Int?,
        messageID: Int?,
        completionStatus: String?,
        model: String?,
        selectedModel: String? = nil,
        answerModel: String? = nil,
        toolModels: [String] = [],
        fallbackReasons: [String] = [],
        sourcesUsed: [String],
        toolsUsed: [String],
        elapsedMs: Int?,
        llmRounds: Int?,
        cards: [AgentDynamicCardDescriptor] = []
    )
    case error(String)
}

public struct AgentToolEvent: Equatable, Sendable {
    public let name: String?
    public let success: Bool?
    public let arguments: String?
    public let preview: String?
    public let result: String?
    public let round: Int?

    public init(
        name: String?,
        success: Bool?,
        arguments: String?,
        preview: String?,
        result: String?,
        round: Int?
    ) {
        self.name = name
        self.success = success
        self.arguments = arguments
        self.preview = preview
        self.result = result
        self.round = round
    }
}

public enum AgentStreamParser {
    public static func parse(_ payload: String) throws -> [AgentStreamEvent] {
        try payload
            .components(separatedBy: "\n\n")
            .compactMap { block -> AgentStreamEvent? in
                let lines = block
                    .split(separator: "\n", omittingEmptySubsequences: true)
                    .map(String.init)
                guard let dataLine = lines.first(where: { $0.hasPrefix("data:") }) else {
                    return nil
                }

                let dataText = dataLine.replacingOccurrences(of: "data:", with: "").trimmingCharacters(in: .whitespaces)
                if dataText == "[DONE]" {
                    return nil
                }
                let data = Data(dataText.utf8)
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
                let explicitEvent = lines
                    .first(where: { $0.hasPrefix("event:") })?
                    .replacingOccurrences(of: "event:", with: "")
                    .trimmingCharacters(in: .whitespaces)
                let event = explicitEvent ?? json?["event"] as? String
                let eventData = (json?["data"] as? [String: Any]) ?? json

                switch event {
                case "agent_start":
                    return .start(conversationID: eventData?["conversation_id"] as? Int)
                case "token":
                    return .token(eventData?["content"] as? String ?? "")
                case "tool_call":
                    return .toolDetails(AgentToolEvent(
                        name: eventData?["tool"] as? String,
                        success: nil,
                        arguments: normalizedJSONString(eventData?["args"]),
                        preview: nil,
                        result: nil,
                        round: eventData?["round"] as? Int
                    ))
                case "tool_result":
                    return .toolDetails(AgentToolEvent(
                        name: eventData?["tool"] as? String,
                        success: eventData?["success"] as? Bool,
                        arguments: normalizedJSONString(eventData?["args"]),
                        preview: eventData?["preview"] as? String,
                        result: eventData?["result"] as? String,
                        round: eventData?["round"] as? Int
                    ))
                case "done":
                    return .done(
                        conversationID: eventData?["conversation_id"] as? Int,
                        messageID: eventData?["message_id"] as? Int,
                        completionStatus: eventData?["completion_status"] as? String,
                        model: eventData?["model"] as? String,
                        selectedModel: eventData?["selected_model"] as? String,
                        answerModel: eventData?["answer_model"] as? String,
                        toolModels: stringArray(eventData?["tool_models"]),
                        fallbackReasons: stringArray(eventData?["fallback_reasons"]),
                        sourcesUsed: stringArray(eventData?["sources_used"]),
                        // tools_used 由并发任务在后端补;未上线前缺失 → 解析为空数组,
                        // ViewModel/footer 容错(空则不显示该块)。
                        toolsUsed: stringArray(eventData?["tools_used"]),
                        elapsedMs: eventData?["elapsed_ms"] as? Int,
                        llmRounds: eventData?["llm_rounds"] as? Int,
                        cards: cardDescriptors(
                            cards: eventData?["cards"],
                            cardType: eventData?["card_type"],
                            cardData: eventData?["card_data"]
                        )
                    )
                case "error":
                    return .error(eventData?["message"] as? String ?? "Unknown stream error")
                default:
                    return nil
                }
            }
    }

    /// 把任意 JSON 值容错地归一为 [String]:已是 [String] 直接用;[Any] 逐项转字符串
    /// (过滤空白);其它(nil / 非数组)→ 空数组。后端字段缺失或类型漂移都不崩。
    private static func stringArray(_ value: Any?) -> [String] {
        if let strings = value as? [String] {
            return strings.filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
        }
        if let items = value as? [Any] {
            return items.compactMap { item in
                let text = (item as? String) ?? String(describing: item)
                let trimmed = text.trimmingCharacters(in: .whitespaces)
                return trimmed.isEmpty ? nil : trimmed
            }
        }
        return []
    }

    private static func normalizedJSONString(_ value: Any?) -> String? {
        guard let value else { return nil }
        if let string = value as? String {
            return string
        }
        if JSONSerialization.isValidJSONObject(value),
           let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]),
           let string = String(data: data, encoding: .utf8) {
            return string
        }
        return String(describing: value)
    }

    private static func cardDescriptors(
        cards: Any?,
        cardType: Any?,
        cardData: Any?
    ) -> [AgentDynamicCardDescriptor] {
        var descriptors = decodeCards(cards)
        if descriptors.isEmpty,
           let type = cardType as? String,
           let data = decodeCardValue(cardData) {
            descriptors = [AgentDynamicCardDescriptor(type: type, data: data)]
        }
        return descriptors
    }

    private static func decodeCards(_ value: Any?) -> [AgentDynamicCardDescriptor] {
        guard let value,
              JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else {
            return []
        }
        return (try? JSONDecoder().decode([AgentDynamicCardDescriptor].self, from: data)) ?? []
    }

    private static func decodeCardValue(_ value: Any?) -> AgentDynamicCardValue? {
        guard let value else {
            return nil
        }
        if let string = value as? String,
           let data = string.data(using: .utf8),
           let decoded = try? JSONDecoder().decode(AgentDynamicCardValue.self, from: data) {
            return decoded
        }
        guard JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else {
            return nil
        }
        return try? JSONDecoder().decode(AgentDynamicCardValue.self, from: data)
    }
}
