import Foundation

// MARK: - Health Extras models
//
// 消费四个已上线的后端能力(H1):
//   ① GET  /medication/deprescribing-review/me  多药梳理 / 减药候选
//   ② GET/POST /chronic/connection              社会连接自评(UCLA-3)
//   ③ GET  /chronic/causal-links                时滞因果(用药→指标描述性关联)
//   ④ GET  /data-health/integrity               数据正确性自检
//
// 所有字段一律 `decodeIfPresent` 容错:后端字段缺失 / 为 null 时绝不让整条记录
// 解码失败,也绝不臆造数据。⚠️ 多药梳理为「减药候选」,绝不命令停药。

// MARK: - ① 多药梳理 / 减药候选

/// 一条减药候选标记(对应 `flags[]` 单条)。code ∈
/// polypharmacy|duplicate_class|long_term_candidate|expired_still_active。
public struct DeprescribingFlag: Codable, Equatable, Sendable, Identifiable {
    public let code: String
    public let detail: String
    public let suggestion: String

    /// 没有稳定服务端 id;用 code+detail 拼一个用于 ForEach。
    public var id: String { code + "|" + detail }

    public init(code: String = "", detail: String = "", suggestion: String = "") {
        self.code = code
        self.detail = detail
        self.suggestion = suggestion
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.code = try container.decodeIfPresent(String.self, forKey: .code) ?? ""
        self.detail = try container.decodeIfPresent(String.self, forKey: .detail) ?? ""
        self.suggestion = try container.decodeIfPresent(String.self, forKey: .suggestion) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case code
        case detail
        case suggestion
    }
}

/// 对应 `GET /medication/deprescribing-review/me` 响应。
public struct DeprescribingReview: Codable, Equatable, Sendable {
    public let activeCount: Int
    public let isPolypharmacy: Bool
    public let flags: [DeprescribingFlag]
    public let disclaimer: String

    public init(
        activeCount: Int = 0,
        isPolypharmacy: Bool = false,
        flags: [DeprescribingFlag] = [],
        disclaimer: String = ""
    ) {
        self.activeCount = activeCount
        self.isPolypharmacy = isPolypharmacy
        self.flags = flags
        self.disclaimer = disclaimer
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.activeCount = try container.decodeIfPresent(Int.self, forKey: .activeCount) ?? 0
        self.isPolypharmacy = try container.decodeIfPresent(Bool.self, forKey: .isPolypharmacy) ?? false
        self.flags = try container.decodeIfPresent([DeprescribingFlag].self, forKey: .flags) ?? []
        self.disclaimer = try container.decodeIfPresent(String.self, forKey: .disclaimer) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case activeCount = "active_count"
        case isPolypharmacy = "is_polypharmacy"
        case flags
        case disclaimer
    }
}

// MARK: - ② 社会连接自评

/// 对应 `GET /chronic/connection` 响应。无 check-in 时 `hasCheckin == false`,
/// 多数字段为 nil —— UI 据此显示「还没做过」而非伪造分数。
public struct ConnectionStatus: Codable, Equatable, Sendable {
    public let hasCheckin: Bool
    public let due: Bool
    public let daysSince: Int?
    public let lastDate: String?
    public let uclaScore: Int?
    public let hasConfidant: Bool?
    public let inStableGroup: Bool?
    public let interpretation: String

    public init(
        hasCheckin: Bool = false,
        due: Bool = true,
        daysSince: Int? = nil,
        lastDate: String? = nil,
        uclaScore: Int? = nil,
        hasConfidant: Bool? = nil,
        inStableGroup: Bool? = nil,
        interpretation: String = ""
    ) {
        self.hasCheckin = hasCheckin
        self.due = due
        self.daysSince = daysSince
        self.lastDate = lastDate
        self.uclaScore = uclaScore
        self.hasConfidant = hasConfidant
        self.inStableGroup = inStableGroup
        self.interpretation = interpretation
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.hasCheckin = try container.decodeIfPresent(Bool.self, forKey: .hasCheckin) ?? false
        self.due = try container.decodeIfPresent(Bool.self, forKey: .due) ?? true
        self.daysSince = try container.decodeIfPresent(Int.self, forKey: .daysSince)
        self.lastDate = try container.decodeIfPresent(String.self, forKey: .lastDate)
        self.uclaScore = try container.decodeIfPresent(Int.self, forKey: .uclaScore)
        self.hasConfidant = try container.decodeIfPresent(Bool.self, forKey: .hasConfidant)
        self.inStableGroup = try container.decodeIfPresent(Bool.self, forKey: .inStableGroup)
        self.interpretation = try container.decodeIfPresent(String.self, forKey: .interpretation) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case hasCheckin = "has_checkin"
        case due
        case daysSince = "days_since"
        case lastDate = "last_date"
        case uclaScore = "ucla_score"
        case hasConfidant = "has_confidant"
        case inStableGroup = "in_stable_group"
        case interpretation
    }
}

