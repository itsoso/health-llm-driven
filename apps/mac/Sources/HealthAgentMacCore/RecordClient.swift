import Foundation

public struct BloodPressureSafetyGuidance: Decodable, Equatable, Sendable {
    public let severity: String
    public let title: String
    public let recheckInstruction: String
    public let emergencyInstruction: String
    public let actionPath: String

    enum CodingKeys: String, CodingKey {
        case severity
        case title
        case recheckInstruction = "recheck_instruction"
        case emergencyInstruction = "emergency_instruction"
        case actionPath = "action_path"
    }
}

public struct QuickRecordResult: Decodable, Equatable, Sendable {
    public let type: String
    public let message: String
    public let success: Bool
    public let recordID: Int?
    public let undoPath: String?
    public let category: String?
    public let categoryColor: String?
    public let safetyGuidance: BloodPressureSafetyGuidance?

    enum CodingKeys: String, CodingKey {
        case type
        case message
        case success
        case recordID = "record_id"
        case undoPath = "undo_path"
        case category
        case categoryColor = "category_color"
        case safetyGuidance = "safety_guidance"
    }

    public var displayMessage: String {
        guard let safetyGuidance else { return message }
        return [message, safetyGuidance.recheckInstruction, safetyGuidance.emergencyInstruction]
            .joined(separator: "\n")
    }

    init(
        type: String,
        message: String,
        success: Bool,
        recordID: Int? = nil,
        undoPath: String? = nil,
        category: String? = nil,
        categoryColor: String? = nil,
        safetyGuidance: BloodPressureSafetyGuidance? = nil
    ) {
        self.type = type
        self.message = message
        self.success = success
        self.recordID = recordID
        self.undoPath = undoPath
        self.category = category
        self.categoryColor = categoryColor
        self.safetyGuidance = safetyGuidance
    }
}

public struct VoiceFoodDraftItem: Decodable, Equatable, Sendable {
    public let name: String
    public let quantity: Double?
    public let unit: String?
    public let calories: Double?
    public let protein: Double?
    public let carbs: Double?
    public let fat: Double?
}

public struct VoiceFoodParseResponse: Decodable, Equatable, Sendable {
    public let rawText: String
    public let mealType: String
    public let mealTypeLabel: String
    public let foods: [VoiceFoodDraftItem]
    public let riskTags: [String]
    public let confidence: Double
    public let needsConfirmation: Bool
    public let clarifyingQuestion: String?
    public let parserVersion: String

    enum CodingKeys: String, CodingKey {
        case rawText = "raw_text"
        case mealType = "meal_type"
        case mealTypeLabel = "meal_type_label"
        case foods
        case riskTags = "risk_tags"
        case confidence
        case needsConfirmation = "needs_confirmation"
        case clarifyingQuestion = "clarifying_question"
        case parserVersion = "parser_version"
    }
}

/// Receipt returned only after the owner-scoped diet draft has been committed.
/// The client submits the opaque server-bound draft token, never the image bytes
/// or a user-editable reconstruction of the record.
public struct DietDraftConfirmationReceipt: Decodable, Equatable, Sendable {
    public let id: Int
    public let displayMessage: String?

    enum CodingKeys: String, CodingKey {
        case id
        case displayMessage = "display_message"
    }

    public init(id: Int, displayMessage: String? = nil) {
        self.id = id
        self.displayMessage = displayMessage
    }
}

public protocol DietDraftConfirming: Sendable {
    func confirmDietDraft(action: AgentDynamicCardActionDescriptor) async throws -> DietDraftConfirmationReceipt
}

private struct QuickRecordRequest: Encodable {
    let text: String
}

private struct VoiceFoodParseRequest: Encodable {
    let rawText: String
    let mealType: String?

    enum CodingKeys: String, CodingKey {
        case rawText = "raw_text"
        case mealType = "meal_type"
    }
}

private struct SavedRecordResponse: Decodable {
    let id: Int?
    let category: String?
    let categoryColor: String?
    let safetyGuidance: BloodPressureSafetyGuidance?

