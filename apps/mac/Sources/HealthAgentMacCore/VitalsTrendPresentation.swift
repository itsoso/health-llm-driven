import Foundation

/// 一天的 Garmin 生理记录 (GET /daily-health/garmin/me 的单条响应)。
/// 只解码「数据指挥台」要展示的字段；睡眠各时段单位为分钟 (后端 `# 分钟`)。
public struct GarminDailyRecord: Decodable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let recordDate: String?
    public let hrv: Double?
    public let restingHeartRate: Int?
    public let avgHeartRate: Int?
    public let maxHeartRate: Int?
    public let stressLevel: Int?
    public let bodyBatteryCurrent: Int?
    public let bodyBatteryLowest: Int?
    public let sleepScore: Int?
    public let totalSleepMinutes: Int?
    public let deepSleepMinutes: Int?
    public let remSleepMinutes: Int?
    public let lightSleepMinutes: Int?
    public let awakeMinutes: Int?
    public let steps: Int?

    public init(
        id: Int,
        recordDate: String? = nil,
        hrv: Double? = nil,
        restingHeartRate: Int? = nil,
        avgHeartRate: Int? = nil,
        maxHeartRate: Int? = nil,
        stressLevel: Int? = nil,
        bodyBatteryCurrent: Int? = nil,
        bodyBatteryLowest: Int? = nil,
        sleepScore: Int? = nil,
        totalSleepMinutes: Int? = nil,
        deepSleepMinutes: Int? = nil,
        remSleepMinutes: Int? = nil,
        lightSleepMinutes: Int? = nil,
        awakeMinutes: Int? = nil,
        steps: Int? = nil
    ) {
        self.id = id
        self.recordDate = recordDate
        self.hrv = hrv
        self.restingHeartRate = restingHeartRate
        self.avgHeartRate = avgHeartRate
        self.maxHeartRate = maxHeartRate
        self.stressLevel = stressLevel
        self.bodyBatteryCurrent = bodyBatteryCurrent
        self.bodyBatteryLowest = bodyBatteryLowest
        self.sleepScore = sleepScore
        self.totalSleepMinutes = totalSleepMinutes
        self.deepSleepMinutes = deepSleepMinutes
        self.remSleepMinutes = remSleepMinutes
        self.lightSleepMinutes = lightSleepMinutes
        self.awakeMinutes = awakeMinutes
        self.steps = steps
    }

    enum CodingKeys: String, CodingKey {
        case id
        case recordDate = "record_date"
        case hrv
        case restingHeartRate = "resting_heart_rate"
        case avgHeartRate = "avg_heart_rate"
        case maxHeartRate = "max_heart_rate"
        case stressLevel = "stress_level"
        case bodyBatteryCurrent = "body_battery_current"
        case bodyBatteryLowest = "body_battery_lowest"
        case sleepScore = "sleep_score"
        case totalSleepMinutes = "total_sleep_duration"
        case deepSleepMinutes = "deep_sleep_duration"
        case remSleepMinutes = "rem_sleep_duration"
        case lightSleepMinutes = "light_sleep_duration"
        case awakeMinutes = "awake_duration"
        case steps
    }
}

/// 把若干天 Garmin 记录整理成「数据指挥台」要的最新快照 + 趋势序列。
/// 纯函数式、可单测 (不碰网络/locale)；数值格式化留给视图层。
public struct VitalsTrendPresentation: Equatable, Sendable {
    /// 趋势用的单一指标：按日期升序、已剔除缺值，附均值。
    public struct Series: Equatable, Sendable {
        public let points: [Double]
        public let average: Double?

        public init(points: [Double]) {
            self.points = points
            self.average = points.isEmpty ? nil : points.reduce(0, +) / Double(points.count)
        }
    }

    public struct SleepStages: Equatable, Sendable {
        public let deepMinutes: Int
        public let lightMinutes: Int
        public let remMinutes: Int
        public let awakeMinutes: Int

        public var totalMinutes: Int { deepMinutes + lightMinutes + remMinutes + awakeMinutes }
        public var hasData: Bool { totalMinutes > 0 }
    }

    /// 单日睡眠分期 (逐日趋势用)。
    public struct SleepStageDay: Equatable, Sendable, Identifiable {
        public let date: String
        public let deepMinutes: Int
        public let lightMinutes: Int
        public let remMinutes: Int
        public let awakeMinutes: Int

        public var id: String { date }
        public var totalMinutes: Int { deepMinutes + lightMinutes + remMinutes + awakeMinutes }