/// `POST /chronic/connection` 请求体。`ucla_score` 须 3–9(UCLA-3 三题各 1–3 分)。
public struct ConnectionCheckinRequest: Codable, Equatable, Sendable {
    public let uclaScore: Int
    public let hasConfidant: Bool
    public let inStableGroup: Bool
    public let notes: String?

    public init(uclaScore: Int, hasConfidant: Bool, inStableGroup: Bool, notes: String? = nil) {
        self.uclaScore = uclaScore
        self.hasConfidant = hasConfidant
        self.inStableGroup = inStableGroup
        self.notes = notes
    }

    enum CodingKeys: String, CodingKey {
        case uclaScore = "ucla_score"
        case hasConfidant = "has_confidant"
        case inStableGroup = "in_stable_group"
        case notes
    }
}

/// `POST /chronic/connection` 响应。提交后后端回带最新 status。
public struct ConnectionCheckinResponse: Codable, Equatable, Sendable {
    public let id: Int?
    public let checkinDate: String?
    public let status: ConnectionStatus?

    public init(id: Int? = nil, checkinDate: String? = nil, status: ConnectionStatus? = nil) {
        self.id = id
        self.checkinDate = checkinDate
        self.status = status
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try container.decodeIfPresent(Int.self, forKey: .id)
        self.checkinDate = try container.decodeIfPresent(String.self, forKey: .checkinDate)
        self.status = try container.decodeIfPresent(ConnectionStatus.self, forKey: .status)
    }

    enum CodingKeys: String, CodingKey {
        case id
        case checkinDate = "checkin_date"
        case status
    }
}

// MARK: - ③ 时滞因果

/// 一条用药干预 → 指标前后变化(对应 `intervention_effects[]` 单条)。描述性关联,非因果。
public struct InterventionEffect: Codable, Equatable, Sendable, Identifiable {
    public let medication: String
    public let metricLabel: String
    public let beforeMean: Double?
    public let afterMean: Double?
    public let delta: Double?
    public let pct: Double?
    public let nBefore: Int
    public let nAfter: Int

    public var id: String { medication + "|" + metricLabel }

    public init(
        medication: String = "",
        metricLabel: String = "",
        beforeMean: Double? = nil,
        afterMean: Double? = nil,
        delta: Double? = nil,
        pct: Double? = nil,
        nBefore: Int = 0,
        nAfter: Int = 0
    ) {
        self.medication = medication
        self.metricLabel = metricLabel
        self.beforeMean = beforeMean
        self.afterMean = afterMean
        self.delta = delta
        self.pct = pct
        self.nBefore = nBefore
        self.nAfter = nAfter
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.medication = try container.decodeIfPresent(String.self, forKey: .medication) ?? ""
        self.metricLabel = try container.decodeIfPresent(String.self, forKey: .metricLabel) ?? ""
        self.beforeMean = try container.decodeIfPresent(Double.self, forKey: .beforeMean)
        self.afterMean = try container.decodeIfPresent(Double.self, forKey: .afterMean)
        self.delta = try container.decodeIfPresent(Double.self, forKey: .delta)
        self.pct = try container.decodeIfPresent(Double.self, forKey: .pct)
        self.nBefore = try container.decodeIfPresent(Int.self, forKey: .nBefore) ?? 0
        self.nAfter = try container.decodeIfPresent(Int.self, forKey: .nAfter) ?? 0
    }

    /// 指标是否朝下走(delta<0)。UI 据此选箭头(不判好坏,只表方向)。
    public var isDecrease: Bool {
        guard let delta else { return false }
        return delta < 0
    }