    enum CodingKeys: String, CodingKey {
        case id
        case category
        case categoryColor = "category_color"
        case safetyGuidance = "safety_guidance"
    }
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

private struct DietDraftConfirmationRequest: Encodable {
    let recordDate: String
    let mealType: String
    let foodItems: String
    let calories: Double?
    let protein: Double?
    let carbs: Double?
    let fat: Double?
    let fiber: Double?
    let source: String?
    let aiRecognized: Int?
    let aiConfidence: Double?
    let aiRawResult: AgentDynamicCardValue?
    let healthTips: String?
    let photoDraftToken: String

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case mealType = "meal_type"
        case foodItems = "food_items"
        case calories, protein, carbs, fat, fiber, source
        case aiRecognized = "ai_recognized"
        case aiConfidence = "ai_confidence"
        case aiRawResult = "ai_raw_result"
        case healthTips = "health_tips"
        case photoDraftToken = "photo_draft_token"
    }

    init?(action: AgentDynamicCardActionDescriptor) {
        guard action.action == "diet_record.create",
              action.requiresManualConfirm == true,
              action.requiredReceipt == true,
              action.capabilityID == "diet_draft.v1",
              let record = action.payload?["record"],
              let recordDate = Self.requiredText(record["record_date"]),
              let mealType = Self.requiredText(record["meal_type"]),
              let foodItems = Self.requiredText(record["food_items"]),
              let photoDraftToken = Self.requiredText(record["photo_draft_token"]) else {
            return nil
        }
        self.recordDate = recordDate
        self.mealType = mealType
        self.foodItems = foodItems
        self.calories = Self.number(record["calories"])
        self.protein = Self.number(record["protein"])
        self.carbs = Self.number(record["carbs"])
        self.fat = Self.number(record["fat"])
        self.fiber = Self.number(record["fiber"])
        self.source = Self.text(record["source"])
        self.aiRecognized = record["ai_recognized"]?.boolValue.map { $0 ? 1 : 0 }
            ?? record["ai_recognized"]?.intValue.map { $0 == 0 ? 0 : 1 }
        self.aiConfidence = Self.number(record["ai_confidence"])
        self.aiRawResult = record["ai_raw_result"]
        self.healthTips = Self.text(record["health_tips"])
        self.photoDraftToken = photoDraftToken
    }

    private static func requiredText(_ value: AgentDynamicCardValue?) -> String? {
        let text = value?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return text.isEmpty ? nil : text
    }

    private static func text(_ value: AgentDynamicCardValue?) -> String? {
        requiredText(value)
    }

    private static func number(_ value: AgentDynamicCardValue?) -> Double? {
        switch value {
        case .int(let number): return Double(number)
        case .double(let number): return number
        case .string(let number): return Double(number)
        default: return nil
        }
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

private struct SneezeCheckinRequest: Encodable {
    let checkinDate: String
    let sneezeCount: Int

    enum CodingKeys: String, CodingKey {
        case checkinDate = "checkin_date"
        case sneezeCount = "sneeze_count"
    }
}

private struct NasalWashCheckinRequest: Encodable {
    let checkinDate: String
    let nasalWashCount: Int

    enum CodingKeys: String, CodingKey {
        case checkinDate = "checkin_date"
        case nasalWashCount = "nasal_wash_count"
    }
}

private struct ExerciseRecordRequest: Encodable {
    let recordDate: String
    let exerciseType: String
    let reps: Int?
    let sets: Int?
    let duration: Int?
    let intensity: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case exerciseType = "exercise_type"
        case reps
        case sets
        case duration
        case intensity
        case notes
    }
}

private struct MedicationLogRequest: Encodable {
    let medicationID: Int
    let takenTime: String
    let status: String
    let actualDosage: String?

    enum CodingKeys: String, CodingKey {
        case medicationID = "medication_id"
        case takenTime = "taken_time"
        case status
        case actualDosage = "actual_dosage"
    }
}

private struct MoodRecordRequest: Encodable {
    let recordDate: String
    let moodScore: Int
    let journal: String?

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case moodScore = "mood_score"
        case journal
    }
}

private struct GlucoseReadingRequest: Encodable {
    let measuredAt: String
    let glucoseMgDl: Double
    let source: String

    enum CodingKeys: String, CodingKey {
        case measuredAt = "measured_at"
        case glucoseMgDl = "glucose_mg_dl"
        case source
    }
}

private struct ExcretionRecordRequest: Encodable {
    let recordDate: String
    let type: String
    let stoolType: Int?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case type
        case stoolType = "stool_type"
        case notes
    }
}

