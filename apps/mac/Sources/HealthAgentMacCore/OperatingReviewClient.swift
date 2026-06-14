import Foundation

public struct HealthOperatingReview: Decodable, Equatable, Sendable {
    public let windowDays: Int
    public let startDate: String
    public let endDate: String
    public let execution: ExecutionSummary
    public let metrics: [String: MetricChange]
    public let completedActionKeys: [String]

    public init(
        windowDays: Int,
        startDate: String,
        endDate: String,
        execution: ExecutionSummary,
        metrics: [String: MetricChange],
        completedActionKeys: [String]
    ) {
        self.windowDays = windowDays
        self.startDate = startDate
        self.endDate = endDate
        self.execution = execution
        self.metrics = metrics
        self.completedActionKeys = completedActionKeys
    }

    enum CodingKeys: String, CodingKey {
        case windowDays = "window_days"
        case startDate = "start_date"
        case endDate = "end_date"
        case execution
        case metrics
        case completedActionKeys = "completed_action_keys"
    }
}

public struct ExecutionSummary: Decodable, Equatable, Sendable {
    public let totalEvents: Int
    public let completedEvents: Int
    public let completionRate: Double
    public let byStatus: [String: Int]
    public let byDomain: [String: Int]

    public init(
        totalEvents: Int,
        completedEvents: Int,
        completionRate: Double,
        byStatus: [String: Int],
        byDomain: [String: Int]
    ) {
        self.totalEvents = totalEvents
        self.completedEvents = completedEvents
        self.completionRate = completionRate
        self.byStatus = byStatus
        self.byDomain = byDomain
    }

    enum CodingKeys: String, CodingKey {
        case totalEvents = "total_events"
        case completedEvents = "completed_events"
        case completionRate = "completion_rate"
        case byStatus = "by_status"
        case byDomain = "by_domain"
    }
}

public struct MetricChange: Decodable, Equatable, Sendable {
    public let status: String
    public let count: Int
    public let first: Double?
    public let firstDate: String?
    public let current: Double?
    public let currentDate: String?
    public let delta: Double?

    public init(
        status: String,
        count: Int,
        first: Double? = nil,
        firstDate: String? = nil,
        current: Double?,
        currentDate: String? = nil,
        delta: Double?
    ) {
        self.status = status
        self.count = count
        self.first = first
        self.firstDate = firstDate
        self.current = current
        self.currentDate = currentDate
        self.delta = delta
    }

    enum CodingKeys: String, CodingKey {
        case status
        case count
        case first
        case firstDate = "first_date"
        case current
        case currentDate = "current_date"
        case delta
    }
}

public struct OperatingReviewSummaryItem: Equatable, Sendable, Identifiable {
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

public struct OperatingReviewHighlight: Equatable, Sendable {
    public let label: String
    public let value: String
    public let detail: String
    public let positive: Bool

    public init(label: String, value: String, detail: String, positive: Bool) {
        self.label = label
        self.value = value
        self.detail = detail
        self.positive = positive
    }
}

public struct OperatingReviewSummary: Equatable, Sendable {
    public let title: String
    public let subtitle: String
    public let items: [OperatingReviewSummaryItem]
    public let highlight: OperatingReviewHighlight?

    public init(
        title: String,
        subtitle: String,
        items: [OperatingReviewSummaryItem],
        highlight: OperatingReviewHighlight? = nil
    ) {
        self.title = title
        self.subtitle = subtitle
        self.items = items
        self.highlight = highlight
    }
}

public enum OperatingReviewSummaryBuilder {
    public static func build(_ review: HealthOperatingReview?) -> OperatingReviewSummary {
        let total = max(0, review?.execution.totalEvents ?? 0)
        let completed = max(0, review?.execution.completedEvents ?? 0)
        let learnable = max(0, review?.completedActionKeys.count ?? 0)
        let rate = clampRate(review?.execution.completionRate ?? 0)
        let rateLabel = "\(Int((rate * 100).rounded()))%"

        let title: String
        let subtitle: String
        if total > 0 {
            title = "执行复盘：\(rateLabel) 完成"
            subtitle = "过去 \(review?.windowDays ?? 7) 天完成 \(completed)/\(total) 个行动。"
        } else {
            title = "执行复盘待开始"
            subtitle = "先完成今天最重要的一件事，复盘会开始累积。"
        }

        return OperatingReviewSummary(
            title: title,
            subtitle: subtitle,
            items: [
                OperatingReviewSummaryItem(key: "completion_rate", label: "完成率", value: rateLabel, accent: rate >= 0.6),
                OperatingReviewSummaryItem(key: "completed", label: "已完成", value: "\(completed)", accent: completed > 0),
                OperatingReviewSummaryItem(key: "total", label: "总行动", value: "\(total)", accent: false),
                OperatingReviewSummaryItem(key: "learnable", label: "可学习", value: "\(learnable)", accent: learnable > 0)
            ],
            highlight: pickMetricHighlight(review?.metrics ?? [:])
        )
    }

    private struct MetricMeta {
        let label: String
        let unit: String
        let good: Direction
    }

    private enum Direction {
        case up
        case down
    }

    private static let metricMeta: [(String, MetricMeta)] = [
        ("weight", MetricMeta(label: "体重", unit: "kg", good: .down)),
        ("waist_cm", MetricMeta(label: "腰围", unit: "cm", good: .down)),
        ("systolic_bp", MetricMeta(label: "收缩压", unit: "mmHg", good: .down)),
        ("diastolic_bp", MetricMeta(label: "舒张压", unit: "mmHg", good: .down)),
        ("sleep_score", MetricMeta(label: "睡眠评分", unit: "", good: .up)),
        ("hrv", MetricMeta(label: "HRV", unit: "ms", good: .up))
    ]

    private static func pickMetricHighlight(_ metrics: [String: MetricChange]) -> OperatingReviewHighlight? {
        let candidates = metricMeta.enumerated().compactMap { priority, entry -> (MetricMeta, Double, Bool, Int)? in
            let (key, meta) = entry
            guard let change = metrics[key],
                  change.status == "present",
                  let delta = change.delta
            else { return nil }
            let positive = meta.good == .down ? delta < 0 : delta > 0
            return (meta, delta, positive, priority)
        }
        .sorted { lhs, rhs in
            if lhs.2 != rhs.2 {
                return lhs.2 && !rhs.2
            }
            return lhs.3 < rhs.3
        }

        guard let picked = candidates.first else { return nil }
        let unitSuffix = picked.0.unit.isEmpty ? "" : " \(picked.0.unit)"
        return OperatingReviewHighlight(
            label: "最明显变化",
            value: "\(picked.0.label) \(formatSigned(picked.1))\(unitSuffix)",
            detail: "时间关联，不等于因果。",
            positive: picked.2
        )
    }

    private static func clampRate(_ value: Double) -> Double {
        guard value.isFinite else { return 0 }
        return max(0, min(1, value))
    }

    private static func formatSigned(_ value: Double) -> String {
        if value > 0 {
            return "+\(formatNumber(value))"
        }
        return formatNumber(value)
    }

    private static func formatNumber(_ value: Double) -> String {
        if value.rounded() == value {
            return "\(Int(value))"
        }
        return "\(Double(round(value * 10) / 10))"
    }
}

public final class OperatingReviewClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchReview(days: Int = 7) async throws -> HealthOperatingReview {
        try await apiClient.get("daily-plan/review?window_days=\(days)")
    }
}