    enum CodingKeys: String, CodingKey {
        case medication
        case metricLabel = "metric_label"
        case beforeMean = "before_mean"
        case afterMean = "after_mean"
        case delta
        case pct
        case nBefore = "n_before"
        case nAfter = "n_after"
    }
}

/// 对应 `GET /chronic/causal-links` 响应。
public struct CausalLinksReport: Codable, Equatable, Sendable {
    public let interventionEffects: [InterventionEffect]
    public let note: String

    public init(interventionEffects: [InterventionEffect] = [], note: String = "") {
        self.interventionEffects = interventionEffects
        self.note = note
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.interventionEffects = try container.decodeIfPresent(
            [InterventionEffect].self, forKey: .interventionEffects
        ) ?? []
        self.note = try container.decodeIfPresent(String.self, forKey: .note) ?? ""
    }

    enum CodingKeys: String, CodingKey {
        case interventionEffects = "intervention_effects"
        case note
    }
}

// MARK: - ④ 数据正确性自检

/// 数据完整性严重度。后端给原始字符串,这里收敛到三态便于配色。
public enum IntegritySeverity: String, Equatable, Sendable {
    case error
    case warning
    case info
}

/// 一条数据完整性问题(对应 `issues[]` 单条)。
public struct IntegrityIssue: Codable, Equatable, Sendable, Identifiable {
    public let code: String
    public let severity: String
    public let detail: String
    public let count: Int
    public let fixHint: String

    public var id: String { code + "|" + detail }

    public init(
        code: String = "",
        severity: String = "",
        detail: String = "",
        count: Int = 1,
        fixHint: String = ""
    ) {
        self.code = code
        self.severity = severity
        self.detail = detail
        self.count = count
        self.fixHint = fixHint
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.code = try container.decodeIfPresent(String.self, forKey: .code) ?? ""
        self.severity = try container.decodeIfPresent(String.self, forKey: .severity) ?? ""
        self.detail = try container.decodeIfPresent(String.self, forKey: .detail) ?? ""
        self.count = try container.decodeIfPresent(Int.self, forKey: .count) ?? 1
        self.fixHint = try container.decodeIfPresent(String.self, forKey: .fixHint) ?? ""
    }

    /// 归一化严重度(小写裁空白),未知值退回 .info。
    public var normalizedSeverity: IntegritySeverity {
        IntegritySeverity(rawValue: severity.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) ?? .info
    }

    enum CodingKeys: String, CodingKey {
        case code
        case severity
        case detail
        case count
        case fixHint = "fix_hint"
    }
}

/// 对应 `GET /data-health/integrity` 响应。空 issues = 健康。
public struct IntegrityReport: Codable, Equatable, Sendable {
    public let healthy: Bool
    public let issueCount: Int
    public let issues: [IntegrityIssue]

    public init(healthy: Bool = true, issueCount: Int = 0, issues: [IntegrityIssue] = []) {
        self.healthy = healthy
        self.issueCount = issueCount
        self.issues = issues
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.healthy = try container.decodeIfPresent(Bool.self, forKey: .healthy) ?? true
        self.issueCount = try container.decodeIfPresent(Int.self, forKey: .issueCount) ?? 0
        self.issues = try container.decodeIfPresent([IntegrityIssue].self, forKey: .issues) ?? []
    }

    enum CodingKeys: String, CodingKey {
        case healthy
        case issueCount = "issue_count"
        case issues
    }
}

// MARK: - Health guardrail summary

public struct HealthGuardrailSummaryItem: Equatable, Sendable, Identifiable {
    public let key: String
    public let label: String
    public let value: String
    public let attention: Bool

    public var id: String { key }

    public init(key: String, label: String, value: String, attention: Bool) {
        self.key = key
        self.label = label
        self.value = value
        self.attention = attention
    }
}

public struct HealthGuardrailSummary: Equatable, Sendable {
    public let attentionCount: Int
    public let title: String
    public let subtitle: String
    public let items: [HealthGuardrailSummaryItem]

    public init(
        attentionCount: Int,
        title: String,
        subtitle: String,
        items: [HealthGuardrailSummaryItem]
    ) {
        self.attentionCount = attentionCount
        self.title = title
        self.subtitle = subtitle
        self.items = items
    }
}

