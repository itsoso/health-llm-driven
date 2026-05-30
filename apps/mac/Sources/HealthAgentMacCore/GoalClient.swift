import Foundation

/// Mirrors backend `GoalResponse` (GET /goals/me). There is no server-side
/// progress percentage or stats endpoint, so progress is derived from
/// current_value / target_value and the overview is computed client-side.
public struct Goal: Codable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let goalType: String
    public let goalPeriod: String
    public let title: String?
    public let description: String?
    public let targetValue: Double?
    public let targetUnit: String?
    public let currentValue: Double?
    public let startDate: String
    public let endDate: String?
    public let implementationSteps: String?
    public let status: String
    public let priority: Int?
    public let notes: String?

    enum CodingKeys: String, CodingKey {
        case id
        case goalType = "goal_type"
        case goalPeriod = "goal_period"
        case title
        case description
        case targetValue = "target_value"
        case targetUnit = "target_unit"
        case currentValue = "current_value"
        case startDate = "start_date"
        case endDate = "end_date"
        case implementationSteps = "implementation_steps"
        case status
        case priority
        case notes
    }

    /// 0...1 progress derived from current/target. nil when the goal has no
    /// numeric target (e.g. a habit goal) so the UI can hide the bar.
    public var progressFraction: Double? {
        guard let target = targetValue, target > 0, let current = currentValue else { return nil }
        return min(max(current / target, 0), 1)
    }
}

/// Client-side rollup over the goal list (no backend stats endpoint exists).
public struct GoalOverview: Equatable, Sendable {
    public let total: Int
    public let active: Int
    public let completed: Int

    public init(goals: [Goal]) {
        total = goals.count
        active = goals.filter { $0.status.lowercased() == "active" }.count
        completed = goals.filter { $0.status.lowercased() == "completed" }.count
    }

    public var completionRate: Double {
        total > 0 ? Double(completed) / Double(total) : 0
    }
}

public final class GoalClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchGoals(status: String? = nil) async throws -> [Goal] {
        var path = "goals/me"
        if let status, !status.isEmpty {
            path += "?status=\(status)"
        }
        return try await apiClient.get(path)
    }
}