/// 用户的一种在用药物 (GET /medication/medications/me)，用于一键打卡 chip。
public struct MedicationOption: Decodable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let name: String
    public let dosage: String?
    public let frequency: String?
    public let safetyAlerts: [MedicationSafetyAlert]

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case dosage
        case frequency
        case safetyAlerts = "safety_alerts"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(Int.self, forKey: .id)
        name = try container.decode(String.self, forKey: .name)
        dosage = try container.decodeIfPresent(String.self, forKey: .dosage)
        frequency = try container.decodeIfPresent(String.self, forKey: .frequency)
        safetyAlerts = try container.decodeIfPresent([MedicationSafetyAlert].self, forKey: .safetyAlerts) ?? []
    }

    public var safetyAlertSummary: String? {
        guard let alert = safetyAlerts.sorted(by: { $0.severity.value > $1.severity.value }).first else {
            return nil
        }
        return "\(alert.severity.labelZH) · \(alert.title)"
    }
}

public struct MedicationSafetyAlert: Decodable, Equatable, Sendable, Identifiable {
    public let ruleID: String
    public let category: String
    public let severity: MedicationSafetyAlertSeverity
    public let title: String
    public let message: String
    public let action: String?
    public let requiresMedicalAttention: Bool?

    public var id: String { ruleID }

    enum CodingKeys: String, CodingKey {
        case ruleID = "rule_id"
        case category
        case severity
        case title
        case message
        case action
        case requiresMedicalAttention = "requires_medical_attention"
    }
}

public struct MedicationSafetyAlertSeverity: Decodable, Equatable, Sendable {
    public let value: Int
    public let label: String
    public let labelZH: String

    enum CodingKeys: String, CodingKey {
        case value
        case label
        case labelZH = "label_zh"
    }
}

private struct SupplementCheckinRequest: Encodable {
    let recordDate: String
    let checkins: [Checkin]

    struct Checkin: Encodable {
        let supplementID: Int
        let taken: Bool

        enum CodingKeys: String, CodingKey {
            case supplementID = "supplement_id"
            case taken
        }
    }

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case checkins
    }
}

private struct BatchCheckinResponse: Decodable {
    let message: String?
}

/// 最近最常打卡的补剂 (后端 GET /supplements/me/frequent, System A 定义+打卡).
public struct FrequentSupplement: Decodable, Equatable, Sendable, Identifiable {
    public let supplementID: Int
    public let name: String
    public let dosage: String?
    public let timing: String?
    public let count: Int

    public var id: Int { supplementID }

    enum CodingKeys: String, CodingKey {
        case supplementID = "supplement_id"
        case name
        case dosage
        case timing
        case count
    }
}

/// 最常用的「饮水量 + 饮品类型」组合 (后端 GET /water/records/me/frequent).
public struct FrequentWater: Decodable, Equatable, Sendable, Identifiable {
    public let amountMl: Int
    public let drinkType: String?
    public let count: Int

    public var id: String { "\(amountMl)-\(drinkType ?? "")" }

    enum CodingKeys: String, CodingKey {
        case amountMl = "amount_ml"
        case drinkType = "drink_type"
        case count
    }
}

