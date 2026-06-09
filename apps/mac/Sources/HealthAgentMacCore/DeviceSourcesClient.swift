import Foundation

// MARK: - /devices/sources/summary

/// 一个数据来源 (穿戴设备/App) 在时间窗内的覆盖天数与最新一组指标。
/// 对应后端 `GET /devices/sources/summary` 的 `sources[]` 单条。
/// `metrics` 各字段都可能为 null/缺失 (不同设备能力不同),解码时全部可选。
public struct DeviceSourceSummary: Codable, Equatable, Sendable, Identifiable {
    public let dataSource: String
    public let daysCovered: Int
    public let latestDate: String?
    public let metrics: DeviceSourceMetrics

    /// `data_source` 在一个用户的来源列表里唯一,可直接做 SwiftUI id。
    public var id: String { dataSource }

    enum CodingKeys: String, CodingKey {
        case dataSource = "data_source"
        case daysCovered = "days_covered"
        case latestDate = "latest_date"
        case metrics
    }

    public init(
        dataSource: String,
        daysCovered: Int,
        latestDate: String? = nil,
        metrics: DeviceSourceMetrics = DeviceSourceMetrics()
    ) {
        self.dataSource = dataSource
        self.daysCovered = daysCovered
        self.latestDate = latestDate
        self.metrics = metrics
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.dataSource = try container.decode(String.self, forKey: .dataSource)
        self.daysCovered = try container.decodeIfPresent(Int.self, forKey: .daysCovered) ?? 0
        self.latestDate = try container.decodeIfPresent(String.self, forKey: .latestDate)
        // metrics 整块可能缺失 — 缺失时给空指标,绝不让整条来源解码失败。
        self.metrics = try container.decodeIfPresent(DeviceSourceMetrics.self, forKey: .metrics)
            ?? DeviceSourceMetrics()
    }
}

/// 单个来源最新一天的指标快照。每项都可空 (设备不上报 → 不显示该格)。
public struct DeviceSourceMetrics: Codable, Equatable, Sendable {
    public let steps: Int?
    public let restingHeartRate: Int?
    public let hrv: Double?
    public let totalSleepDuration: Int?   // 分钟
    public let sleepScore: Int?
    public let spo2Avg: Double?
    public let spo2Min: Double?
    public let avgHeartRate: Int?
    public let activeCalories: Int?
    public let distanceMeters: Double?

    enum CodingKeys: String, CodingKey {
        case steps
        case restingHeartRate = "resting_heart_rate"
        case hrv
        case totalSleepDuration = "total_sleep_duration"
        case sleepScore = "sleep_score"
        case spo2Avg = "spo2_avg"
        case spo2Min = "spo2_min"
        case avgHeartRate = "avg_heart_rate"
        case activeCalories = "active_calories"
        case distanceMeters = "distance_meters"
    }

    public init(
        steps: Int? = nil,
        restingHeartRate: Int? = nil,
        hrv: Double? = nil,
        totalSleepDuration: Int? = nil,
        sleepScore: Int? = nil,
        spo2Avg: Double? = nil,
        spo2Min: Double? = nil,
        avgHeartRate: Int? = nil,
        activeCalories: Int? = nil,
        distanceMeters: Double? = nil
    ) {
        self.steps = steps
        self.restingHeartRate = restingHeartRate
        self.hrv = hrv
        self.totalSleepDuration = totalSleepDuration
        self.sleepScore = sleepScore
        self.spo2Avg = spo2Avg
        self.spo2Min = spo2Min
        self.avgHeartRate = avgHeartRate
        self.activeCalories = activeCalories
        self.distanceMeters = distanceMeters
    }
}

/// 对应 `GET /devices/sources/summary` 整体响应。
public struct DeviceSourcesResponse: Codable, Equatable, Sendable {
    public let windowDays: Int
    public let sources: [DeviceSourceSummary]

    enum CodingKeys: String, CodingKey {
        case windowDays = "window_days"
        case sources
    }

    public init(windowDays: Int, sources: [DeviceSourceSummary]) {
        self.windowDays = windowDays
        self.sources = sources
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.windowDays = try container.decodeIfPresent(Int.self, forKey: .windowDays) ?? 0
        self.sources = try container.decodeIfPresent([DeviceSourceSummary].self, forKey: .sources) ?? []
    }
}

// MARK: - /devices/compare

/// 一条跨来源的指标对比 (对应后端 `comparisons[]` 单条)。
/// `bySource` 是 {data_source: value};只在 ≥2 个来源都报告该指标时才有意义。
public struct DeviceComparison: Codable, Equatable, Sendable, Identifiable {
    public let metric: String
    public let label: String
    public let unit: String?
    public let bySource: [String: Double]
    public let diff: Double?
    public let agreement: String?

