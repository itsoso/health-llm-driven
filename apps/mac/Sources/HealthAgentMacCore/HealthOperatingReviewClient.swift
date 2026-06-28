import Foundation

public struct HealthOperatingReview: Codable, Equatable, Sendable {
    public let windowDays: Int
    public let startDate: String
    public let endDate: String
    public let execution: HealthReviewExecutionSummary
    public let metrics: [String: HealthReviewMetricChange]
    public let completedActionKeys: [String]
    public let predictionBacktest: HealthReviewPredictionBacktest?

    enum CodingKeys: String, CodingKey {
        case windowDays = "window_days"
        case startDate = "start_date"
        case endDate = "end_date"
        case execution
        case metrics
        case completedActionKeys = "completed_action_keys"
        case predictionBacktest = "prediction_backtest"
    }

    public init(
        windowDays: Int,
        startDate: String,
        endDate: String,
        execution: HealthReviewExecutionSummary,
        metrics: [String: HealthReviewMetricChange] = [:],
        completedActionKeys: [String] = [],
        predictionBacktest: HealthReviewPredictionBacktest? = nil
    ) {
        self.windowDays = windowDays
        self.startDate = startDate
        self.endDate = endDate
        self.execution = execution
        self.metrics = metrics
        self.completedActionKeys = completedActionKeys
        self.predictionBacktest = predictionBacktest
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.windowDays = try container.decodeIfPresent(Int.self, forKey: .windowDays) ?? 30
        self.startDate = try container.decodeIfPresent(String.self, forKey: .startDate) ?? ""
        self.endDate = try container.decodeIfPresent(String.self, forKey: .endDate) ?? ""
        self.execution = try container.decodeIfPresent(HealthReviewExecutionSummary.self, forKey: .execution)
            ?? HealthReviewExecutionSummary()
        self.metrics = try container.decodeIfPresent([String: HealthReviewMetricChange].self, forKey: .metrics) ?? [:]
        self.completedActionKeys = try container.decodeIfPresent([String].self, forKey: .completedActionKeys) ?? []
        self.predictionBacktest = try container.decodeIfPresent(HealthReviewPredictionBacktest.self, forKey: .predictionBacktest)
    }
}

public struct HealthReviewExecutionSummary: Codable, Equatable, Sendable {
    public let totalEvents: Int
    public let completedEvents: Int
    public let completionRate: Double
    public let byStatus: [String: Int]
    public let byDomain: [String: Int]

    enum CodingKeys: String, CodingKey {
        case totalEvents = "total_events"
        case completedEvents = "completed_events"
        case completionRate = "completion_rate"
        case byStatus = "by_status"
        case byDomain = "by_domain"
    }

    public init(
        totalEvents: Int = 0,
        completedEvents: Int = 0,
        completionRate: Double = 0,
        byStatus: [String: Int] = [:],
        byDomain: [String: Int] = [:]
    ) {
        self.totalEvents = totalEvents
        self.completedEvents = completedEvents
        self.completionRate = completionRate
        self.byStatus = byStatus
        self.byDomain = byDomain
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.totalEvents = try container.decodeIfPresent(Int.self, forKey: .totalEvents) ?? 0
        self.completedEvents = try container.decodeIfPresent(Int.self, forKey: .completedEvents) ?? 0
        self.completionRate = try container.decodeIfPresent(Double.self, forKey: .completionRate) ?? 0
        self.byStatus = try container.decodeIfPresent([String: Int].self, forKey: .byStatus) ?? [:]
        self.byDomain = try container.decodeIfPresent([String: Int].self, forKey: .byDomain) ?? [:]
    }
}

public struct HealthReviewMetricChange: Codable, Equatable, Sendable {
    public let status: String
    public let count: Int
    public let first: Double?
    public let firstDate: String?
    public let current: Double?
    public let currentDate: String?
    public let delta: Double?

    enum CodingKeys: String, CodingKey {
        case status
        case count
        case first
        case firstDate = "first_date"
        case current
        case currentDate = "current_date"
        case delta
    }

    public init(
        status: String = "missing",
        count: Int = 0,
        first: Double? = nil,
        firstDate: String? = nil,
        current: Double? = nil,
        currentDate: String? = nil,
        delta: Double? = nil
    ) {
        self.status = status
        self.count = count
        self.first = first
        self.firstDate = firstDate
        self.current = current
        self.currentDate = currentDate
        self.delta = delta
    }
}

public struct HealthReviewPredictionBacktest: Codable, Equatable, Sendable {
    public let version: String
    public let status: String
    public let windowDays: Int
    public let candidateCount: Int
    public let readyCandidateCount: Int
    public let results: [HealthReviewPredictionBacktestResult]
    public let summary: HealthReviewPredictionBacktestSummary?
    public let boundary: String?

    enum CodingKeys: String, CodingKey {
        case version
        case status
        case windowDays = "window_days"
        case candidateCount = "candidate_count"
        case readyCandidateCount = "ready_candidate_count"
        case results
        case summary
        case boundary
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.version = try container.decodeIfPresent(String.self, forKey: .version) ?? ""
        self.status = try container.decodeIfPresent(String.self, forKey: .status) ?? "not_ready"
        self.windowDays = try container.decodeIfPresent(Int.self, forKey: .windowDays) ?? 30
        self.candidateCount = try container.decodeIfPresent(Int.self, forKey: .candidateCount) ?? 0
        self.readyCandidateCount = try container.decodeIfPresent(Int.self, forKey: .readyCandidateCount) ?? 0
        self.results = try container.decodeIfPresent([HealthReviewPredictionBacktestResult].self, forKey: .results) ?? []
        self.summary = try container.decodeIfPresent(HealthReviewPredictionBacktestSummary.self, forKey: .summary)
        self.boundary = try container.decodeIfPresent(String.self, forKey: .boundary)
    }
}

