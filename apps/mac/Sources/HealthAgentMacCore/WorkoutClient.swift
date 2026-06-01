import Foundation

/// Mirrors backend `WorkoutSummary` (GET /workout/me). Durations are in seconds
/// and distances in meters on the wire; the UI converts for display.
public struct WorkoutSummary: Codable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let workoutDate: String
    public let workoutType: String
    public let workoutName: String?
    public let durationSeconds: Int?
    public let distanceMeters: Double?
    public let avgHeartRate: Int?
    public let calories: Int?
    public let feeling: String?
    public let hasAIAnalysis: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case workoutDate = "workout_date"
        case workoutType = "workout_type"
        case workoutName = "workout_name"
        case durationSeconds = "duration_seconds"
        case distanceMeters = "distance_meters"
        case avgHeartRate = "avg_heart_rate"
        case calories
        case feeling
        case hasAIAnalysis = "has_ai_analysis"
    }
}

/// Mirrors backend `WorkoutStats` (GET /workout/me/stats).
///
/// Note: backend `workouts_by_type` is a free-form dict whose shape has changed
/// over time (`{type: count}` historically, now `{type: {count, duration_minutes}}`).
/// The desktop UI doesn't render it, so it is decoded leniently (any JSON / nil)
/// — a server-side shape change must never break the whole stats card again.
public struct WorkoutStats: Codable, Equatable, Sendable {
    public let totalWorkouts: Int
    public let totalDurationMinutes: Int
    public let totalDistanceKm: Double
    public let totalCalories: Int
    public let avgDurationMinutes: Double
    public let avgDistanceKm: Double
    public let recentTrend: String

    enum CodingKeys: String, CodingKey {
        case totalWorkouts = "total_workouts"
        case totalDurationMinutes = "total_duration_minutes"
        case totalDistanceKm = "total_distance_km"
        case totalCalories = "total_calories"
        case avgDurationMinutes = "avg_duration_minutes"
        case avgDistanceKm = "avg_distance_km"
        case recentTrend = "recent_trend"
    }

    public init(
        totalWorkouts: Int,
        totalDurationMinutes: Int,
        totalDistanceKm: Double,
        totalCalories: Int,
        avgDurationMinutes: Double,
        avgDistanceKm: Double,
        recentTrend: String
    ) {
        self.totalWorkouts = totalWorkouts
        self.totalDurationMinutes = totalDurationMinutes
        self.totalDistanceKm = totalDistanceKm
        self.totalCalories = totalCalories
        self.avgDurationMinutes = avgDurationMinutes
        self.avgDistanceKm = avgDistanceKm
        self.recentTrend = recentTrend
    }
}

public final class WorkoutClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchWorkouts(limit: Int = 50) async throws -> [WorkoutSummary] {
        try await apiClient.get("workout/me?limit=\(limit)")
    }

    public func fetchStats(days: Int = 30) async throws -> WorkoutStats {
        try await apiClient.get("workout/me/stats?days=\(days)")
    }
}
