import Foundation

public enum WatchAskError: Error, Equatable, Sendable {
    case missingText
    case textTooLong
}

public struct WatchAskRequest: Equatable, Sendable {
    public static let maxTextLength = 500

    public let text: String

    public init(text: String) throws {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { throw WatchAskError.missingText }
        guard trimmed.count <= Self.maxTextLength else { throw WatchAskError.textTooLong }
        self.text = trimmed
    }

    public var body: [String: String] {
        ["text": text]
    }
}

public enum WatchAskDisplayTone: String, Equatable, Sendable {
    case normal
    case caution
    case risk
}

public struct WatchAskResponse: Codable, Equatable, Sendable {
    public let answer: String
    public let escalateToPhone: Bool
    public let requiresMedicalAttention: Bool

    enum CodingKeys: String, CodingKey {
        case answer
        case escalateToPhone = "escalate_to_phone"
        case requiresMedicalAttention = "requires_medical_attention"
    }

    public init(answer: String, escalateToPhone: Bool, requiresMedicalAttention: Bool) {
        self.answer = answer
        self.escalateToPhone = escalateToPhone
        self.requiresMedicalAttention = requiresMedicalAttention
    }

    public static func decode(_ data: Data) throws -> WatchAskResponse {
        try JSONDecoder().decode(WatchAskResponse.self, from: data)
    }

    public var displayTone: WatchAskDisplayTone {
        if requiresMedicalAttention { return .risk }
        if escalateToPhone { return .caution }
        return .normal
    }
}
