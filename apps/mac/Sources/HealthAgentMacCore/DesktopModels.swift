import Foundation

public struct DesktopBootstrap: Decodable, Equatable, Sendable {
    public let user: DesktopUser
    public let modelPreference: ModelPreference
    public let dailyPlan: DailyOperatingPlan
    public let trajectory: TrajectorySummary
    public let actionCards: [ActionCardSummary]
    public let recentMemory: [MemoryFactSummary]
    public let recentRecordsSummary: RecentRecordsSummary
    public let genomicSummary: GenomicSummary?
    public let knowledgeSummary: KnowledgeSummary?
    public let activeJobs: [DesktopJobSummary]

    public init(
        user: DesktopUser,
        modelPreference: ModelPreference,
        dailyPlan: DailyOperatingPlan,
        trajectory: TrajectorySummary,
        actionCards: [ActionCardSummary],
        recentMemory: [MemoryFactSummary],
        recentRecordsSummary: RecentRecordsSummary,
        genomicSummary: GenomicSummary? = nil,
        knowledgeSummary: KnowledgeSummary? = nil,
        activeJobs: [DesktopJobSummary]
    ) {
        self.user = user
        self.modelPreference = modelPreference
        self.dailyPlan = dailyPlan
        self.trajectory = trajectory
        self.actionCards = actionCards
        self.recentMemory = recentMemory
        self.recentRecordsSummary = recentRecordsSummary
        self.genomicSummary = genomicSummary
        self.knowledgeSummary = knowledgeSummary
        self.activeJobs = activeJobs
    }

    enum CodingKeys: String, CodingKey {
        case user
        case modelPreference = "model_preference"
        case dailyPlan = "daily_plan"
        case trajectory
        case actionCards = "action_cards"
        case recentMemory = "recent_memory"
        case recentRecordsSummary = "recent_records_summary"
        case genomicSummary = "genomic_summary"
        case knowledgeSummary = "knowledge_summary"
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
    public let availableRanges: [Int]?
    public let diet: DietRecordSummary?
    public let water: WaterRecordSummary?
    public let supplements: SupplementRecordSummary?
    public let latestWeight: DesktopRecordMetric?
    public let latestBloodPressure: DesktopRecordMetric?
    public let latestGarmin: GarminMetricSummary?
    public let recentRecords: [DesktopRecordMetric]?

    public init(
        diet: DietRecordSummary? = nil,
        water: WaterRecordSummary? = nil,
        date: String? = nil,
        rangeDays: Int? = nil,
        availableRanges: [Int]? = nil,
        latestWeight: DesktopRecordMetric? = nil,
        latestBloodPressure: DesktopRecordMetric? = nil,
        latestGarmin: GarminMetricSummary? = nil,
        recentRecords: [DesktopRecordMetric]? = nil,
        supplements: SupplementRecordSummary? = nil
    ) {
        self.date = date
        self.rangeDays = rangeDays
        self.availableRanges = availableRanges
        self.diet = diet
        self.water = water
        self.supplements = supplements
        self.latestWeight = latestWeight
        self.latestBloodPressure = latestBloodPressure
        self.latestGarmin = latestGarmin
        self.recentRecords = recentRecords
    }

    enum CodingKeys: String, CodingKey {
        case date
        case rangeDays = "range_days"
        case availableRanges = "available_ranges"
        case diet
        case water
        case supplements
        case latestWeight = "latest_weight"
        case latestBloodPressure = "latest_blood_pressure"
        case latestGarmin = "latest_garmin"
        case recentRecords = "recent_records"
    }
}

public struct DietRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayCalories: Double?
    public let last7Count: Int?
    public let last7Calories: Double?
    public let last7AvgCalories: Double?
    public let last30Count: Int?
    public let last30Calories: Double?
    public let last30AvgCalories: Double?
    public let daily7: [DietDailyPoint]?
    public let daily30: [DietDailyPoint]?

    public init(
        todayCount: Int? = nil,
        todayCalories: Double? = nil,
        last7Count: Int? = nil,
        last7Calories: Double? = nil,
        last7AvgCalories: Double? = nil,
        last30Count: Int? = nil,
        last30Calories: Double? = nil,
        last30AvgCalories: Double? = nil,
        daily7: [DietDailyPoint]? = nil,
        daily30: [DietDailyPoint]? = nil
    ) {
        self.todayCount = todayCount
        self.todayCalories = todayCalories
        self.last7Count = last7Count
        self.last7Calories = last7Calories
        self.last7AvgCalories = last7AvgCalories
        self.last30Count = last30Count
        self.last30Calories = last30Calories
        self.last30AvgCalories = last30AvgCalories
        self.daily7 = daily7
        self.daily30 = daily30
    }

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayCalories = "today_calories"
        case last7Count = "last_7_count"
        case last7Calories = "last_7_calories"
        case last7AvgCalories = "last_7_avg_calories"
        case last30Count = "last_30_count"
        case last30Calories = "last_30_calories"
        case last30AvgCalories = "last_30_avg_calories"
        case daily7 = "daily_7"
        case daily30 = "daily_30"
    }
}

