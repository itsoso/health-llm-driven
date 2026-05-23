import Foundation

public struct DesktopBootstrap: Decodable, Equatable, Sendable {
    public let user: DesktopUser
    public let modelPreference: ModelPreference
    public let dailyPlan: DailyOperatingPlan
    public let trajectory: TrajectorySummary
    public let actionCards: [ActionCardSummary]
    public let recentMemory: [MemoryFactSummary]
    public let recentRecordsSummary: RecentRecordsSummary
    public let activeJobs: [DesktopJobSummary]

    enum CodingKeys: String, CodingKey {
        case user
        case modelPreference = "model_preference"
        case dailyPlan = "daily_plan"
        case trajectory
        case actionCards = "action_cards"
        case recentMemory = "recent_memory"
        case recentRecordsSummary = "recent_records_summary"
        case activeJobs = "active_jobs"
    }
}

public struct DesktopUser: Decodable, Equatable, Sendable {
    public let id: Int
    public let name: String?
    public let email: String?
}

public struct ModelPreference: Decodable, Equatable, Sendable {
    public let llmModelID: String?

    enum CodingKeys: String, CodingKey {
        case llmModelID = "llm_model_id"
    }
}

public struct DailyOperatingPlan: Decodable, Equatable, Sendable {
    public let planDate: String
    public let actions: [DailyPlanAction]

    enum CodingKeys: String, CodingKey {
        case planDate = "plan_date"
        case actions
    }
}

public struct DailyPlanAction: Decodable, Equatable, Identifiable, Sendable {
    public let actionKey: String?
    public let title: String
    public let domain: String?

    public var id: String { actionKey ?? title }

    enum CodingKeys: String, CodingKey {
        case actionKey = "action_key"
        case title
        case domain
    }
}

public struct TrajectorySummary: Decodable, Equatable, Sendable {
    public let focusDomains: [String]?

    enum CodingKeys: String, CodingKey {
        case focusDomains = "focus_domains"
    }
}

public struct ActionCardSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let title: String
    public let status: String?
    public let priority: Int?
}

public struct MemoryFactSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let objectValue: String

    enum CodingKeys: String, CodingKey {
        case id
        case objectValue = "object_value"
    }
}

public struct RecentRecordsSummary: Decodable, Equatable, Sendable {
    public let date: String?
    public let rangeDays: Int?
    public let diet: DietRecordSummary?
    public let water: WaterRecordSummary?
    public let latestWeight: DesktopRecordMetric?
    public let latestBloodPressure: DesktopRecordMetric?
    public let latestGarmin: GarminMetricSummary?
    public let recentRecords: [DesktopRecordMetric]?

    public init(
        diet: DietRecordSummary? = nil,
        water: WaterRecordSummary? = nil,
        date: String? = nil,
        rangeDays: Int? = nil,
        latestWeight: DesktopRecordMetric? = nil,
        latestBloodPressure: DesktopRecordMetric? = nil,
        latestGarmin: GarminMetricSummary? = nil,
        recentRecords: [DesktopRecordMetric]? = nil
    ) {
        self.date = date
        self.rangeDays = rangeDays
        self.diet = diet
        self.water = water
        self.latestWeight = latestWeight
        self.latestBloodPressure = latestBloodPressure
        self.latestGarmin = latestGarmin
        self.recentRecords = recentRecords
    }

    enum CodingKeys: String, CodingKey {
        case date
        case rangeDays = "range_days"
        case diet
        case water
        case latestWeight = "latest_weight"
        case latestBloodPressure = "latest_blood_pressure"
        case latestGarmin = "latest_garmin"
        case recentRecords = "recent_records"
    }
}

public struct DietRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayCalories: Double?
    public let last30Count: Int?
    public let last30Calories: Double?

    public init(
        todayCount: Int? = nil,
        todayCalories: Double? = nil,
        last30Count: Int? = nil,
        last30Calories: Double? = nil
    ) {
        self.todayCount = todayCount
        self.todayCalories = todayCalories
        self.last30Count = last30Count
        self.last30Calories = last30Calories
    }

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayCalories = "today_calories"
        case last30Count = "last_30_count"
        case last30Calories = "last_30_calories"
    }
}

