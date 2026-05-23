import Foundation

public struct QuickRecordResult: Decodable, Equatable, Sendable {
    public let type: String
    public let message: String
    public let success: Bool
}

private struct QuickRecordRequest: Encodable {
    let text: String
}

private struct SavedRecordResponse: Decodable {
    let id: Int?
}

private struct DietRecordRequest: Encodable {
    let recordDate: String
    let mealType: String
    let foodItems: String
    let calories: Double?
    let protein: Double?

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case mealType = "meal_type"
        case foodItems = "food_items"
        case calories
        case protein
    }
}

private struct WaterRecordRequest: Encodable {
    let userID: Int
    let recordDate: String
    let amount: Int
    let drinkType: String

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case recordDate = "record_date"
        case amount
        case drinkType = "drink_type"
    }
}

private struct WeightRecordRequest: Encodable {
    let recordDate: String
    let weight: Double
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case weight
        case notes
    }
}

private struct BloodPressureRecordRequest: Encodable {
    let userID: Int
    let recordDate: String
    let systolic: Int
    let diastolic: Int

    enum CodingKeys: String, CodingKey {
        case userID = "user_id"
        case recordDate = "record_date"
        case systolic
        case diastolic
    }
}

private struct SymptomRecordRequest: Encodable {
    let bodyPart: String
    let description: String
    let source: String

    enum CodingKeys: String, CodingKey {
        case bodyPart = "body_part"
        case description
        case source
    }
}

public final class RecordClient: Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func quickRecord(text: String) async throws -> QuickRecordResult {
        try await apiClient.post("quick-record", body: QuickRecordRequest(text: text))
    }

    public func recordDiet(foodItems: String, calories: Double?, protein: Double?) async throws -> QuickRecordResult {
        let _: SavedRecordResponse = try await apiClient.post(
            "diet/records",
            body: DietRecordRequest(
                recordDate: Self.todayString(),
                mealType: Self.currentMealType(),
                foodItems: foodItems,
                calories: calories,
                protein: protein
            )
        )
        return QuickRecordResult(type: "diet", message: "已记录饮食：\(foodItems)", success: true)
    }

    public func recordWater(amountMl: Int) async throws -> QuickRecordResult {
        let _: SavedRecordResponse = try await apiClient.post(
            "water/records",
            body: WaterRecordRequest(
                userID: 0,
                recordDate: Self.todayString(),
                amount: amountMl,
                drinkType: "水"
            )
        )
        return QuickRecordResult(type: "water", message: "已记录饮水 \(amountMl)ml", success: true)
    }

    public func recordWeight(weightKg: Double) async throws -> QuickRecordResult {
        let _: SavedRecordResponse = try await apiClient.post(
            "weight/records",
            body: WeightRecordRequest(
                recordDate: Self.todayString(),
                weight: weightKg,
                notes: "mac_structured_record"
            )
        )
        return QuickRecordResult(type: "weight", message: "已记录体重 \(weightKg)kg", success: true)
    }

    public func recordBloodPressure(systolic: Int, diastolic: Int) async throws -> QuickRecordResult {
        let _: SavedRecordResponse = try await apiClient.post(
            "blood-pressure/records",
            body: BloodPressureRecordRequest(
                userID: 0,
                recordDate: Self.todayString(),
                systolic: systolic,
                diastolic: diastolic
            )
        )
        return QuickRecordResult(type: "bp", message: "已记录血压 \(systolic)/\(diastolic) mmHg", success: true)
    }

    public func recordSymptom(description: String) async throws -> QuickRecordResult {
        let _: SavedRecordResponse = try await apiClient.post(
            "symptoms",
            body: SymptomRecordRequest(
                bodyPart: "other",
                description: description,
                source: "manual"
            )
        )
        return QuickRecordResult(type: "symptom", message: "已记录症状：\(description)", success: true)
    }

    private static func todayString() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private static func currentMealType() -> String {
        let hour = Calendar.current.component(.hour, from: Date())
        switch hour {
        case 5..<10:
            return "breakfast"
        case 10..<14:
            return "lunch"
        case 17..<21:
            return "dinner"
        default:
            return "snack"
        }
    }
}