public struct WaterRecordSummary: Decodable, Equatable, Sendable {
    public let todayCount: Int?
    public let todayTotalMl: Int?
    public let last7Count: Int?
    public let last7TotalMl: Int?
    public let last7AvgMl: Double?
    public let last30Count: Int?
    public let last30TotalMl: Int?
    public let last30AvgMl: Double?
    public let daily7: [WaterDailyPoint]?
    public let daily30: [WaterDailyPoint]?

    public init(
        todayCount: Int? = nil,
        todayTotalMl: Int? = nil,
        last7Count: Int? = nil,
        last7TotalMl: Int? = nil,
        last7AvgMl: Double? = nil,
        last30Count: Int? = nil,
        last30TotalMl: Int? = nil,
        last30AvgMl: Double? = nil,
        daily7: [WaterDailyPoint]? = nil,
        daily30: [WaterDailyPoint]? = nil
    ) {
        self.todayCount = todayCount
        self.todayTotalMl = todayTotalMl
        self.last7Count = last7Count
        self.last7TotalMl = last7TotalMl
        self.last7AvgMl = last7AvgMl
        self.last30Count = last30Count
        self.last30TotalMl = last30TotalMl
        self.last30AvgMl = last30AvgMl
        self.daily7 = daily7
        self.daily30 = daily30
    }

    enum CodingKeys: String, CodingKey {
        case todayCount = "today_count"
        case todayTotalMl = "today_total_ml"
        case last7Count = "last_7_count"
        case last7TotalMl = "last_7_total_ml"
        case last7AvgMl = "last_7_avg_ml"
        case last30Count = "last_30_count"
        case last30TotalMl = "last_30_total_ml"
        case last30AvgMl = "last_30_avg_ml"
        case daily7 = "daily_7"
        case daily30 = "daily_30"
    }
}

public struct DietDailyPoint: Decodable, Equatable, Identifiable, Sendable {
    public let date: String
    public let count: Int
    public let calories: Double

    public var id: String { date }

    public init(date: String, count: Int, calories: Double) {
        self.date = date
        self.count = count
        self.calories = calories
    }
}

public struct WaterDailyPoint: Decodable, Equatable, Identifiable, Sendable {
    public let date: String
    public let count: Int
    public let totalMl: Int

    public var id: String { date }

    public init(date: String, count: Int, totalMl: Int) {
        self.date = date
        self.count = count
        self.totalMl = totalMl
    }

    enum CodingKeys: String, CodingKey {
        case date
        case count
        case totalMl = "total_ml"
    }
}

public struct SupplementRecordSummary: Decodable, Equatable, Sendable {
    public let activeCount: Int?
    public let todayCount: Int?
    public let last7Count: Int?
    public let last7AvgPerDay: Double?
    public let last30Count: Int?
    public let last30AvgPerDay: Double?
    public let adherence7Pct: Double?
    public let adherence30Pct: Double?
    public let daily7: [SupplementDailyPoint]?
    public let daily30: [SupplementDailyPoint]?
    public let topItems: [SupplementTopItem]?

    public init(
        activeCount: Int? = nil,
        todayCount: Int? = nil,
        last7Count: Int? = nil,
        last7AvgPerDay: Double? = nil,
        last30Count: Int? = nil,
        last30AvgPerDay: Double? = nil,
        adherence7Pct: Double? = nil,
        adherence30Pct: Double? = nil,
        daily7: [SupplementDailyPoint]? = nil,
        daily30: [SupplementDailyPoint]? = nil,
        topItems: [SupplementTopItem]? = nil
    ) {
        self.activeCount = activeCount
        self.todayCount = todayCount
        self.last7Count = last7Count
        self.last7AvgPerDay = last7AvgPerDay
        self.last30Count = last30Count
        self.last30AvgPerDay = last30AvgPerDay
        self.adherence7Pct = adherence7Pct
        self.adherence30Pct = adherence30Pct
        self.daily7 = daily7
        self.daily30 = daily30
        self.topItems = topItems
    }

    enum CodingKeys: String, CodingKey {
        case activeCount = "active_count"
        case todayCount = "today_count"
        case last7Count = "last_7_count"
        case last7AvgPerDay = "last_7_avg_per_day"
        case last30Count = "last_30_count"
        case last30AvgPerDay = "last_30_avg_per_day"
        case adherence7Pct = "adherence_7_pct"
        case adherence30Pct = "adherence_30_pct"
        case daily7 = "daily_7"
        case daily30 = "daily_30"
        case topItems = "top_items"
    }
}

public struct SupplementDailyPoint: Decodable, Equatable, Identifiable, Sendable {
    public let date: String
    public let count: Int

    public var id: String { date }

    public init(date: String, count: Int) {
        self.date = date
        self.count = count
    }
}

