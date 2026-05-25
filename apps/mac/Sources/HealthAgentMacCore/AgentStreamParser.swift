import Foundation

public enum AgentStreamEvent: Equatable, Sendable {
    case start(conversationID: Int?)
    case token(String)
    case tool(name: String?, success: Bool?)
    case toolDetails(AgentToolEvent)
    case done(conversationID: Int?, messageID: Int?, completionStatus: String?, model: String?, sourcesUsed: [String])
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
                        sourcesUsed: eventData?["sources_used"] as? [String] ?? []
                    )
                case "error":
                    return .error(eventData?["message"] as? String ?? "Unknown stream error")
                default:
                    return nil
                }
            }
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
}