    public var id: String { metric }

    enum CodingKeys: String, CodingKey {
        case metric
        case label
        case unit
        case bySource = "by_source"
        case diff
        case agreement
    }

    public init(
        metric: String,
        label: String,
        unit: String? = nil,
        bySource: [String: Double] = [:],
        diff: Double? = nil,
        agreement: String? = nil
    ) {
        self.metric = metric
        self.label = label
        self.unit = unit
        self.bySource = bySource
        self.diff = diff
        self.agreement = agreement
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.metric = try container.decode(String.self, forKey: .metric)
        let decodedLabel = try container.decodeIfPresent(String.self, forKey: .label)
        self.label = decodedLabel ?? self.metric
        self.unit = try container.decodeIfPresent(String.self, forKey: .unit)
        self.bySource = try container.decodeIfPresent([String: Double].self, forKey: .bySource) ?? [:]
        self.diff = try container.decodeIfPresent(Double.self, forKey: .diff)
        self.agreement = try container.decodeIfPresent(String.self, forKey: .agreement)
    }
}

/// 对应 `GET /devices/compare` 整体响应。
public struct DeviceComparisonResponse: Codable, Equatable, Sendable {
    public let windowDays: Int
    public let sources: [String]
    public let comparisons: [DeviceComparison]
    public let note: String?

    enum CodingKeys: String, CodingKey {
        case windowDays = "window_days"
        case sources
        case comparisons
        case note
    }

    public init(
        windowDays: Int = 0,
        sources: [String] = [],
        comparisons: [DeviceComparison] = [],
        note: String? = nil
    ) {
        self.windowDays = windowDays
        self.sources = sources
        self.comparisons = comparisons
        self.note = note
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.windowDays = try container.decodeIfPresent(Int.self, forKey: .windowDays) ?? 0
        self.sources = try container.decodeIfPresent([String].self, forKey: .sources) ?? []
        self.comparisons = try container.decodeIfPresent([DeviceComparison].self, forKey: .comparisons) ?? []
        self.note = try container.decodeIfPresent(String.self, forKey: .note)
    }
}

// MARK: - Display mapping (pure, testable)

/// 把后端的 `data_source` 标签映射成给人看的设备名 + 图标。
/// 纯函数、无 locale 依赖,核心库里可单测。具体型号 (Ultra 3 / Gen3) 后端
/// 拿不到准确版本时退回到品牌名,绝不假装知道型号。
public enum DeviceSourceDisplay {
    /// 友好显示名。未知标签原样返回 (不假装识别)。
    public static func name(for dataSource: String) -> String {
        switch dataSource.lowercased() {
        case "apple-watch", "apple_watch", "applewatch": return "Apple Watch"
        case "ringconn": return "RingConn Gen3"
        case "garmin": return "Garmin"
        case "oura": return "Oura Ring"
        case "withings-app", "withings_app", "withings": return "Withings"
        case "unknown", "": return "未知来源"
        default: return dataSource
        }
    }

    /// 卡片头部用的 SF Symbol。
    public static func systemImage(for dataSource: String) -> String {
        switch dataSource.lowercased() {
        case "apple-watch", "apple_watch", "applewatch": return "applewatch"
        case "ringconn", "oura": return "circle.circle"
        case "garmin": return "figure.run"
        case "withings-app", "withings_app", "withings": return "scalemass"
        default: return "dot.radiowaves.left.and.right"
        }
    }
}

/// 把分钟数格式化成「Xh Ym」/「Xh」/「Ym」。min<=0 或 nil 返回 nil。
/// 纯函数,核心库里单测。
public enum DurationFormat {
    public static func minutesToHours(_ minutes: Int?) -> String? {
        guard let minutes, minutes > 0 else { return nil }
        let h = minutes / 60
        let m = minutes % 60
        if h > 0 && m > 0 { return "\(h)h \(m)m" }
        if h > 0 { return "\(h)h" }
        return "\(m)m"
    }
}

// MARK: - Client

/// 拉「数据来源」页所需数据。summary 是主路径 (失败抛错,让 UI 显示错误态);
/// compare 是 best-effort 次要信息 (失败返回 nil,不打断页面)。
public final class DeviceSourcesClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchSourcesSummary(days: Int = 30) async throws -> DeviceSourcesResponse {
        try await apiClient.get("devices/sources/summary?days=\(days)")
    }

    /// best-effort:任何失败 (网络/解码/端点不存在) 都返回 nil,调用方据此隐藏对比区。
    public func fetchComparison(days: Int = 7) async -> DeviceComparisonResponse? {
        try? await apiClient.get("devices/compare?days=\(days)")
    }
}