public struct SupplementTopItem: Decodable, Equatable, Identifiable, Sendable {
    public let name: String
    public let count: Int

    public var id: String { name }

    public init(name: String, count: Int) {
        self.name = name
        self.count = count
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

public struct GenomicSummary: Decodable, Equatable, Sendable {
    public let profileID: Int?
    public let provider: String?
    public let testDate: String?
    public let reportID: String?
    public let recordCount: Int
    public let highRiskCount: Int
    public let mediumRiskCount: Int
    public let lowRiskCount: Int
    public let infoCount: Int
    public let actionableCount: Int
    public let categoryCount: Int
    public let topCategories: [GenomicCategorySummary]
    public let topFindings: [GenomicFindingSummary]
    public let latestImport: GenomicImportSummary?

    enum CodingKeys: String, CodingKey {
        case profileID = "profile_id"
        case provider
        case testDate = "test_date"
        case reportID = "report_id"
        case recordCount = "record_count"
        case highRiskCount = "high_risk_count"
        case mediumRiskCount = "medium_risk_count"
        case lowRiskCount = "low_risk_count"
        case infoCount = "info_count"
        case actionableCount = "actionable_count"
        case categoryCount = "category_count"
        case topCategories = "top_categories"
        case topFindings = "top_findings"
        case latestImport = "latest_import"
    }
}

public struct GenomicCategorySummary: Decodable, Equatable, Identifiable, Sendable {
    public let category: String
    public let count: Int
    public let highRiskCount: Int
    public let mediumRiskCount: Int

    public var id: String { category }

    enum CodingKeys: String, CodingKey {
        case category
        case count
        case highRiskCount = "high_risk_count"
        case mediumRiskCount = "medium_risk_count"
    }
}

public struct GenomicFindingSummary: Decodable, Equatable, Identifiable, Sendable {
    public let id: Int
    public let rsid: String?
    public let category: String?
    public let geneName: String
    public let variantName: String?
    public let genotype: String?
    public let resultLabel: String?
    public let riskLevel: String?
    public let evidenceLevel: String?
    public let description: String?
    public let variantNature: String?

    public var displayTitle: String {
        if let variantName, !variantName.isEmpty {
            return "\(geneName) · \(variantName)"
        }
        return geneName
    }

    enum CodingKeys: String, CodingKey {
        case id
        case rsid
        case category
        case geneName = "gene_name"
        case variantName = "variant_name"
        case genotype
        case resultLabel = "result_label"
        case riskLevel = "risk_level"
        case evidenceLevel = "evidence_level"
        case description
        case variantNature = "variant_nature"
    }
}

public struct GenomicImportSummary: Decodable, Equatable, Sendable {
    public let status: String?
    public let sourceType: String?
    public let rawRecordCount: Int?
    public let matchedCount: Int?
    public let duplicateCount: Int?
    public let unknownCount: Int?
    public let finishedAt: String?
    public let rawFileHash: String?

    enum CodingKeys: String, CodingKey {
        case status
        case sourceType = "source_type"
        case rawRecordCount = "raw_record_count"
        case matchedCount = "matched_count"
        case duplicateCount = "duplicate_count"
        case unknownCount = "unknown_count"
        case finishedAt = "finished_at"
        case rawFileHash = "raw_file_hash"
    }
}

public struct KnowledgeSummary: Decodable, Equatable, Sendable {
    public let documentCount: Int
    public let claimCount: Int
    public let entityCount: Int
    public let articleCount: Int
    public let edgeCount: Int
    public let evidenceLevelCounts: [KnowledgeCount]
    public let sourceCounts: [KnowledgeSourceCount]
    public let recentDocuments: [KnowledgeDocumentSummary]

    enum CodingKeys: String, CodingKey {
        case documentCount = "document_count"
        case claimCount = "claim_count"
        case entityCount = "entity_count"
        case articleCount = "article_count"
        case edgeCount = "edge_count"
        case evidenceLevelCounts = "evidence_level_counts"
        case sourceCounts = "source_counts"
        case recentDocuments = "recent_documents"
    }
}

public struct KnowledgeCount: Decodable, Equatable, Identifiable, Sendable {
    public let level: String
    public let count: Int

    public var id: String { level }
}

public struct KnowledgeSourceCount: Decodable, Equatable, Identifiable, Sendable {
    public let source: String
    public let count: Int

    public var id: String { source }
}

public struct KnowledgeDocumentSummary: Decodable, Equatable, Identifiable, Sendable {
    public let docID: String
    public let docType: String
    public let title: String?
    public let summary: String?
    public let evidenceLevel: String?
    public let confidence: Double?
    public let sources: [String]

    public var id: String { docID }

    enum CodingKeys: String, CodingKey {
        case docID = "doc_id"
        case docType = "doc_type"
        case title
        case summary
        case evidenceLevel = "evidence_level"
        case confidence
        case sources
    }
}
