import Foundation

/// `/api/v1/watch/summary` 的解码模型(snake_case 对齐后端 watch_summary.py)。
/// 后端契约改动时,这里 + WatchSummaryTests 的 fixture 必须同步(防静默漂移)。

public enum ComplicationTone: String, Codable, Sendable {
    case green, yellow, red, gray
}

public struct WatchSource: Codable, Sendable, Equatable {
    public let objectType: String
    public let objectId: Int

    enum CodingKeys: String, CodingKey {
        case objectType = "object_type"
        case objectId = "object_id"
    }
}

public struct WatchStatus: Codable, Sendable {
    public let light: ComplicationTone
    public let readinessScore: Int?
    public let headline: String

    enum CodingKeys: String, CodingKey {
        case light
        case readinessScore = "readiness_score"
        case headline
    }
}

public struct WatchTopAction: Codable, Sendable {
    public let title: String
    public let kind: String
    public let timeWindow: String?
    public let source: WatchSource?

    enum CodingKeys: String, CodingKey {
        case title, kind, source
        case timeWindow = "time_window"
    }
}

public struct WatchAgendaCount: Codable, Sendable {
    public let total: Int
    public let pending: Int
}

public struct WatchQuickAction: Codable, Sendable, Identifiable {
    public let kind: String
    public let label: String
    public let endpoint: String
    public let method: String
    public var id: String { kind }
}

public struct WatchPushItem: Codable, Sendable, Identifiable {
    public let tier: String          // "P0" | "P1"
    public let title: String
    public let detail: String?
    public let kind: String
    public let source: WatchSource?
    public var id: String { "\(tier)-\(kind)-\(title)" }
    public var isUrgent: Bool { tier == "P0" }
}

public struct WatchSummary: Codable, Sendable {
    public let status: WatchStatus
    public let topAction: WatchTopAction?
    public let agenda: WatchAgendaCount
    public let quickActions: [WatchQuickAction]
    public let pushItems: [WatchPushItem]

    enum CodingKeys: String, CodingKey {
        case status, agenda
        case topAction = "top_action"
        case quickActions = "quick_actions"
        case pushItems = "push_items"
    }

    /// 解码 `/watch/summary` JSON。容错:quick_actions 里缺字段的项跳过(由后端契约保证齐全;
    /// 这里只做防御解码,不静默吞整个响应)。
    public static func decode(_ data: Data) throws -> WatchSummary {
        try JSONDecoder().decode(WatchSummary.self, from: data)
    }
}
