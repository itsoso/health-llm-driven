import Foundation

public struct Workout: Codable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let workoutType: String
    public let name: String?
    public let startTime: String
    public let endTime: String?
    public let durationMin: Double?
    public let distanceKm: Double?
    public let calories: Int?
    public let avgHeartRate: Int?
    public let maxHeartRate: Int?
    public let elevationGainM: Double?
    public let avgPace: String?
    public let perceivedExertion: Int?
    public let notes: String?
    public let source: String

    enum CodingKeys: String, CodingKey {
        case id
        case workoutType = "workout_type"
        case name
        case startTime = "start_time"
        case endTime = "end_time"
        case durationMin = "duration_min"
        case distanceKm = "distance_km"
        case calories
        case avgHeartRate = "avg_heart_rate"
        case maxHeartRate = "max_heart_rate"
        case elevationGainM = "elevation_gain_m"
        case avgPace = "avg_pace"
        case perceivedExertion = "perceived_exertion"
        case notes
        case source
    }
}

public struct WorkoutStats: Codable, Equatable, Sendable {
    public let totalWorkouts: Int
    public let totalDurationMin: Double
    public let totalCalories: Int
    public let totalDistanceKm: Double
    public let byType: [String: Int]
    public let avgDurationMin: Double
    public let weeklyFrequency: Double
    public let periodDays: Int

    enum CodingKeys: String, CodingKey {
        case totalWorkouts = "total_workouts"
        case totalDurationMin = "total_duration_min"
        case totalCalories = "total_calories"
        case totalDistanceKm = "total_distance_km"
        case byType = "by_type"
        case avgDurationMin = "avg_duration_min"
        case weeklyFrequency = "weekly_frequency"
        case periodDays = "period_days"
    }
}

public final class WorkoutClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchWorkouts(limit: Int = 50) async throws -> [Workout] {
        try await apiClient.get("workouts/?limit=\(limit)")
    }

    public func fetchStats(days: Int = 30) async throws -> WorkoutStats {
        try await apiClient.get("workouts/stats/summary?days=\(days)")
    }
}
