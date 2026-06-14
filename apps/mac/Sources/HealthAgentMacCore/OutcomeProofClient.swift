import Foundation

public struct ProgressDashboard: Decodable, Equatable, Sendable {
    public let stats: ProgressStats
    public let closedCards: [ProgressCard]
    public let verifyingCards: [ProgressCard]

    public init(
        stats: ProgressStats = ProgressStats(),
        closedCards: [ProgressCard] = [],
        verifyingCards: [ProgressCard] = []
    ) {
        self.stats = stats
        self.closedCards = closedCards
        self.verifyingCards = verifyingCards
    }

    enum CodingKeys: String, CodingKey {
        case stats
        case closedCards = "closed_cards"
        case verifyingCards = "verifying_cards"
    }
}

public struct ProgressStats: Decodable, Equatable, Sendable {
    public let totalSurfaced: Int
    public let graded: Int
    public let improved: Int
    public let improvementRate: Double?

    public init(
        totalSurfaced: Int = 0,
        graded: Int = 0,
        improved: Int = 0,
        improvementRate: Double? = nil
    ) {
        self.totalSurfaced = totalSurfaced
        self.graded = graded
        self.improved = improved
        self.improvementRate = improvementRate
    }

    enum CodingKeys: String, CodingKey {
        case totalSurfaced = "total_surfaced"
        case graded
        case improved
        case improvementRate = "improvement_rate"
    }
}

public struct ProgressCard: Decodable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let outcome: String?
    public let metricKey: String?
    public let baselineValue: String?
    public let actualValue: String?

    public init(
        id: Int,
        title: String,
        outcome: String? = nil,
        metricKey: String? = nil,
        baselineValue: String? = nil,
        actualValue: String? = nil
    ) {
        self.id = id
        self.title = title
        self.outcome = outcome
        self.metricKey = metricKey
        self.baselineValue = baselineValue
        self.actualValue = actualValue
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case outcome
        case metricKey = "metric_key"
        case baselineValue = "baseline_value"
        case actualValue = "actual_value"
    }
}

public struct OutcomeProofSummaryItem: Equatable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let value: String
    public let accent: Bool

    public var id: String { key }

    public init(key: String, label: String, value: String, accent: Bool) {
        self.key = key
        self.label = label
        self.value = value
        self.accent = accent
    }
}

public struct OutcomeProofHighlight: Equatable, Sendable {
    public let title: String
    public let detail: String

    public init(title: String, detail: String) {
        self.title = title
        self.detail = detail
    }
}

public struct OutcomeProofSummary: Equatable, Sendable {
    public let title: String
    public let subtitle: String
    public let items: [OutcomeProofSummaryItem]
    public let highlight: OutcomeProofHighlight?

    public init(
        title: String,
        subtitle: String,
        items: [OutcomeProofSummaryItem],
        highlight: OutcomeProofHighlight? = nil
    ) {
        self.title = title
        self.subtitle = subtitle
        self.items = items
        self.highlight = highlight
    }
}

public enum OutcomeProofSummaryBuilder {
    public static func build(_ dashboard: ProgressDashboard?) -> OutcomeProofSummary {
        let stats = dashboard?.stats ?? ProgressStats()
        let graded = max(0, stats.graded)
        let improved = max(0, stats.improved)
        let verifying = max(0, dashboard?.verifyingCards.count ?? 0)
        let total = max(0, stats.totalSurfaced)
        let improvementRate = rateLabel(stats.improvementRate, improved: improved, graded: graded)

        let title: String
        let subtitle: String
        if graded > 0 && improved > 0 {
            title = "个人证据：\(improved) 项已改善"
            subtitle = "已验证 \(graded) 项，\(improved)/\(graded) 对你有效。"
        } else if graded > 0 {
            title = "个人证据：\(graded) 项已验证"
            subtitle = "暂未看到明确改善，下一轮会调整干预。"
        } else if verifying > 0 {
            title = "个人证据验证中"
            subtitle = "\(verifying) 个干预已完成，等待指标变化。"
        } else if total > 0 {
            title = "个人证据待完成"
            subtitle = "\(total) 条建议正在推进，完成后才会进入验证。"
        } else {
            title = "等待第一个验证闭环"
            subtitle = "接受并完成建议后，这里会显示对你是否有效。"
        }

        return OutcomeProofSummary(
            title: title,
            subtitle: subtitle,
            items: [
                OutcomeProofSummaryItem(key: "graded", label: "已验证", value: "\(graded)", accent: false),
                OutcomeProofSummaryItem(key: "improved", label: "已改善", value: "\(improved)", accent: improved > 0),
                OutcomeProofSummaryItem(key: "verifying", label: "验证中", value: "\(verifying)", accent: verifying > 0 && graded == 0),
                OutcomeProofSummaryItem(key: "rate", label: "改善率", value: improvementRate, accent: improved > 0)
            ],
            highlight: pickImprovedHighlight(dashboard?.closedCards ?? [])
        )
    }

    private static func rateLabel(_ rate: Double?, improved: Int, graded: Int) -> String {
        let value: Double?
        if let rate, rate.isFinite {
            value = rate
        } else if graded > 0 {
            value = Double(improved) / Double(graded)
        } else {
            value = nil
        }
        guard let value else { return "—" }
        return "\(Int((value * 100).rounded()))%"
    }

    private static func pickImprovedHighlight(_ cards: [ProgressCard]) -> OutcomeProofHighlight? {
        guard let card = cards.first(where: { $0.outcome == "improved" }) else { return nil }
        let metric = card.metricKey?.isEmpty == false ? card.metricKey! : "指标"
        let detail: String
        if let baseline = card.baselineValue, !baseline.isEmpty,
           let actual = card.actualValue, !actual.isEmpty {
            detail = "\(metric) \(baseline) → \(actual)"
        } else {
            detail = metric
        }
        return OutcomeProofHighlight(title: card.title, detail: detail)
    }
}

public final class OutcomeProofClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchDashboard(days: Int = 30) async throws -> ProgressDashboard {
        try await apiClient.get("action-cards/me/progress?days=\(days)")
    }
}
