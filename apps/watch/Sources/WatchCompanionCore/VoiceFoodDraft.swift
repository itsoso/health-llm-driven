import Foundation

/// `/diet/voice/parse` 返回的腕上确认草稿。Watch 只能先解析,用户确认后才发 `/diet/records` 入库。
public struct VoiceFoodDraft: Codable, Equatable, Sendable {
    public let rawText: String
    public let mealType: String
    public let mealTypeLabel: String
    public let foods: [VoiceFoodDraftItem]
    public let confidence: Double
    public let needsConfirmation: Bool
    public let clarifyingQuestion: String?
    public let riskTags: [String]
    public let parserVersion: String

    enum CodingKeys: String, CodingKey {
        case rawText = "raw_text"
        case mealType = "meal_type"
        case mealTypeLabel = "meal_type_label"
        case foods, confidence
        case needsConfirmation = "needs_confirmation"
        case clarifyingQuestion = "clarifying_question"
        case riskTags = "risk_tags"
        case parserVersion = "parser_version"
    }

    public static func decode(_ data: Data) throws -> VoiceFoodDraft {
        try JSONDecoder().decode(VoiceFoodDraft.self, from: data)
    }

    public var foodLine: String {
        let text = foods.map(\.displayText).joined(separator: ", ")
        return text.isEmpty ? rawText : text
    }

    public var summaryLine: String {
        "\(mealTypeLabel): \(foodLine)"
    }

    public func confirmRequest(recordDate: String) -> QuickRecordRequest {
        var body: [String: String] = [
            "record_date": recordDate,
            "meal_type": mealType,
            "food_items": foodLine,
            "ai_recognized": "true",
            "source": "apple_watch",
        ]

        if let value = total(\.calories) { body["calories"] = Self.format(value) }
        if let value = total(\.protein) { body["protein"] = Self.format(value) }
        if let value = total(\.carbs) { body["carbs"] = Self.format(value) }
        if let value = total(\.fat) { body["fat"] = Self.format(value) }

        var notes = ["Watch 语音草稿: \(rawText)"]
        if let clarifyingQuestion, !clarifyingQuestion.isEmpty {
            notes.append("待确认: \(clarifyingQuestion)")
        }
        if !riskTags.isEmpty {
            notes.append("风险标签: \(riskTags.joined(separator: ","))")
        }
        body["notes"] = notes.joined(separator: " | ")

        return QuickRecordRequest(
            path: "/diet/records",
            method: "POST",
            query: [:],
            body: body,
            resultKind: .saved,
            successMessage: "已记录饮食"
        )
    }

    private func total(_ keyPath: KeyPath<VoiceFoodDraftItem, Double?>) -> Double? {
        let values = foods.compactMap { $0[keyPath: keyPath] }
        guard !values.isEmpty else { return nil }
        return values.reduce(0, +)
    }

    private static func format(_ value: Double) -> String {
        let rounded = (value * 10).rounded() / 10
        if rounded == rounded.rounded() {
            return String(Int(rounded))
        }
        return String(format: "%.1f", rounded)
    }
}

public struct VoiceFoodDraftItem: Codable, Equatable, Sendable {
    public let name: String
    public let amount: String?
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?

    public var displayText: String {
        let trimmed = amount?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? name : "\(name) \(trimmed)"
    }
}