public final class RecordClient: DietDraftConfirming, Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func quickRecord(text: String) async throws -> QuickRecordResult {
        try await apiClient.post("quick-record", body: QuickRecordRequest(text: text))
    }

    public func parseVoiceDietDraft(rawText: String, mealType: String? = nil) async throws -> VoiceFoodParseResponse {
        try await apiClient.post(
            "diet/voice/parse",
            body: VoiceFoodParseRequest(rawText: rawText, mealType: mealType)
        )
    }

    public func recordDiet(foodItems: String, calories: Double?, protein: Double?) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "diet/records",
            body: DietRecordRequest(
                recordDate: Self.todayString(),
                mealType: Self.currentMealType(),
                foodItems: foodItems,
                calories: calories,
                protein: protein
            )
        )
        return QuickRecordResult(
            type: "diet",
            message: "已记录饮食：\(foodItems)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "diet/records", recordID: saved.id)
        )
    }

    public func confirmDietDraft(action: AgentDynamicCardActionDescriptor) async throws -> DietDraftConfirmationReceipt {
        guard let request = DietDraftConfirmationRequest(action: action) else {
            throw APIError.emptyResponse
        }
        return try await apiClient.post("diet/records", body: request)
    }

    public func recordWater(amountMl: Int, drinkType: String = "水") async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "water/records",
            body: WaterRecordRequest(
                userID: 0,
                recordDate: Self.todayString(),
                amount: amountMl,
                drinkType: drinkType
            )
        )
        let suffix = (drinkType.isEmpty || drinkType == "水") ? "" : " \(drinkType)"
        return QuickRecordResult(
            type: "water",
            message: "已记录饮水 \(amountMl)ml\(suffix)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "water/records", recordID: saved.id)
        )
    }

    /// 最近最常打卡的补剂，用于「常吃补剂」一键打卡建议。
    public func fetchFrequentSupplements(limit: Int = 8, days: Int = 30) async throws -> [FrequentSupplement] {
        try await apiClient.get("supplements/me/frequent?limit=\(limit)&days=\(days)")
    }

    /// 最常用的饮水量 + 饮品类型组合，用于「常喝」一键记录建议。
    public func fetchFrequentWater(limit: Int = 6, days: Int = 30) async throws -> [FrequentWater] {
        try await apiClient.get("water/records/me/frequent?limit=\(limit)&days=\(days)")
    }

    /// 给今天的某个补剂打卡 (System A 定义+打卡)。taken=false 即取消打卡。
    public func checkinSupplement(supplementID: Int, name: String, taken: Bool = true) async throws -> QuickRecordResult {
        let _: BatchCheckinResponse = try await apiClient.post(
            "supplements/records/batch",
            body: SupplementCheckinRequest(
                recordDate: Self.todayString(),
                checkins: [.init(supplementID: supplementID, taken: taken)]
            )
        )
        return QuickRecordResult(
            type: "supplement",
            message: taken ? "已为今天补剂打卡：\(name)" : "已取消今天补剂打卡：\(name)",
            success: true
        )
    }

    public func recordWeight(weightKg: Double) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "weight/records",
            body: WeightRecordRequest(
                recordDate: Self.todayString(),
                weight: weightKg,
                notes: "mac_structured_record"
            )
        )
        return QuickRecordResult(
            type: "weight",
            message: "已记录体重 \(weightKg)kg",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "weight/records", recordID: saved.id)
        )
    }

    public func recordBloodPressure(systolic: Int, diastolic: Int) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "blood-pressure/records",
            body: BloodPressureRecordRequest(
                userID: 0,
                recordDate: Self.todayString(),
                systolic: systolic,
                diastolic: diastolic
            )
        )
        return QuickRecordResult(
            type: "bp",
            message: "已记录血压 \(systolic)/\(diastolic) mmHg",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "blood-pressure/records", recordID: saved.id),
            category: saved.category,
            categoryColor: saved.categoryColor,
            safetyGuidance: saved.safetyGuidance
        )
    }

    /// 记录今天的打喷嚏次数 (鼻炎症状)。走 POST /checkin/，按日期 upsert，
    /// 后端把 sneeze_count 并入当天打卡，供鼻炎趋势聚合。次数为当日累计值。
    public func recordSneeze(count: Int) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "checkin/",
            body: SneezeCheckinRequest(checkinDate: Self.todayString(), sneezeCount: count)
        )
        return QuickRecordResult(
            type: "sneeze",
            message: "已记录今天打喷嚏 \(count) 次",
            success: true,
            recordID: saved.id
        )
    }

    /// 记录今天的洗鼻次数 (鼻炎护理)。走 POST /checkin/ (nasal_wash_count)，
    /// 与打喷嚏同一套，按日期 upsert。次数为当日累计值。
    public func recordNasalWash(count: Int) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "checkin/",
            body: NasalWashCheckinRequest(checkinDate: Self.todayString(), nasalWashCount: count)
        )
        return QuickRecordResult(
            type: "nasal_wash",
            message: "已记录今天洗鼻 \(count) 次",
            success: true,
            recordID: saved.id
        )
    }

    /// 用户在用药物列表 (供一键打卡 chip)。best-effort：失败返回空。
    public func fetchMyMedications() async -> [MedicationOption] {
        let meds: [MedicationOption]? = try? await apiClient.get("medication/medications/me?active_only=true")
        return meds ?? []
    }

    /// 给某个药物打一次「已服用」(POST /medication/logs)。剂量缺省用药物定义的剂量。
    public func logMedication(medicationID: Int, name: String, dosage: String?) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "medication/logs",
            body: MedicationLogRequest(
                medicationID: medicationID,
                takenTime: Self.nowHHmm(),
                status: "taken",
                actualDosage: dosage
            )
        )
        let suffix = (dosage?.isEmpty == false) ? " \(dosage!)" : ""
        return QuickRecordResult(
            type: "medication",
            message: "已记录服药：\(name)\(suffix)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "medication/logs", recordID: saved.id)
        )
    }

    /// 记录一次心情打分 (1–10) + 可选随记。走 POST /mood/records。
    public func recordMood(score: Int, note: String?) async throws -> QuickRecordResult {
        let journal = (note?.isEmpty == false) ? note : nil
        let saved: SavedRecordResponse = try await apiClient.post(
            "mood/records",
            body: MoodRecordRequest(recordDate: Self.todayString(), moodScore: score, journal: journal)
        )
        return QuickRecordResult(
            type: "mood",
            message: "已记录心情 \(score)/10",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "mood/records", recordID: saved.id)
        )
    }

    /// 记录一次血糖 (手动)。走 POST /cgm/readings；调用方负责换算成 mg/dL。
    public func recordBloodGlucose(mgDl: Double, displayText: String) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "cgm/readings",
            body: GlucoseReadingRequest(measuredAt: Self.nowISO8601(), glucoseMgDl: mgDl, source: "manual")
        )
        return QuickRecordResult(
            type: "blood_glucose",
            message: "已记录血糖 \(displayText)",
            success: true,
            recordID: saved.id
        )
    }

    /// 记录一次排泄 (大便/小便)。走 POST /excretion/records。
    public func recordExcretion(type: String, stoolType: Int?, notes: String?) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "excretion/records",
            body: ExcretionRecordRequest(
                recordDate: Self.todayString(),
                type: type,
                stoolType: type == "bowel" ? stoolType : nil,
                notes: (notes?.isEmpty == false) ? notes : nil
            )
        )
        let label = type == "urine" ? "小便" : "大便"
        return QuickRecordResult(
            type: "excretion",
            message: "已记录排泄：\(label)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "excretion/records", recordID: saved.id)
        )
    }

    /// 记录一次运动 (俯卧撑/跑步等)。走 POST /daily-health/exercise，
    /// 强度按次数自动判定 (≥30 high / ≥15 medium / else low)，与 Web PushupCard 一致。
    public func recordExercise(
        exerciseType: String,
        reps: Int?,
        sets: Int?,
        durationMinutes: Int?,
        notes: String? = nil
    ) async throws -> QuickRecordResult {
        let intensity: String?
        if let reps {
            intensity = reps >= 30 ? "high" : (reps >= 15 ? "medium" : "low")
        } else {
            intensity = nil
        }
        let saved: SavedRecordResponse = try await apiClient.post(
            "daily-health/exercise",
            body: ExerciseRecordRequest(
                recordDate: Self.todayString(),
                exerciseType: exerciseType,
                reps: reps,
                sets: sets,
                duration: durationMinutes,
                intensity: intensity,
                notes: notes
            )
        )
        var detail: [String] = []
        if let reps {
            let s = sets ?? 1
            detail.append(s > 1 ? "\(reps)个×\(s)组" : "\(reps)个")
        }
        if let durationMinutes { detail.append("\(durationMinutes)分钟") }
        let suffix = detail.isEmpty ? "" : " " + detail.joined(separator: "，")
        return QuickRecordResult(
            type: "exercise",
            message: "已记录运动：\(exerciseType)\(suffix)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "daily-health/exercise", recordID: saved.id)
        )
    }

    public func recordSymptom(description: String) async throws -> QuickRecordResult {
        let saved: SavedRecordResponse = try await apiClient.post(
            "symptoms",
            body: SymptomRecordRequest(
                bodyPart: "other",
                description: description,
                source: "manual"
            )
        )
        return QuickRecordResult(
            type: "symptom",
            message: "已记录症状：\(description)",
            success: true,
            recordID: saved.id,
            undoPath: undoPath(prefix: "symptoms", recordID: saved.id)
        )
    }

    public func undoSavedRecord(path: String) async throws {
        try await apiClient.delete(path)
    }

    private func undoPath(prefix: String, recordID: Int?) -> String? {
        guard let recordID else {
            return nil
        }
        return "\(prefix)/\(recordID)"
    }

    private static func todayString() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: Date())
    }

    private static func nowHHmm() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: Date())
    }

    private static func nowISO8601() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
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
