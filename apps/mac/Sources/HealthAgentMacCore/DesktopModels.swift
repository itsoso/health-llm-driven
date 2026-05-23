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
    public let diet: DietRecordSummary?
    public let water: WaterRecordSummary?
}

public struct DietRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayCalories: Double?

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayCalories = "today_calories"
    }
}

public struct WaterRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayTotalMl: Int?

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayTotalMl = "today_total_ml"
    }
}

public struct DesktopJobSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let jobType: String
    public let status: String
    public let progress: Int

    enum CodingKeys: String, CodingKey {
        case id
        case jobType = "job_type"
        case status
        case progress
    }
}
