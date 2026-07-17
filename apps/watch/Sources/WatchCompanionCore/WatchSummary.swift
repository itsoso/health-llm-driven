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

/// 可在腕上「一键完成」的 kind(= health_protocol 或 SmartReminder 域)。
/// 训练决策、复查、测量等非可回写来源只读不可勾,与后端回写边界一致。
public let watchCompletableKinds: Set<String> = [
    "medication", "supplement", "hydration", "diet",
    "training", "activity", "exercise", "reminder",
]

public let watchCompletableSourceTypes: Set<String> = [
    "health_protocol", "smart_reminder",
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

public struct WatchRuntimeVerificationWindow: Codable, Sendable, Equatable {
    public let metrics: [String]
    public let windowDays: Int?

    public init(metrics: [String] = [], windowDays: Int? = nil) {
        self.metrics = metrics
        self.windowDays = windowDays
    }

    enum CodingKeys: String, CodingKey {
        case metrics
        case windowDays = "window_days"
    }
}

public struct WatchRuntimeContext: Codable, Sendable, Equatable {
    public let currentStateSummary: String?
    public let replanReason: String?
    public let safetyBoundary: String?
    public let verificationWindow: WatchRuntimeVerificationWindow?

    public init(
        currentStateSummary: String? = nil,
        replanReason: String? = nil,
        safetyBoundary: String? = nil,
        verificationWindow: WatchRuntimeVerificationWindow? = nil
    ) {
        self.currentStateSummary = currentStateSummary
        self.replanReason = replanReason
        self.safetyBoundary = safetyBoundary
        self.verificationWindow = verificationWindow
    }

    enum CodingKeys: String, CodingKey {
        case currentStateSummary = "current_state_summary"
        case replanReason = "replan_reason"
        case safetyBoundary = "safety_boundary"
        case verificationWindow = "verification_window"
    }
}

public struct WatchRuntimeSummary: Codable, Sendable, Equatable {
    public let mode: String?
    public let generatedBy: String?
    public let horizonDays: Int?
    public let start: String?
    public let end: String?

    public init(
        mode: String? = nil,
        generatedBy: String? = nil,
        horizonDays: Int? = nil,
        start: String? = nil,
        end: String? = nil
    ) {
        self.mode = mode
        self.generatedBy = generatedBy
        self.horizonDays = horizonDays
        self.start = start
        self.end = end
    }

    enum CodingKeys: String, CodingKey {
        case mode, start, end
        case generatedBy = "generated_by"
        case horizonDays = "horizon_days"
    }
}

private func watchDecisionBasisLines(
    rationale: String?,
    runtimeContext: WatchRuntimeContext?,
    maxCount: Int
) -> [String] {
    guard maxCount > 0 else { return [] }
    var lines: [String] = []

    func append(_ value: String?) {
        let cleaned = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !cleaned.isEmpty, !lines.contains(cleaned) else { return }
        lines.append(cleaned)
    }

    append(rationale)
    append(runtimeContext?.currentStateSummary)
    append(watchVerificationLine(runtimeContext?.verificationWindow))
    append(runtimeContext?.safetyBoundary)

    return Array(lines.prefix(maxCount))
}

private func watchVerificationLine(_ window: WatchRuntimeVerificationWindow?) -> String? {
    guard let window else { return nil }
    let metrics = uniqueWatchMetricLabels(window.metrics)
    if let days = window.windowDays, !metrics.isEmpty {
        return "验证: \(days)天 · \(metrics.joined(separator: " / "))"
    }
    if let days = window.windowDays {
        return "验证: \(days)天"
    }
    if !metrics.isEmpty {
        return "验证: \(metrics.joined(separator: " / "))"
    }
    return nil
}

private func uniqueWatchMetricLabels(_ metrics: [String]) -> [String] {
    var seen: Set<String> = []
    var result: [String] = []
    for metric in metrics {
        let label = watchMetricLabel(metric)
        guard !label.isEmpty, !seen.contains(label) else { continue }
        seen.insert(label)
        result.append(label)
    }
    return result
}

private func watchMetricLabel(_ metric: String) -> String {
    switch metric {
    case "post_meal_walk_completed":
        return "餐后步行"
    case "waist_cm":
        return "腰围"
    case "weight", "weight_kg":
        return "体重"
    case "sleep_score":
        return "睡眠"
    case "hrv", "hrv_ms":
        return "HRV"
    case "systolic_bp":
        return "收缩压"
    case "diastolic_bp":
        return "舒张压"
    case "fasting_glucose":
        return "空腹血糖"
    default:
        return metric
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "_", with: " ")
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
    public let runtimeContext: WatchRuntimeContext?

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
        prescription: WatchPrescription? = nil,
        runtimeContext: WatchRuntimeContext? = nil
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
        self.runtimeContext = runtimeContext
    }

    /// 可一键完成 = 有 action_id 且来源/kind 属于后端可回写域。非可完成项只渲染只读。
    public var isCompletable: Bool {
        guard let id = actionId, !id.isEmpty else { return false }
        guard let objectType = source?.objectType, watchCompletableSourceTypes.contains(objectType) else { return false }
        return watchCompletableKinds.contains(kind)
    }

    public func decisionBasisLines(maxCount: Int = 3) -> [String] {
        watchDecisionBasisLines(
            rationale: rationaleShort,
            runtimeContext: runtimeContext,
            maxCount: maxCount
        )
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
        case runtimeContext = "runtime_context"
    }
}

public struct WatchDueItem: Codable, Sendable, Identifiable {
    public let title: String
    public let kind: String
    public let timeWindow: String?
    public let source: WatchSource?
    public let actionId: String?
    public let prescription: WatchPrescription?
    public let runtimeContext: WatchRuntimeContext?

