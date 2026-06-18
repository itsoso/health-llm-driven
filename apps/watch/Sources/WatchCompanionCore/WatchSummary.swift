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

public enum WatchFreshnessState: String, Codable, Sendable, Equatable {
    case fresh
    case stale
    case missing
    case error
    case unknown

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = WatchFreshnessState(rawValue: raw) ?? .unknown
    }
}

public struct WatchFreshness: Codable, Sendable, Equatable {
    public let state: WatchFreshnessState
    public let label: String
    public let latestDate: String?
    public let ageDays: Int?
    public let lastSyncAt: String?

    public init(
        state: WatchFreshnessState,
        label: String,
        latestDate: String?,
        ageDays: Int?,
        lastSyncAt: String?
    ) {
        self.state = state
        self.label = label
        self.latestDate = latestDate
        self.ageDays = ageDays
        self.lastSyncAt = lastSyncAt
    }

    enum CodingKeys: String, CodingKey {
        case state, label
        case latestDate = "latest_date"
        case ageDays = "age_days"
        case lastSyncAt = "last_sync_at"
    }

    public var isFresh: Bool {
        state == .fresh
    }

    public var shortText: String {
        switch state {
        case .fresh:
            return "已同步"
        case .error:
            return "同步异常"
        case .stale, .missing, .unknown:
            return "待同步"
        }
    }
}

public struct WatchStatus: Codable, Sendable {
    public let light: ComplicationTone
    public let readinessScore: Int?
    public let headline: String
    public let freshness: WatchFreshness?

    public init(
        light: ComplicationTone,
        readinessScore: Int?,
        headline: String,
        freshness: WatchFreshness? = nil
    ) {
        self.light = light
        self.readinessScore = readinessScore
        self.headline = headline
        self.freshness = freshness
    }

    enum CodingKeys: String, CodingKey {
        case light
        case readinessScore = "readiness_score"
        case headline
        case freshness
    }
}

/// 可在腕上「一键完成」的 kind(= health_protocol 域:处方药/补剂/喝水/餐协议/微运动)。
/// 训练决策、复查、测量等非 health_protocol 来源只读不可勾,与后端回写边界一致。
public let watchCompletableKinds: Set<String> = [
    "medication", "supplement", "hydration", "diet",
    "training", "activity", "exercise",
]

/// cut A:movement 处方(后端 `prescription`)。各端按形态渲染;腕上用 intensityLabel 出强度 chip。
public struct WatchPrescription: Codable, Sendable, Equatable {
    public let intensity: String        // high | moderate | low | rest | unknown
    public let type: String?
    public let durationMin: Int?
    public let rpe: String?
    public let guidance: String?
    public let geneNote: String?

    public init(intensity: String, type: String? = nil, durationMin: Int? = nil,
                rpe: String? = nil, guidance: String? = nil, geneNote: String? = nil) {
        self.intensity = intensity; self.type = type; self.durationMin = durationMin
        self.rpe = rpe; self.guidance = guidance; self.geneNote = geneNote
    }

    enum CodingKeys: String, CodingKey {
        case intensity, type, rpe, guidance
        case durationMin = "duration_min"
        case geneNote = "gene_note"
    }

    /// 腕上强度 chip 文案(空串 = 不显示)。
    public var intensityLabel: String {
        switch intensity {
        case "high": return "高强度"
        case "moderate": return "中强度"
        case "low": return "低强度"
        case "rest": return "休息"
        default: return ""
        }
    }
}

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
    public let prescription: WatchPrescription?

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
        actionId: String? = nil,
        prescription: WatchPrescription? = nil
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
        self.prescription = prescription
    }

    /// 可一键完成 = 有 action_id 且 kind 属于 health_protocol 可回写域。非可完成项只渲染只读。
    public var isCompletable: Bool {
        guard let id = actionId, !id.isEmpty else { return false }
        guard source?.objectType == "health_protocol" else { return false }
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
        case prescription
    }
}

public struct WatchDueItem: Codable, Sendable, Identifiable {
    public let title: String
    public let kind: String
    public let timeWindow: String?
    public let source: WatchSource?
    public let actionId: String?
    public let prescription: WatchPrescription?

    public init(title: String, kind: String, timeWindow: String?, source: WatchSource?,
                actionId: String? = nil, prescription: WatchPrescription? = nil) {
        self.title = title; self.kind = kind; self.timeWindow = timeWindow
        self.source = source; self.actionId = actionId; self.prescription = prescription
    }

    public var id: String { actionId ?? "\(kind)-\(title)-\(timeWindow ?? "anytime")" }

    public var isCompletable: Bool {
        guard let id = actionId, !id.isEmpty else { return false }
        guard source?.objectType == "health_protocol" else { return false }
        return watchCompletableKinds.contains(kind)
    }

    enum CodingKeys: String, CodingKey {
        case title, kind, source
        case timeWindow = "time_window"
        case actionId = "action_id"
        case prescription
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
    public let dueItems: [WatchDueItem]
    public let agenda: WatchAgendaCount
    public let quickActions: [WatchQuickAction]
    public let pushItems: [WatchPushItem]

    enum CodingKeys: String, CodingKey {
        case status, agenda
        case topAction = "top_action"
        case dueItems = "due_items"
        case quickActions = "quick_actions"
        case pushItems = "push_items"
    }

    public init(
        status: WatchStatus,
        topAction: WatchTopAction?,
        dueItems: [WatchDueItem] = [],
        agenda: WatchAgendaCount,
        quickActions: [WatchQuickAction],
        pushItems: [WatchPushItem]
    ) {
        self.status = status
        self.topAction = topAction
        self.dueItems = dueItems
        self.agenda = agenda
        self.quickActions = quickActions
        self.pushItems = pushItems
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decode(WatchStatus.self, forKey: .status)
        self.topAction = try c.decodeIfPresent(WatchTopAction.self, forKey: .topAction)
        self.dueItems = try c.decodeIfPresent([WatchDueItem].self, forKey: .dueItems) ?? []
        self.agenda = try c.decode(WatchAgendaCount.self, forKey: .agenda)
        self.quickActions = try c.decode([WatchQuickAction].self, forKey: .quickActions)
        self.pushItems = try c.decode([WatchPushItem].self, forKey: .pushItems)
    }

    /// 解码 `/watch/summary` JSON。容错:quick_actions 里缺字段的项跳过(由后端契约保证齐全;
    /// 这里只做防御解码,不静默吞整个响应)。
    public static func decode(_ data: Data) throws -> WatchSummary {
        try JSONDecoder().decode(WatchSummary.self, from: data)
    }
}
