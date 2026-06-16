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

/// 可在腕上「一键完成」的 kind(= health_protocol 域:处方药/补剂/喝水/餐协议)。
/// 其余 kind(训练/复查/测量…)只读不可勾,与后端 health_protocol-only 回写边界一致。
public let watchCompletableKinds: Set<String> = ["medication", "supplement", "hydration", "diet"]

public struct WatchTopAction: Codable, Sendable {
    public let title: String
    public let kind: String
    public let timeWindow: String?
    public let source: WatchSource?
    public let priorityTier: String?
    public let leverageScore: Int?
    public let rationaleShort: String?
    public let verificationWindowDays: Int?
    public let safetyStatus: String?
    /// 后端注入:`agenda-{object_type}-{object_id}`。无 source 的项为 nil(不可完成,只读)。
    public let actionId: String?

    public init(
        title: String,
        kind: String,
        timeWindow: String?,
        source: WatchSource?,
        priorityTier: String? = nil,
        leverageScore: Int? = nil,
        rationaleShort: String? = nil,
        verificationWindowDays: Int? = nil,
        safetyStatus: String? = nil,
        actionId: String? = nil
    ) {
        self.title = title
        self.kind = kind
        self.timeWindow = timeWindow
        self.source = source
        self.priorityTier = priorityTier
        self.leverageScore = leverageScore
        self.rationaleShort = rationaleShort
        self.verificationWindowDays = verificationWindowDays
        self.safetyStatus = safetyStatus
        self.actionId = actionId
    }

    /// 可一键完成 = 有 action_id 且 kind 属于 health_protocol 可回写域。非可完成项只渲染只读。
    public var isCompletable: Bool {
        guard let id = actionId, !id.isEmpty else { return false }
        return watchCompletableKinds.contains(kind)
    }

    enum CodingKeys: String, CodingKey {
        case title, kind, source
        case timeWindow = "time_window"
        case priorityTier = "priority_tier"
        case leverageScore = "leverage_score"
        case rationaleShort = "rationale_short"
        case verificationWindowDays = "verification_window_days"
        case safetyStatus = "safety_status"
        case actionId = "action_id"
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
