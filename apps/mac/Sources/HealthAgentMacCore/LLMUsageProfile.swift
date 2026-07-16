import Foundation

public struct LLMUsageCall: Codable, Equatable, Sendable {
    public let runID: String?
    public let provider: String?
    public let model: String?
    public let caller: String?
    public let promptTokens: Int?
    public let completionTokens: Int?
    public let totalTokens: Int?
    public let costUsd: Double?
    public let costCny: Double?
    public let costEstimated: Bool?
    public let costSource: String?
    public let tokenplanCreditsEstimate: Double?
    public let tokenplanCostCny: Double?
    public let tokenplanPaygValueCny: Double?
    public let tokenplanCostEstimated: Bool?
    public let tokenplanCostSource: String?
    public let latencyMs: Int?
    public let success: Bool?
    public let errorType: String?
    public let errorCode: String?
    public let errorMessage: String?
    public let recoveryAction: String?
    public let recoveryModel: String?

    private enum CodingKeys: String, CodingKey {
        case provider, model, caller, success
        case runID = "run_id"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case costUsd = "cost_usd"
        case costCny = "cost_cny"
        case costEstimated = "cost_estimated"
        case costSource = "cost_source"
        case tokenplanCreditsEstimate = "tokenplan_credits_estimate"
        case tokenplanCostCny = "tokenplan_cost_cny"
        case tokenplanPaygValueCny = "tokenplan_payg_value_cny"
        case tokenplanCostEstimated = "tokenplan_cost_estimated"
        case tokenplanCostSource = "tokenplan_cost_source"
        case latencyMs = "latency_ms"
        case errorType = "error_type"
        case errorCode = "error_code"
        case errorMessage = "error_message"
        case recoveryAction = "recovery_action"
        case recoveryModel = "recovery_model"
    }

    public init(
        runID: String? = nil,
        provider: String? = nil,
        model: String? = nil,
        caller: String? = nil,
        promptTokens: Int? = nil,
        completionTokens: Int? = nil,
        totalTokens: Int? = nil,
        costUsd: Double? = nil,
        costCny: Double? = nil,
        costEstimated: Bool? = nil,
        costSource: String? = nil,
        tokenplanCreditsEstimate: Double? = nil,
        tokenplanCostCny: Double? = nil,
        tokenplanPaygValueCny: Double? = nil,
        tokenplanCostEstimated: Bool? = nil,
        tokenplanCostSource: String? = nil,
        latencyMs: Int? = nil,
        success: Bool? = nil,
        errorType: String? = nil,
        errorCode: String? = nil,
        errorMessage: String? = nil,
        recoveryAction: String? = nil,
        recoveryModel: String? = nil
    ) {
        self.runID = runID
        self.provider = provider
        self.model = model
        self.caller = caller
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
        self.totalTokens = totalTokens
        self.costUsd = costUsd
        self.costCny = costCny
        self.costEstimated = costEstimated
        self.costSource = costSource
        self.tokenplanCreditsEstimate = tokenplanCreditsEstimate
        self.tokenplanCostCny = tokenplanCostCny
        self.tokenplanPaygValueCny = tokenplanPaygValueCny
        self.tokenplanCostEstimated = tokenplanCostEstimated
        self.tokenplanCostSource = tokenplanCostSource
        self.latencyMs = latencyMs
        self.success = success
        self.errorType = errorType
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        self.recoveryAction = recoveryAction
        self.recoveryModel = recoveryModel
    }
}

public struct LLMUsageProfile: Codable, Equatable, Sendable {
    public let runID: String?
    public let calls: Int?
    public let promptTokens: Int?
    public let completionTokens: Int?
    public let totalTokens: Int?
    public let costUsd: Double?
    public let costCny: Double?
    public let costEstimated: Bool?
    public let costSources: [String]
    public let tokenplanCreditsEstimate: Double?
    public let tokenplanCostCny: Double?
    public let tokenplanPaygValueCny: Double?
    public let tokenplanCostEstimated: Bool?
    public let tokenplanCostSource: String?
    public let latencyMs: Int?
    public let failedCalls: Int?
    public let models: [String]
    public let providers: [String]
    public let items: [LLMUsageCall]

