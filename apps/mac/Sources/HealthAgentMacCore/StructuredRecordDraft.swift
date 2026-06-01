import Foundation

public enum StructuredRecordDraftType: String, CaseIterable, Identifiable, Sendable {
    case diet
    case water
    case supplement
    case weight
    case bloodPressure
    case symptom
    case sneeze

    public var id: String { rawValue }
}

public struct StructuredRecordDraft: Equatable, Sendable {
    public let type: StructuredRecordDraftType
    public let foodName: String
    public let calories: String
    public let protein: String
    public let waterMl: String
    public let supplementName: String
    public let supplementDose: String
    public let weightKg: String
    public let systolic: String
    public let diastolic: String
    public let symptom: String
    public let sneezeCount: String

    public init(
        type: StructuredRecordDraftType,
        foodName: String = "",
        calories: String = "",
        protein: String = "",
        waterMl: String = "",
        supplementName: String = "",
        supplementDose: String = "",
        weightKg: String = "",
        systolic: String = "",
        diastolic: String = "",
        symptom: String = "",
        sneezeCount: String = ""
    ) {
        self.type = type
        self.foodName = foodName
        self.calories = calories
        self.protein = protein
        self.waterMl = waterMl
        self.supplementName = supplementName
        self.supplementDose = supplementDose
        self.weightKg = weightKg
        self.systolic = systolic
        self.diastolic = diastolic
        self.symptom = symptom
        self.sneezeCount = sneezeCount
    }

    public var canSubmit: Bool {
        switch type {
        case .diet:
            !trim(foodName).isEmpty
        case .water:
            positiveInt(waterMl) != nil
        case .supplement:
            !trim(supplementName).isEmpty
        case .weight:
            positiveDouble(weightKg) != nil
        case .bloodPressure:
            positiveInt(systolic) != nil && positiveInt(diastolic) != nil
        case .symptom:
            !trim(symptom).isEmpty
        case .sneeze:
            positiveInt(sneezeCount) != nil
        }
    }

    public var previewText: String {
        switch type {
        case .diet:
            let parts = [
                trim(foodName),
                trim(calories).isEmpty ? "" : "\(trim(calories))kcal",
                trim(protein).isEmpty ? "" : "蛋白质\(trim(protein))g"
            ].filter { !$0.isEmpty }
            return parts.isEmpty ? "" : "记录饮食：" + parts.joined(separator: "，")
        case .water:
            return trim(waterMl).isEmpty ? "" : "喝水 \(trim(waterMl))ml"
        case .supplement:
            let text = [trim(supplementName), trim(supplementDose)].filter { !$0.isEmpty }.joined(separator: " ")
            return text.isEmpty ? "" : "记录补剂：\(text)"
        case .weight:
            return trim(weightKg).isEmpty ? "" : "记录体重 \(trim(weightKg))kg"
        case .bloodPressure:
            return trim(systolic).isEmpty || trim(diastolic).isEmpty ? "" : "记录血压 \(trim(systolic))/\(trim(diastolic)) mmHg"
        case .symptom:
            return trim(symptom).isEmpty ? "" : "记录症状：\(trim(symptom))"
        case .sneeze:
            return trim(sneezeCount).isEmpty ? "" : "记录打喷嚏 \(trim(sneezeCount)) 次"
        }
    }

    public func positiveDouble(_ value: String) -> Double? {
        let normalized = trim(value).replacingOccurrences(of: ",", with: ".")
        guard let number = Double(normalized), number > 0 else {
            return nil
        }
        return number
    }

    public func positiveInt(_ value: String) -> Int? {
        guard let number = Int(trim(value)), number > 0 else {
            return nil
        }
        return number
    }

    private func trim(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
