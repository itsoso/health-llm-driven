import Foundation

public typealias TodayDynamicTrigger = String

public struct TodayDynamicSection: Codable, Equatable, Sendable {
    public let slot: String
    public let priority: Int
    public let title: String?
    public let cards: [AgentDynamicCardDescriptor]

    public init(slot: String, priority: Int, title: String? = nil, cards: [AgentDynamicCardDescriptor]) {
        self.slot = slot
        self.priority = priority
        self.title = title
        self.cards = cards
    }
}

public struct TodayDynamicView: Codable, Equatable, Sendable {
    public let viewID: String
    public let surface: String
    public let trigger: String
    public let generatedBy: String
    public let contextHash: String
    public let safetyBoundary: String?
    public let sections: [TodayDynamicSection]

    public init(
        viewID: String,
        surface: String,
        trigger: String,
        generatedBy: String,
        contextHash: String,
        safetyBoundary: String?,
        sections: [TodayDynamicSection]
    ) {
        self.viewID = viewID
        self.surface = surface
        self.trigger = trigger
        self.generatedBy = generatedBy
        self.contextHash = contextHash
        self.safetyBoundary = safetyBoundary
        self.sections = sections
    }

    private enum CodingKeys: String, CodingKey {
        case viewID = "view_id"
        case surface
        case trigger
        case generatedBy = "generated_by"
        case contextHash = "context_hash"
        case safetyBoundary = "safety_boundary"
        case sections
    }
}

public protocol TodayDynamicViewServicing: Sendable {
    func fetchTodayDynamicView(trigger: TodayDynamicTrigger) async throws -> TodayDynamicView
}

public final class TodayDynamicViewClient: TodayDynamicViewServicing, @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchTodayDynamicView(trigger: TodayDynamicTrigger = "open") async throws -> TodayDynamicView {
        try await apiClient.post("dynamic-views/today", body: TodayDynamicViewRequest(trigger: trigger))
    }
}

private struct TodayDynamicViewRequest: Encodable, Sendable {
    let surface = "mobile.today"
    let trigger: String
    let clientContext: [String: AgentDynamicCardValue]

    init(trigger: String) {
        self.trigger = trigger
        self.clientContext = [
            "client": .string("mac"),
            "client_capabilities": .array([
                .string("daily_artifact"),
                .string("runtime_agenda")
            ])
        ]
    }

    private enum CodingKeys: String, CodingKey {
        case surface
        case trigger
        case clientContext = "client_context"
    }
}

public extension TodayDynamicView {
    var menuBarActions: [DailyPlanAction] {
        var seen = Set<String>()
        var actions: [DailyPlanAction] = []
        for card in sections
            .sorted(by: { $0.priority > $1.priority })
            .flatMap(\.cards) {
            guard let action = Self.menuAction(from: card) else {
                continue
            }
            let key = Self.titleKey(action.title)
            guard seen.insert(key).inserted else {
                continue
            }
            actions.append(action)
            if actions.count >= 3 {
                break
            }
        }
        return actions
    }

    private static func menuAction(from card: AgentDynamicCardDescriptor) -> DailyPlanAction? {
        let atom = card.render?.atom ?? card.type
        switch atom {
        case "daily_artifact":
            return action(from: card.data["top_action"], domain: "daily_artifact")
        case "runtime_agenda":
            return action(from: card.data["next_action"], domain: "runtime_agenda")
        default:
            return nil
        }
    }

    private static func action(from value: AgentDynamicCardValue?, domain: String) -> DailyPlanAction? {
        guard let title = cleanText(value?["title"]?.stringValue) else {
            return nil
        }
        let id = cleanText(value?["id"]?.stringValue) ?? titleKey(title)
        return DailyPlanAction(actionKey: "\(domain)-\(id)", title: title, domain: domain)
    }

    private static func cleanText(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func titleKey(_ value: String) -> String {
        value
            .lowercased()
            .filter { !$0.isWhitespace && !["，", ",", "。", ".", ":", "：", ";", "；"].contains(String($0)) }
    }
}
