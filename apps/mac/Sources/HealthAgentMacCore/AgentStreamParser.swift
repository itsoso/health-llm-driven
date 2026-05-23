import Foundation

public enum AgentStreamEvent: Equatable, Sendable {
    case token(String)
    case done(conversationID: Int?, messageID: Int?, completionStatus: String?)
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
                guard
                    let eventLine = lines.first(where: { $0.hasPrefix("event:") }),
                    let dataLine = lines.first(where: { $0.hasPrefix("data:") })
                else {
                    return nil
                }

                let event = eventLine.replacingOccurrences(of: "event:", with: "").trimmingCharacters(in: .whitespaces)
                let dataText = dataLine.replacingOccurrences(of: "data:", with: "").trimmingCharacters(in: .whitespaces)
                let data = Data(dataText.utf8)
                let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]

                switch event {
                case "token":
                    return .token(json?["content"] as? String ?? "")
                case "done":
                    return .done(
                        conversationID: json?["conversation_id"] as? Int,
                        messageID: json?["message_id"] as? Int,
                        completionStatus: json?["completion_status"] as? String
                    )
                case "error":
                    return .error(json?["message"] as? String ?? "Unknown stream error")
                default:
                    return nil
                }
            }
    }
}
