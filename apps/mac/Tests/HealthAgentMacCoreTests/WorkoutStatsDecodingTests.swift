import Foundation
import XCTest
@testable import HealthAgentMacCore

/// Regression: backend `workouts_by_type` is a nested dict
/// (`{type: {count, duration_minutes}}`), but the model previously declared
/// `[String: Int]`, so the whole stats payload failed to decode and the UI
/// showed a raw "data couldn't be read" system error. The field is now ignored.
final class WorkoutStatsDecodingTests: XCTestCase {
    private func decode(_ json: String) throws -> WorkoutStats {
        try JSONDecoder().decode(WorkoutStats.self, from: Data(json.utf8))
    }

    func testDecodesRealBackendPayloadWithNestedWorkoutsByType() throws {
        let json = """
        {
          "total_workouts": 7,
          "total_duration_minutes": 148,
          "total_distance_km": 18.9,
          "total_calories": 1503,
          "avg_duration_minutes": 21.1,
          "avg_distance_km": 2.7,
          "workouts_by_type": {
            "running": {"count": 5, "duration_minutes": 96},
            "treadmill": {"count": 2, "duration_minutes": 52}
          },
          "recent_trend": "stable"
        }
        """
        let stats = try decode(json)
        XCTAssertEqual(stats.totalWorkouts, 7)
        XCTAssertEqual(stats.totalCalories, 1503)
        XCTAssertEqual(stats.recentTrend, "stable")
    }

    func testDecodesEmptyStats() throws {
        let json = """
        {
          "total_workouts": 0,
          "total_duration_minutes": 0,
          "total_distance_km": 0,
          "total_calories": 0,
          "avg_duration_minutes": 0,
          "avg_distance_km": 0,
          "workouts_by_type": {},
          "recent_trend": "stable"
        }
        """
        let stats = try decode(json)
        XCTAssertEqual(stats.totalWorkouts, 0)
    }

    func testDecodesEvenIfWorkoutsByTypeKeyAbsent() throws {
        // 字段被忽略, 缺失也不该影响解码.
        let json = """
        {
          "total_workouts": 3,
          "total_duration_minutes": 60,
          "total_distance_km": 5,
          "total_calories": 300,
          "avg_duration_minutes": 20,
          "avg_distance_km": 1.7,
          "recent_trend": "improving"
        }
        """
        let stats = try decode(json)
        XCTAssertEqual(stats.totalWorkouts, 3)
        XCTAssertEqual(stats.recentTrend, "improving")
    }
}
