import Foundation

public enum AgentStreamEvent: Equatable, Sendable {
    case start(conversationID: Int?)
    case token(String)
    case tool(name: String?, success: Bool?)
    case done(conversationID: Int?, messageID: Int?, completionStatus: String?, model: String?, sourcesUsed: [String])
    case error(String)
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
                    return .tool(name: eventData?["tool"] as? String, success: nil)
                case "tool_result":
                    return .tool(name: eventData?["tool"] as? String, success: eventData?["success"] as? Bool)
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
}