public struct HealthReviewPredictionBacktestSummary: Codable, Equatable, Sendable {
    public let met: Int
    public let notMet: Int
    public let inconclusive: Int

    enum CodingKeys: String, CodingKey {
        case met
        case notMet = "not_met"
        case inconclusive
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.met = try container.decodeIfPresent(Int.self, forKey: .met) ?? 0
        self.notMet = try container.decodeIfPresent(Int.self, forKey: .notMet) ?? 0
        self.inconclusive = try container.decodeIfPresent(Int.self, forKey: .inconclusive) ?? 0
    }
}

public struct HealthReviewPredictionBacktestResult: Codable, Equatable, Identifiable, Sendable {
    public let predictionID: String
    public let actionKey: String
    public let actionTitle: String
    public let metric: String
    public let verdict: String
    public let observedDelta: Double?
    public let confidenceBefore: String?
    public let confidenceAfter: String?
    public let confidenceChange: HealthReviewConfidenceChange?
    public let confidenceHistory: [HealthReviewConfidenceHistoryEntry]
    public let inconclusiveReason: String?
    public let requiresClinician: Bool?
    public let nextStep: HealthReviewPredictionNextStep?
    public let explanation: String?
    public let attribution: String?
    public let boundary: String?

    public var id: String { predictionID + "|" + metric }

    enum CodingKeys: String, CodingKey {
        case predictionID = "prediction_id"
        case actionKey = "action_key"
        case actionTitle = "action_title"
        case metric
        case verdict
        case observedDelta = "observed_delta"
        case confidenceBefore = "confidence_before"
        case confidenceAfter = "confidence_after"
        case confidenceChange = "confidence_change"
        case confidenceHistory = "confidence_history"
        case inconclusiveReason = "inconclusive_reason"
        case requiresClinician = "requires_clinician"
        case nextStep = "next_step"
        case explanation
        case attribution
        case boundary
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.predictionID = try container.decodeIfPresent(String.self, forKey: .predictionID) ?? UUID().uuidString
        self.actionKey = try container.decodeIfPresent(String.self, forKey: .actionKey) ?? ""
        self.actionTitle = try container.decodeIfPresent(String.self, forKey: .actionTitle) ?? self.actionKey
        self.metric = try container.decodeIfPresent(String.self, forKey: .metric) ?? ""
        self.verdict = try container.decodeIfPresent(String.self, forKey: .verdict) ?? "inconclusive"
        self.observedDelta = try container.decodeIfPresent(Double.self, forKey: .observedDelta)
        self.confidenceBefore = try container.decodeIfPresent(String.self, forKey: .confidenceBefore)
        self.confidenceAfter = try container.decodeIfPresent(String.self, forKey: .confidenceAfter)
        self.confidenceChange = try container.decodeIfPresent(HealthReviewConfidenceChange.self, forKey: .confidenceChange)
        self.confidenceHistory = try container.decodeIfPresent([HealthReviewConfidenceHistoryEntry].self, forKey: .confidenceHistory) ?? []
        self.inconclusiveReason = try container.decodeIfPresent(String.self, forKey: .inconclusiveReason)
        self.requiresClinician = try container.decodeIfPresent(Bool.self, forKey: .requiresClinician)
        self.nextStep = try container.decodeIfPresent(HealthReviewPredictionNextStep.self, forKey: .nextStep)
        self.explanation = try container.decodeIfPresent(String.self, forKey: .explanation)
        self.attribution = try container.decodeIfPresent(String.self, forKey: .attribution)
        self.boundary = try container.decodeIfPresent(String.self, forKey: .boundary)
    }
}

public struct HealthReviewConfidenceChange: Codable, Equatable, Sendable {
    public let before: String?
    public let after: String?
    public let direction: String?
}

public struct HealthReviewConfidenceHistoryEntry: Codable, Equatable, Sendable {
    public let stage: String
    public let confidence: String
    public let reason: String
}

public struct HealthReviewPredictionNextStep: Codable, Equatable, Sendable {
    public let action: String
    public let label: String
    public let reason: String
    public let replanHint: String?
    public let requiresClinician: Bool?

    enum CodingKeys: String, CodingKey {
        case action
        case label
        case reason
        case replanHint = "replan_hint"
        case requiresClinician = "requires_clinician"
    }
}

public enum HealthOperatingReviewPresentation {
    public static func nextStepSummary(for result: HealthReviewPredictionBacktestResult) -> String? {
        guard let label = result.nextStep?.label, !label.isEmpty else {
            return nil
        }
        let before = result.confidenceChange?.before ?? result.confidenceBefore
        let after = result.confidenceChange?.after ?? result.confidenceAfter
        let confidence = (before.flatMap { beforeValue in after.map { " · 置信度 \(beforeValue) → \($0)" } }) ?? ""
        return "下一步: \(label)\(confidence) · 观察性,非因果"
    }

    public static func completionPercent(_ review: HealthOperatingReview) -> Int {
        Int((review.execution.completionRate * 100).rounded())
    }

    public static func boundary(for backtest: HealthReviewPredictionBacktest?) -> String {
        backtest?.boundary ?? "观察性回测, 不证明单个行动造成指标变化。"
    }
}

public final class HealthOperatingReviewClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchReview(windowDays: Int = 30) async throws -> HealthOperatingReview {
        try await apiClient.get("daily-plan/review?window_days=\(windowDays)")
    }
}