        public init(date: String, deepMinutes: Int, lightMinutes: Int, remMinutes: Int, awakeMinutes: Int) {
            self.date = date
            self.deepMinutes = deepMinutes
            self.lightMinutes = lightMinutes
            self.remMinutes = remMinutes
            self.awakeMinutes = awakeMinutes
        }
    }

    public let hasData: Bool
    public let latestDate: String?

    // 最新一天的快照值
    public let latestHRV: Double?
    public let latestRestingHR: Int?
    public let latestAvgHR: Int?
    public let latestStress: Int?
    public let latestBodyBattery: Int?
    public let latestBodyBatteryLowest: Int?
    public let latestSleepScore: Int?
    public let latestSleepHours: Double?
    public let sleepStages: SleepStages?
    /// 窗口内每天的睡眠分期 (升序，仅含有分期数据的天)。
    public let sleepStageDays: [SleepStageDay]

    // 趋势序列 (按日期升序)
    public let hrvSeries: Series
    public let restingHRSeries: Series
    public let avgHRSeries: Series
    public let stressSeries: Series
    public let bodyBatterySeries: Series
    public let sleepHoursSeries: Series

    public init(records: [GarminDailyRecord], lastDays: Int? = nil) {
        // 后端按日期倒序返回；统一成升序，便于趋势从左到右。
        let sorted = records.sorted { ($0.recordDate ?? "") < ($1.recordDate ?? "") }
        let scoped: [GarminDailyRecord]
        if let lastDays, lastDays > 0, sorted.count > lastDays {
            scoped = Array(sorted.suffix(lastDays))
        } else {
            scoped = sorted
        }

        self.hasData = !scoped.isEmpty
        let latest = scoped.last
        self.latestDate = latest?.recordDate

        self.latestHRV = latest?.hrv
        self.latestRestingHR = latest?.restingHeartRate
        self.latestAvgHR = latest?.avgHeartRate
        self.latestStress = latest?.stressLevel
        self.latestBodyBattery = latest?.bodyBatteryCurrent
        self.latestBodyBatteryLowest = latest?.bodyBatteryLowest
        self.latestSleepScore = latest?.sleepScore
        if let mins = latest?.totalSleepMinutes, mins > 0 {
            self.latestSleepHours = Double(mins) / 60.0
        } else {
            self.latestSleepHours = nil
        }

        if let latest,
           (latest.deepSleepMinutes ?? 0) + (latest.lightSleepMinutes ?? 0)
            + (latest.remSleepMinutes ?? 0) + (latest.awakeMinutes ?? 0) > 0 {
            self.sleepStages = SleepStages(
                deepMinutes: latest.deepSleepMinutes ?? 0,
                lightMinutes: latest.lightSleepMinutes ?? 0,
                remMinutes: latest.remSleepMinutes ?? 0,
                awakeMinutes: latest.awakeMinutes ?? 0
            )
        } else {
            self.sleepStages = nil
        }

        self.sleepStageDays = scoped.compactMap { rec in
            guard let date = rec.recordDate else { return nil }
            let deep = rec.deepSleepMinutes ?? 0
            let light = rec.lightSleepMinutes ?? 0
            let rem = rec.remSleepMinutes ?? 0
            let awake = rec.awakeMinutes ?? 0
            guard deep + light + rem + awake > 0 else { return nil }
            return SleepStageDay(date: date, deepMinutes: deep, lightMinutes: light, remMinutes: rem, awakeMinutes: awake)
        }

        self.hrvSeries = Series(points: scoped.compactMap(\.hrv))
        self.restingHRSeries = Series(points: scoped.compactMap { $0.restingHeartRate.map(Double.init) })
        self.avgHRSeries = Series(points: scoped.compactMap { $0.avgHeartRate.map(Double.init) })
        self.stressSeries = Series(points: scoped.compactMap { $0.stressLevel.map(Double.init) })
        self.bodyBatterySeries = Series(points: scoped.compactMap { $0.bodyBatteryCurrent.map(Double.init) })
        self.sleepHoursSeries = Series(points: scoped.compactMap {
            guard let mins = $0.totalSleepMinutes, mins > 0 else { return nil }
            return Double(mins) / 60.0
        })
    }
}

/// 拉「数据指挥台」生理趋势用的多日 Garmin 记录。best-effort：失败返回空，
/// 不打断页面其余部分 (与 NocturnalTimeseriesClient.fetchSpO2WeekSummary 同风格)。
public final class GarminTrendClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchDaily(limit: Int = 30) async -> [GarminDailyRecord] {
        let records: [GarminDailyRecord]? = try? await apiClient.get("daily-health/garmin/me?limit=\(limit)")
        return records ?? []
    }
}