public enum HealthGuardrailSummaryBuilder {
    public static func build(
        integrity: IntegrityReport? = nil,
        deprescribing: DeprescribingReview? = nil,
        connection: ConnectionStatus? = nil,
        causalLinks: CausalLinksReport? = nil
    ) -> HealthGuardrailSummary {
        let integrityIssues = max(0, integrity?.issueCount ?? integrity?.issues.count ?? 0)
        let medicationFlags = max(0, deprescribing?.flags.count ?? 0)
        let connectionDue = connection?.due == true
        let causalInsightCount = max(0, causalLinks?.interventionEffects.count ?? 0)
        let attentionCount = integrityIssues + medicationFlags + (connectionDue ? 1 : 0)

        let title: String
        if attentionCount > 0 {
            title = "健康守门 \(attentionCount) 项待处理"
        } else if causalInsightCount > 0 {
            title = "健康守门正常 · \(causalInsightCount) 条用药关联"
        } else {
            title = "健康守门正常"
        }

        let subtitle: String
        if attentionCount > 0 {
            subtitle = "先处理会影响建议可信度的健康维护项。"
        } else if causalInsightCount > 0 {
            subtitle = "数据可信，已有用药-指标关联可复盘。"
        } else {
            subtitle = "数据与维护项暂无异常，继续执行今日闭环。"
        }

        return HealthGuardrailSummary(
            attentionCount: attentionCount,
            title: title,
            subtitle: subtitle,
            items: [
                HealthGuardrailSummaryItem(
                    key: "data_integrity",
                    label: "数据自检",
                    value: integrity.map { _ in integrityIssues > 0 ? "\(integrityIssues) 个问题" : "通过" } ?? "未加载",
                    attention: integrityIssues > 0
                ),
                HealthGuardrailSummaryItem(
                    key: "deprescribing",
                    label: "用药梳理",
                    value: deprescribing.map { medicationFlags > 0 ? "\(medicationFlags) 条候选" : "\($0.activeCount) 种在用" } ?? "未加载",
                    attention: medicationFlags > 0
                ),
                HealthGuardrailSummaryItem(
                    key: "connection",
                    label: "社会连接",
                    value: connection.map { status in
                        if status.due { return "本周应自评" }
                        if let days = status.daysSince { return "\(days) 天前" }
                        return "已维护"
                    } ?? "未加载",
                    attention: connectionDue
                ),
                HealthGuardrailSummaryItem(
                    key: "causal_links",
                    label: "指标关联",
                    value: causalLinks.map { _ in causalInsightCount > 0 ? "\(causalInsightCount) 条可复盘" : "等待数据" } ?? "未加载",
                    attention: false
                )
            ]
        )
    }
}

// MARK: - Client

/// 「健康进阶」四个已上线能力的客户端。对标 `OriginatorClient` / `LiverHealthClient`:
/// 主路径失败抛错让 UI 显示错误态,不静默吞错。
public final class HealthExtrasClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// ① 拉多药梳理 / 减药候选。失败抛错(UI 显示错误态)。
    public func fetchDeprescribingReview() async throws -> DeprescribingReview {
        try await apiClient.get("medication/deprescribing-review/me")
    }

    /// ② 拉社会连接自评状态。
    public func fetchConnectionStatus() async throws -> ConnectionStatus {
        try await apiClient.get("chronic/connection")
    }

    /// ② 提交一次社会连接自评。
    public func submitConnectionCheckin(
        uclaScore: Int,
        hasConfidant: Bool,
        inStableGroup: Bool,
        notes: String? = nil
    ) async throws -> ConnectionCheckinResponse {
        let body = ConnectionCheckinRequest(
            uclaScore: uclaScore,
            hasConfidant: hasConfidant,
            inStableGroup: inStableGroup,
            notes: notes
        )
        return try await apiClient.post("chronic/connection", body: body)
    }

    /// ③ 拉时滞因果(用药→指标描述性关联)。
    public func fetchCausalLinks() async throws -> CausalLinksReport {
        try await apiClient.get("chronic/causal-links")
    }

    /// ④ 拉数据正确性自检。
    public func fetchIntegrityReport() async throws -> IntegrityReport {
        try await apiClient.get("data-health/integrity")
    }
}