public struct WaterRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayTotalMl: Int?
    public let last30Count: Int?
    public let last30TotalMl: Int?

    public init(
        todayCount: Int? = nil,
        todayTotalMl: Int? = nil,
        last30Count: Int? = nil,
        last30TotalMl: Int? = nil
    ) {
        self.todayCount = todayCount
        self.todayTotalMl = todayTotalMl
        self.last30Count = last30Count
        self.last30TotalMl = last30TotalMl
    }

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayTotalMl = "today_total_ml"
        case last30Count = "last_30_count"
        case last30TotalMl = "last_30_total_ml"
    }
}

public struct DesktopRecordMetric: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let type: String
    public let title: String
    public let value: JSONValue?
    public let unit: String?
    public let category: String?
    public let recordDate: String?

    public var displayValue: String {
        let rawValue: String
        switch value {
        case .string(let value):
            rawValue = value
        case .int(let value):
            rawValue = "\(value)"
        case .double(let value):
            rawValue = value.formatted(.number.precision(.fractionLength(0...1)))
        case .bool(let value):
            rawValue = value ? "true" : "false"
        case .object, .array, .null, nil:
            rawValue = "—"
        }
        guard let unit, !unit.isEmpty, rawValue != "—" else {
            return rawValue
        }
        return "\(rawValue) \(unit)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case title
        case value
        case unit
        case category
        case recordDate = "record_date"
    }
}

public struct GarminMetricSummary: Decodable, Equatable, Sendable {
    public let id: Int
    public let type: String?
    public let title: String?
    public let recordDate: String?
    public let steps: Int?
    public let sleepScore: Int?
    public let spo2Avg: Double?
    public let restingHeartRate: Int?
    public let hrv: Double?
    public let trainingReadinessScore: Int?

    enum CodingKeys: String, CodingKey {
        case id
        case type
        case title
        case recordDate = "record_date"
        case steps
        case sleepScore = "sleep_score"
        case spo2Avg = "spo2_avg"
        case restingHeartRate = "resting_heart_rate"
        case hrv
        case trainingReadinessScore = "training_readiness_score"
    }
}

public struct DesktopJobSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let jobType: String
    public let status: String
    public let progress: Int
    public let sourceKind: String?
    public let sourceName: String?
    public let sourceHash: String?
    public let requestPayload: [String: JSONValue]?
    public let resultPayload: [String: JSONValue]?
    public let errorMessage: String?
    public let retryOfJobID: Int?
    public let createdAt: String?
    public let updatedAt: String?
    public let startedAt: String?
    public let completedAt: String?

    public init(
        id: Int,
        jobType: String,
        status: String,
        progress: Int,
        sourceKind: String? = nil,
        sourceName: String? = nil,
        sourceHash: String? = nil,
        requestPayload: [String: JSONValue]? = nil,
        resultPayload: [String: JSONValue]? = nil,
        errorMessage: String? = nil,
        retryOfJobID: Int? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil,
        startedAt: String? = nil,
        completedAt: String? = nil
    ) {
        self.id = id
        self.jobType = jobType
        self.status = status
        self.progress = progress
        self.sourceKind = sourceKind
        self.sourceName = sourceName
        self.sourceHash = sourceHash
        self.requestPayload = requestPayload
        self.resultPayload = resultPayload
        self.errorMessage = errorMessage
        self.retryOfJobID = retryOfJobID
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.startedAt = startedAt
        self.completedAt = completedAt
    }

    enum CodingKeys: String, CodingKey {
        case id
        case jobType = "job_type"
        case status
        case progress
        case sourceKind = "source_kind"
        case sourceName = "source_name"
        case sourceHash = "source_hash"
        case requestPayload = "request_payload"
        case resultPayload = "result_payload"
        case errorMessage = "error_message"
        case retryOfJobID = "retry_of_job_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
    }
}
