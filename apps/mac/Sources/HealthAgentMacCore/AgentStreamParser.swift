import Foundation

public enum AgentStreamEvent: Equatable, Sendable {
    case start(conversationID: Int?)
    case token(String)
    case tool(name: String?, success: Bool?)
    case toolDetails(AgentToolEvent)
    /// Real backend progress stage (`status` event). Arrives zero-or-more times
    /// BEFORE the first `token` (vision / thinking / tool / synthesis). Optional —
    /// old backends never emit it, in which case the UI keeps its time-based
    /// "thinking…" fallback. All fields tolerate absence.
    case status(stage: String, detail: String?, round: Int?)
    /// Mid-stream perf hint (`perf_pre_llm`): arrives right when prompt assembly
    /// finishes, before the first token. Optional — old backends never emit it.
    /// The main waterfall renders from the final `done.perf`; this is only a live
    /// "assembling…" signal.
    case perfPreLLM(preLLMMs: Int?, stages: MessagePerf.PreLLMStages?)
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
        cards: [AgentDynamicCardDescriptor] = [],
        // Per-answer stage-timing perf. Absent on old backends → nil → footer
        // renders unchanged (full back-compat).
        perf: MessagePerf? = nil,
        llmUsage: LLMUsageProfile? = nil,
        // Safe progress summaries (`done.thinking_steps`). The authoritative,
        // persisted list of "思考过程" steps for this turn. Absent on old backends
        // → empty → the collapsible trace simply isn't rendered.
        thinkingSteps: [String] = [],
        // Exact terminal truth for one medication write-intent. This remains
        // namespaced because top-level receipts/alerts may also contain
        // unrelated writes from the same assistant turn.
        medicationBatchDecision: AgentMedicationBatchDecision? = nil
    )
    case error(String)
}

public struct AgentMedicationBatchDecision: Equatable, Sendable {
    public let intentID: Int
    public let status: MedicationBatchDecisionStatus
    public let writeReceipts: [AgentDynamicCardValue]
    public let safetyAlerts: [AgentDynamicCardValue]

    public init(
        intentID: Int,
        status: MedicationBatchDecisionStatus,
        writeReceipts: [AgentDynamicCardValue],
        safetyAlerts: [AgentDynamicCardValue]
    ) {
        self.intentID = intentID
        self.status = status
        self.writeReceipts = writeReceipts
        self.safetyAlerts = safetyAlerts
    }
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
                // P0-1 进度事件 (flat 契约) 用顶层 `type` 而非 `event` 区分:
                //   {"type":"status","stage":"accepted"} / {"type":"status","stage":"tool",...}
                // 既有事件仍用 `event`。二者都归一到 `event`, 让 switch 复用同一 case。
                let flatType = json?["type"] as? String
                let event = explicitEvent ?? json?["event"] as? String ?? flatType
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
                case "status":
                    // Two `status` families both land here:
                    //  1) legacy thinking-process: {"event":"status","data":{stage,detail,round}}
                    //  2) P0-1 progress (flat):     {"type":"status","stage","round"?,"label"?}
                    // `stage` is required either way; missing → ignore (unknown event).
                    // The progress family carries a full human `label` (e.g. "查看健康数据…");
                    // fold it into `detail` so the existing detail-rendering path surfaces it,
                    // preferring `label` when present. `detail` / `round` are optional.
                    guard let stage = eventData?["stage"] as? String,
                          !stage.trimmingCharacters(in: .whitespaces).isEmpty else {
                        return nil
                    }
                    let rawDetail = (eventData?["label"] as? String) ?? (eventData?["detail"] as? String)
                    let detail = rawDetail
                        .flatMap { $0.trimmingCharacters(in: .whitespaces).isEmpty ? nil : $0 }
                    return .status(
                        stage: stage,
                        detail: detail,
                        round: eventData?["round"] as? Int
                    )
                case "perf_pre_llm":
                    return .perfPreLLM(
                        preLLMMs: eventData?["pre_llm_ms"] as? Int,
                        stages: decode(MessagePerf.PreLLMStages.self, from: eventData?["stages"])
                    )
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
                        ),
                        // perf absent on old backends → nil → footer unchanged.
                        perf: decode(MessagePerf.self, from: eventData?["perf"]),
                        llmUsage: decode(LLMUsageProfile.self, from: eventData?["llm_usage"]),
                        // thinking_steps absent on old backends → [] → no trace.
                        thinkingSteps: stringArray(eventData?["thinking_steps"]),
                        medicationBatchDecision: medicationBatchDecision(
                            eventData?["medication_batch_decision"],
                            legacyWriteReceipts: eventData?["write_receipts"],
                            legacySafetyAlerts: eventData?["safety_alerts"]
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

    /// Bridges a `JSONSerialization`-produced value (dict / array) back into a
    /// `Codable` type by re-serializing and decoding. Returns nil on any mismatch
    /// (missing object, non-JSON value, decode failure) so a malformed / absent
    /// `perf` never crashes the stream — it just renders the plain footer.
    private static func decode<T: Decodable>(_ type: T.Type, from value: Any?) -> T? {
        guard let value,
              !(value is NSNull),
              JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value) else {
            return nil
        }
        return try? JSONDecoder().decode(T.self, from: data)
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

    private static func medicationBatchDecision(
        _ value: Any?,
        legacyWriteReceipts: Any?,
        legacySafetyAlerts: Any?
    ) -> AgentMedicationBatchDecision? {
        guard let decision = value as? [String: Any],
              let intentID = decision["intent_id"] as? Int,
              intentID > 0,
              let rawStatus = decision["status"] as? String,
              let status = MedicationBatchDecisionStatus(rawValue: rawStatus),
              status == .executed || status == .dismissed || status == .expired else {
            return nil
        }
        let writeReceiptSource = decision.keys.contains("write_receipts")
            ? decision["write_receipts"]
            : legacyWriteReceipts
        let safetyAlertSource = decision.keys.contains("safety_alerts")
            ? decision["safety_alerts"]
            : legacySafetyAlerts
        return AgentMedicationBatchDecision(
            intentID: intentID,
            status: status,
            writeReceipts: status == .executed
                ? decodeCardValues(writeReceiptSource)
                : [],
            safetyAlerts: status == .executed
                ? decodeCardValues(safetyAlertSource)
                : []
        )
    }

    private static func decodeCardValues(_ value: Any?) -> [AgentDynamicCardValue] {
        guard let value,
              JSONSerialization.isValidJSONObject(value),
              let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) else {
            return []
        }
        return (try? JSONDecoder().decode([AgentDynamicCardValue].self, from: data)) ?? []
    }
}
