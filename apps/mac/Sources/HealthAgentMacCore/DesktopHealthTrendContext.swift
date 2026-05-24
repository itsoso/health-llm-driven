import Foundation

public enum DesktopHealthTrendKind: String, CaseIterable, Identifiable, Sendable {
    case diet
    case water
    case supplements
    case weight
    case bloodPressure
    case steps

    public var id: String { rawValue }

    public var title: String {
        switch self {
        case .diet: "饮食趋势"
        case .water: "饮水趋势"
        case .supplements: "补剂趋势"
        case .weight: "体重记录"
        case .bloodPressure: "血压记录"
        case .steps: "步数趋势"
        }
    }
}

public struct DesktopHealthTrendPoint: Equatable, Identifiable, Sendable {
    public let date: String
    public let value: Double
    public let count: Int?

    public var id: String { date }

    public init(date: String, value: Double, count: Int? = nil) {
        self.date = date
        self.value = value
        self.count = count
    }
}

public struct DesktopHealthTrendContext: Equatable, Identifiable, Sendable {
    public let kind: DesktopHealthTrendKind
    public let rangeDays: Int
    public let unit: String
    public let total: Double?
    public let average: Double?
    public let recordCount: Int?
    public let points: [DesktopHealthTrendPoint]
    public let latestRecord: DesktopRecordMetric?

    public var id: String { "\(kind.rawValue)-\(rangeDays)d" }
    public var title: String { kind.title }

    public init(
        kind: DesktopHealthTrendKind,
        rangeDays: Int,
        unit: String,
        total: Double? = nil,
        average: Double? = nil,
        recordCount: Int? = nil,
        points: [DesktopHealthTrendPoint],
        latestRecord: DesktopRecordMetric? = nil
    ) {
        self.kind = kind
        self.rangeDays = rangeDays
        self.unit = unit
        self.total = total
        self.average = average
        self.recordCount = recordCount
        self.points = points
        self.latestRecord = latestRecord
    }

    public var pointSeriesText: String {
        points.map { point in
            let countSuffix = point.count.map { "(count \($0))" }
            return [
                "\(point.date)=\(Self.format(point.value)) \(unit)",
                countSuffix
            ].compactMap { $0 }.joined()
        }
        .joined(separator: "; ")
    }

    public var latestRecordText: String? {
        guard let latestRecord else { return nil }
        return [
            latestRecord.title,
            latestRecord.displayValue,
            latestRecord.recordDate
        ].compactMap { $0 }.joined(separator: " · ")
    }

    public static func format(_ value: Double) -> String {
        if value.rounded() == value {
            return String(Int(value))
        }
        return String(format: "%.1f", value)
    }
}
