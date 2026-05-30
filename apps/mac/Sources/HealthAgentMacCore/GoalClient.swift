import Foundation

public struct Goal: Codable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let title: String
    public let description: String?
    public let category: String
    public let status: String
    public let targetValue: Double?
    public let currentValue: Double?
    public let unit: String?
    public let targetDate: String?
    public let startDate: String
    public let progressPercent: Double

    enum CodingKeys: String, CodingKey {
        case id, title, description, category, status, unit
        case targetValue = "target_value"
        case currentValue = "current_value"
        case targetDate = "target_date"
        case startDate = "start_date"
        case progressPercent = "progress_percent"
    }
}

public struct GoalStats: Codable, Equatable, Sendable {
    public let total: Int
    public let active: Int
    public let completed: Int
    public let abandoned: Int
    public let completionRate: Double
    public let byCategory: [String: Int]

    enum CodingKeys: String, CodingKey {
        case total, active, completed, abandoned
        case completionRate = "completion_rate"
        case byCategory = "by_category"
    }
}

public final class GoalClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchGoals(status: String? = nil, limit: Int = 50) async throws -> [Goal] {
        var path = "goals/?limit=\(limit)"
        if let status, !status.isEmpty {
            path += "&status=\(status)"
        }
        return try await apiClient.get(path)
    }

    public func fetchStats() async throws -> GoalStats {
        try await apiClient.get("goals/stats/summary")
    }
}
