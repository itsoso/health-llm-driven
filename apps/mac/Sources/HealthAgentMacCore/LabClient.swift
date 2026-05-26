import Foundation

public struct LabIndicatorPoint: Decodable, Sendable, Equatable, Identifiable {
    public let date: String
    public let value: Double?
    public let isAbnormal: Bool?

    public var id: String { date }

    enum CodingKeys: String, CodingKey {
        case date
        case value
        case isAbnormal = "is_abnormal"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.date = try container.decode(String.self, forKey: .date)
        self.value = try container.decodeIfPresent(Double.self, forKey: .value)
        if let bool = try? container.decodeIfPresent(Bool.self, forKey: .isAbnormal) {
            self.isAbnormal = bool
        } else if let str = try? container.decodeIfPresent(String.self, forKey: .isAbnormal) {
            let normalized = str.lowercased()
            if normalized == "true" || normalized == "high" || normalized == "low" || normalized == "abnormal" {
                self.isAbnormal = true
            } else if normalized == "false" || normalized == "normal" {
                self.isAbnormal = false
            } else {
                self.isAbnormal = nil
            }
        } else {
            self.isAbnormal = nil
        }
    }
}

public struct LabIndicatorSeries: Decodable, Sendable, Equatable, Identifiable {
    public let code: String
    public let name: String?
    public let unit: String?
    public let referenceLow: Double?
    public let referenceHigh: Double?
    public let data: [LabIndicatorPoint]

    public var id: String { code }

    enum CodingKeys: String, CodingKey {
        case name
        case unit
        case referenceLow = "reference_low"
        case referenceHigh = "reference_high"
        case data
    }

    public init(
        code: String,
        name: String?,
        unit: String?,
        referenceLow: Double?,
        referenceHigh: Double?,
        data: [LabIndicatorPoint]
    ) {
        self.code = code
        self.name = name
        self.unit = unit
        self.referenceLow = referenceLow
        self.referenceHigh = referenceHigh
        self.data = data
    }

    public init(from decoder: Decoder) throws {
        // Decoder is invoked from a parent map; the code key isn't in the body.
        // We populate `code` later via an init-from-pair helper.
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.code = ""
        self.name = try container.decodeIfPresent(String.self, forKey: .name)
        self.unit = try container.decodeIfPresent(String.self, forKey: .unit)
        self.referenceLow = try container.decodeIfPresent(Double.self, forKey: .referenceLow)
        self.referenceHigh = try container.decodeIfPresent(Double.self, forKey: .referenceHigh)
        self.data = try container.decodeIfPresent([LabIndicatorPoint].self, forKey: .data) ?? []
    }

    public var latest: LabIndicatorPoint? {
        data.sorted { $0.date < $1.date }.last
    }

    public var earliest: LabIndicatorPoint? {
        data.sorted { $0.date < $1.date }.first
    }

    public var sortedData: [LabIndicatorPoint] {
        data.sorted { $0.date < $1.date }
    }

    public var minValue: Double? { data.compactMap { $0.value }.min() }
    public var maxValue: Double? { data.compactMap { $0.value }.max() }

    public var abnormalCount: Int {
        data.filter { $0.isAbnormal == true }.count
    }

    public var displayName: String { name ?? code }
}

public final class LabClient: @unchecked Sendable {
    private let apiClient: APIClient

    public static let defaultIndicators: [String] = [
        "ALT", "AST", "GGT",
        "HCY", "TC", "TG", "LDL",
        "FBG", "glucose_hba1c",
        "UA", "CREA", "BMI",
        "bone_vitd",
    ]

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchIndicatorTrends(indicators: [String] = LabClient.defaultIndicators) async throws -> [LabIndicatorSeries] {
        let codes = indicators.joined(separator: ",")
        let raw: [String: LabIndicatorSeries] = try await apiClient.get(
            "medical-exams/me/indicator-trends?indicators=\(codes)"
        )
        return raw.map { (code, series) in
            LabIndicatorSeries(
                code: code,
                name: series.name,
                unit: series.unit,
                referenceLow: series.referenceLow,
                referenceHigh: series.referenceHigh,
                data: series.data
            )
        }.sorted { $0.code < $1.code }
    }
}