    private enum CodingKeys: String, CodingKey {
        case calls, models, providers, items
        case runID = "run_id"
        case promptTokens = "prompt_tokens"
        case completionTokens = "completion_tokens"
        case totalTokens = "total_tokens"
        case costUsd = "cost_usd"
        case costCny = "cost_cny"
        case costEstimated = "cost_estimated"
        case costSources = "cost_sources"
        case tokenplanCreditsEstimate = "tokenplan_credits_estimate"
        case tokenplanCostCny = "tokenplan_cost_cny"
        case tokenplanPaygValueCny = "tokenplan_payg_value_cny"
        case tokenplanCostEstimated = "tokenplan_cost_estimated"
        case tokenplanCostSource = "tokenplan_cost_source"
        case latencyMs = "latency_ms"
        case failedCalls = "failed_calls"
    }

    public init(
        runID: String? = nil,
        calls: Int? = nil,
        promptTokens: Int? = nil,
        completionTokens: Int? = nil,
        totalTokens: Int? = nil,
        costUsd: Double? = nil,
        costCny: Double? = nil,
        costEstimated: Bool? = nil,
        costSources: [String] = [],
        tokenplanCreditsEstimate: Double? = nil,
        tokenplanCostCny: Double? = nil,
        tokenplanPaygValueCny: Double? = nil,
        tokenplanCostEstimated: Bool? = nil,
        tokenplanCostSource: String? = nil,
        latencyMs: Int? = nil,
        failedCalls: Int? = nil,
        models: [String] = [],
        providers: [String] = [],
        items: [LLMUsageCall] = []
    ) {
        self.runID = runID
        self.calls = calls
        self.promptTokens = promptTokens
        self.completionTokens = completionTokens
        self.totalTokens = totalTokens
        self.costUsd = costUsd
        self.costCny = costCny
        self.costEstimated = costEstimated
        self.costSources = costSources
        self.tokenplanCreditsEstimate = tokenplanCreditsEstimate
        self.tokenplanCostCny = tokenplanCostCny
        self.tokenplanPaygValueCny = tokenplanPaygValueCny
        self.tokenplanCostEstimated = tokenplanCostEstimated
        self.tokenplanCostSource = tokenplanCostSource
        self.latencyMs = latencyMs
        self.failedCalls = failedCalls
        self.models = models
        self.providers = providers
        self.items = items
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        runID = try? c.decode(String.self, forKey: .runID)
        calls = try? c.decode(Int.self, forKey: .calls)
        promptTokens = try? c.decode(Int.self, forKey: .promptTokens)
        completionTokens = try? c.decode(Int.self, forKey: .completionTokens)
        totalTokens = try? c.decode(Int.self, forKey: .totalTokens)
        costUsd = try? c.decode(Double.self, forKey: .costUsd)
        costCny = try? c.decode(Double.self, forKey: .costCny)
        costEstimated = try? c.decode(Bool.self, forKey: .costEstimated)
        costSources = (try? c.decode([String].self, forKey: .costSources)) ?? []
        tokenplanCreditsEstimate = try? c.decode(Double.self, forKey: .tokenplanCreditsEstimate)
        tokenplanCostCny = try? c.decode(Double.self, forKey: .tokenplanCostCny)
        tokenplanPaygValueCny = try? c.decode(Double.self, forKey: .tokenplanPaygValueCny)
        tokenplanCostEstimated = try? c.decode(Bool.self, forKey: .tokenplanCostEstimated)
        tokenplanCostSource = try? c.decode(String.self, forKey: .tokenplanCostSource)
        latencyMs = try? c.decode(Int.self, forKey: .latencyMs)
        failedCalls = try? c.decode(Int.self, forKey: .failedCalls)
        models = (try? c.decode([String].self, forKey: .models)) ?? []
        providers = (try? c.decode([String].self, forKey: .providers)) ?? []
        items = (try? c.decode([LLMUsageCall].self, forKey: .items)) ?? []
    }
}