    public init(title: String, kind: String, timeWindow: String?, source: WatchSource?,
                actionId: String? = nil, prescription: WatchPrescription? = nil,
                runtimeContext: WatchRuntimeContext? = nil) {
        self.title = title; self.kind = kind; self.timeWindow = timeWindow
        self.source = source; self.actionId = actionId; self.prescription = prescription
        self.runtimeContext = runtimeContext
    }

    public var id: String { actionId ?? "\(kind)-\(title)-\(timeWindow ?? "anytime")" }

    public var isCompletable: Bool {
        guard let id = actionId, !id.isEmpty else { return false }
        guard let objectType = source?.objectType, watchCompletableSourceTypes.contains(objectType) else { return false }
        return watchCompletableKinds.contains(kind)
    }

    public func decisionBasisLines(maxCount: Int = 2) -> [String] {
        watchDecisionBasisLines(
            rationale: nil,
            runtimeContext: runtimeContext,
            maxCount: maxCount
        )
    }

    enum CodingKeys: String, CodingKey {
        case title, kind, source
        case timeWindow = "time_window"
        case actionId = "action_id"
        case prescription
        case runtimeContext = "runtime_context"
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

public enum WatchQuickActionKind: String, Sendable, Equatable {
    case water
    case exercise
    case dietVoice
    case symptomVoice
}

public struct WatchQuickActionPresentation: Sendable, Equatable, Identifiable {
    public let kind: WatchQuickActionKind
    public let label: String

    public init(kind: WatchQuickActionKind, label: String) {
        self.kind = kind
        self.label = label
    }

    public var id: String { kind.rawValue }
}

public func watchQuickActionPresentations(_ actions: [WatchQuickAction]) -> [WatchQuickActionPresentation] {
    let source = actions.isEmpty ? watchDefaultRemoteQuickActions() : actions
    var result: [WatchQuickActionPresentation] = []
    var seen: Set<WatchQuickActionKind> = []

    func append(_ item: WatchQuickActionPresentation) {
        guard !seen.contains(item.kind) else { return }
        seen.insert(item.kind)
        result.append(item)
    }

    for action in source {
        guard let presentation = watchPresentation(for: action) else { continue }
        append(presentation)
    }
    append(.init(kind: .symptomVoice, label: "语音记症状"))
    return result
}

private func watchDefaultRemoteQuickActions() -> [WatchQuickAction] {
    [
        .init(kind: "water", label: "喝水", endpoint: "/water/records/quick", method: "POST"),
        .init(kind: "exercise", label: "运动", endpoint: "/daily-health/exercise", method: "POST"),
        .init(kind: "diet_voice", label: "记一餐", endpoint: "/diet/voice/parse", method: "POST"),
    ]
}

private func watchPresentation(for action: WatchQuickAction) -> WatchQuickActionPresentation? {
    guard action.method.uppercased() == "POST" else { return nil }
    switch action.kind {
    case "water":
        guard action.endpoint == "/water/records/quick" else { return nil }
        return .init(kind: .water, label: normalizedQuickActionLabel(action.label, fallback: "喝水"))
    case "exercise":
        guard action.endpoint == "/daily-health/exercise" else { return nil }
        return .init(kind: .exercise, label: normalizedQuickActionLabel(action.label, fallback: "运动"))
    case "diet_voice":
        guard action.endpoint == "/diet/voice/parse" else { return nil }
        let label = normalizedQuickActionLabel(action.label, fallback: "记一餐")
        return .init(kind: .dietVoice, label: label.contains("语音") ? label : "语音\(label)")
    default:
        return nil
    }
}

private func normalizedQuickActionLabel(_ label: String, fallback: String) -> String {
    let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? fallback : trimmed
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
    public let runtime: WatchRuntimeSummary?
    public let quickActions: [WatchQuickAction]
    public let pushItems: [WatchPushItem]

    enum CodingKeys: String, CodingKey {
        case status, agenda, runtime
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
        runtime: WatchRuntimeSummary? = nil,
        quickActions: [WatchQuickAction],
        pushItems: [WatchPushItem]
    ) {
        self.status = status
        self.topAction = topAction
        self.dueItems = dueItems
        self.agenda = agenda
        self.runtime = runtime
        self.quickActions = quickActions
        self.pushItems = pushItems
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decode(WatchStatus.self, forKey: .status)
        self.topAction = try c.decodeIfPresent(WatchTopAction.self, forKey: .topAction)
        self.dueItems = try c.decodeIfPresent([WatchDueItem].self, forKey: .dueItems) ?? []
        self.agenda = try c.decode(WatchAgendaCount.self, forKey: .agenda)
        self.runtime = try c.decodeIfPresent(WatchRuntimeSummary.self, forKey: .runtime)
        self.quickActions = try c.decode([WatchQuickAction].self, forKey: .quickActions)
        self.pushItems = try c.decode([WatchPushItem].self, forKey: .pushItems)
    }

    /// 解码 `/watch/summary` JSON。容错:quick_actions 里缺字段的项跳过(由后端契约保证齐全;
    /// 这里只做防御解码,不静默吞整个响应)。
    public static func decode(_ data: Data) throws -> WatchSummary {
        try JSONDecoder().decode(WatchSummary.self, from: data)
    }
}

public func watchSmartReminderVisibleEventMetas(_ summary: WatchSummary) -> [[String: String]] {
    summary.dueItems.compactMap { item in
        guard item.source?.objectType == "smart_reminder",
              let reminderId = item.source?.objectId,
              let actionId = item.actionId,
              !actionId.isEmpty else {
            return nil
        }
        return [
            "action_id": actionId,
            "reminder_id": String(reminderId),
            "kind": item.kind,
            "surface": "watch_summary",
        ]
    }
}
