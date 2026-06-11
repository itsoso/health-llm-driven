import Foundation

// MARK: - Liver health models
//
// 消费后端 `GET /chronic/liver`（P0①，见 PR #121）。所有字段一律 `decodeIfPresent`
// 容错：后端字段缺失 / 为 null 时绝不让整条记录解码失败，也绝不臆造数据 —— 没有
// 趋势数据就如实显示「数据不足」。这只是趋势提示，不是诊断。

/// 一条指标趋势（ALT / GGT 共用结构）。`verdict` ∈ improving|worsening|stable。
public struct LiverTrend: Codable, Equatable, Sendable {
    public let n: Int
    public let firstValue: Double?
    public let lastValue: Double?
    public let firstDate: String?
    public let lastDate: String?
    public let pctChange: Double?
    public let direction: String?
    public let verdict: String?

    public init(
        n: Int = 0,
        firstValue: Double? = nil,
        lastValue: Double? = nil,
        firstDate: String? = nil,
        lastDate: String? = nil,
        pctChange: Double? = nil,
        direction: String? = nil,
        verdict: String? = nil
    ) {
        self.n = n
        self.firstValue = firstValue
        self.lastValue = lastValue
        self.firstDate = firstDate
        self.lastDate = lastDate
        self.pctChange = pctChange
        self.direction = direction
        self.verdict = verdict
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.n = try container.decodeIfPresent(Int.self, forKey: .n) ?? 0
        self.firstValue = try container.decodeIfPresent(Double.self, forKey: .firstValue)
        self.lastValue = try container.decodeIfPresent(Double.self, forKey: .lastValue)
        self.firstDate = try container.decodeIfPresent(String.self, forKey: .firstDate)
        self.lastDate = try container.decodeIfPresent(String.self, forKey: .lastDate)
        self.pctChange = try container.decodeIfPresent(Double.self, forKey: .pctChange)
        self.direction = try container.decodeIfPresent(String.self, forKey: .direction)
        self.verdict = try container.decodeIfPresent(String.self, forKey: .verdict)
    }

    /// 归一化裁决（小写裁掉空白），未知值退回 nil。UI 用它决定配色。
    public var normalizedVerdict: LiverTrendVerdict? {
        guard let verdict else { return nil }
        return LiverTrendVerdict(rawValue: verdict.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    enum CodingKeys: String, CodingKey {
        case n
        case firstValue = "first_value"
        case lastValue = "last_value"
        case firstDate = "first_date"
        case lastDate = "last_date"
        case pctChange = "pct_change"
        case direction
        case verdict
    }
}

/// 趋势裁决配色枚举。后端给原始字符串，这里收敛到三态便于 UI 着色。
public enum LiverTrendVerdict: String, Equatable, Sendable {
    case improving
    case worsening
    case stable
}

/// 对应 `GET /chronic/liver` 整体响应。
public struct LiverHealthReport: Codable, Equatable, Sendable {
    public let available: Bool
    public let reason: String?

    public let altLatest: Double?
    public let astLatest: Double?
    public let ggtLatest: Double?
    public let plateletsLatest: Double?
    public let tgLatest: Double?
    public let astAltRatio: Double?

    public let altTrend: LiverTrend?
    public let ggtTrend: LiverTrend?

    public let fib4: Double?
    public let fib4Band: String?
    public let fattyLiverRisk: String?

    public let summaryLines: [String]
    public let advice: [String]

    public init(
        available: Bool = false,
        reason: String? = nil,
        altLatest: Double? = nil,
        astLatest: Double? = nil,
        ggtLatest: Double? = nil,
        plateletsLatest: Double? = nil,
        tgLatest: Double? = nil,
        astAltRatio: Double? = nil,
        altTrend: LiverTrend? = nil,
        ggtTrend: LiverTrend? = nil,
        fib4: Double? = nil,
        fib4Band: String? = nil,
        fattyLiverRisk: String? = nil,
        summaryLines: [String] = [],
        advice: [String] = []
    ) {
        self.available = available
        self.reason = reason
        self.altLatest = altLatest
        self.astLatest = astLatest
        self.ggtLatest = ggtLatest
        self.plateletsLatest = plateletsLatest
        self.tgLatest = tgLatest
        self.astAltRatio = astAltRatio
        self.altTrend = altTrend
        self.ggtTrend = ggtTrend
        self.fib4 = fib4
        self.fib4Band = fib4Band
        self.fattyLiverRisk = fattyLiverRisk
        self.summaryLines = summaryLines
        self.advice = advice
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.available = try container.decodeIfPresent(Bool.self, forKey: .available) ?? false
        self.reason = try container.decodeIfPresent(String.self, forKey: .reason)
        self.altLatest = try container.decodeIfPresent(Double.self, forKey: .altLatest)
        self.astLatest = try container.decodeIfPresent(Double.self, forKey: .astLatest)
        self.ggtLatest = try container.decodeIfPresent(Double.self, forKey: .ggtLatest)
        self.plateletsLatest = try container.decodeIfPresent(Double.self, forKey: .plateletsLatest)
        self.tgLatest = try container.decodeIfPresent(Double.self, forKey: .tgLatest)
        self.astAltRatio = try container.decodeIfPresent(Double.self, forKey: .astAltRatio)
        self.altTrend = try container.decodeIfPresent(LiverTrend.self, forKey: .altTrend)
        self.ggtTrend = try container.decodeIfPresent(LiverTrend.self, forKey: .ggtTrend)
        self.fib4 = try container.decodeIfPresent(Double.self, forKey: .fib4)
        self.fib4Band = try container.decodeIfPresent(String.self, forKey: .fib4Band)
        self.fattyLiverRisk = try container.decodeIfPresent(String.self, forKey: .fattyLiverRisk)
        self.summaryLines = try container.decodeIfPresent([String].self, forKey: .summaryLines) ?? []
        self.advice = try container.decodeIfPresent([String].self, forKey: .advice) ?? []
    }

    /// FIB-4 是否可评估。后端缺血小板时 `fib4 == nil` —— UI 据此显示灰字提示
    /// 「缺血小板，补血常规即可评估」，而不是装作有结果。
    public var hasFib4: Bool { fib4 != nil }

    /// 脂肪肝风险是否偏高（用于橙色高亮）。后端给的是中文/英文风险词，这里只做
    /// 「是否含偏高/高」的判断，未知词当作普通显示。
    public var fattyLiverRiskElevated: Bool {
        guard let risk = fattyLiverRisk?.lowercased() else { return false }
        return risk.contains("高") || risk.contains("high") || risk.contains("elevated")
    }

    enum CodingKeys: String, CodingKey {
        case available
        case reason
        case altLatest = "alt_latest"
        case astLatest = "ast_latest"
        case ggtLatest = "ggt_latest"
        case plateletsLatest = "platelets_latest"
        case tgLatest = "tg_latest"
        case astAltRatio = "ast_alt_ratio"
        case altTrend = "alt_trend"
        case ggtTrend = "ggt_trend"
        case fib4
        case fib4Band = "fib4_band"
        case fattyLiverRisk = "fatty_liver_risk"
        case summaryLines = "summary_lines"
        case advice
    }
}

// MARK: - Client

/// 肝脏趋势。对标 `OriginatorClient` / `DeviceSourcesClient`：主路径失败抛错让 UI
/// 显示错误态，不静默吞错。
public final class LiverHealthClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    /// 拉肝脏趋势报告。失败抛错（UI 显示错误态）。
    public func fetchReport() async throws -> LiverHealthReport {
        try await apiClient.get("chronic/liver")
    }
}
