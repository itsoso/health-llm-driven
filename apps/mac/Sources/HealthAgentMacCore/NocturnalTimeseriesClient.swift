import Foundation

public struct NocturnalTimeseriesPoint: Decodable, Sendable, Equatable {
    public let sampleTime: String   // "HH:MM:SS"
    public let value: Double?
    public let epochMs: Int64?

    enum CodingKeys: String, CodingKey {
        case sampleTime = "sample_time"
        case value
        case epochMs = "epoch_ms"
    }

    public var minutesFromMidnight: Int? {
        let parts = sampleTime.split(separator: ":")
        guard parts.count >= 2,
              let h = Int(parts[0]),
              let m = Int(parts[1]) else { return nil }
        return h * 60 + m
    }
}

public struct NocturnalTimeseriesResponse: Decodable, Sendable, Equatable {
    public let recordDate: String
    public let metrics: [String: [NocturnalTimeseriesPoint]]
    public let counts: [String: Int]

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case metrics
        case counts
    }

    public var spo2Points: [NocturnalTimeseriesPoint] {
        metrics["spo2"] ?? []
    }
}

public struct NocturnalSpO2Summary: Sendable, Equatable {
    public let date: String
    public let samples: [NocturnalTimeseriesPoint]
    public let minValue: Double?
    public let avgValue: Double?
    public let percentBelow90: Double?
    public let lowestEpisodes: [NocturnalTimeseriesPoint]

    public init(date: String, samples: [NocturnalTimeseriesPoint]) {
        self.date = date
        self.samples = samples

        let values = samples.compactMap { $0.value }
        self.minValue = values.min()
        if values.isEmpty {
            self.avgValue = nil
            self.percentBelow90 = nil
        } else {
            self.avgValue = values.reduce(0, +) / Double(values.count)
            let below = values.filter { $0 < 90 }.count
            self.percentBelow90 = Double(below) / Double(values.count) * 100
        }
        self.lowestEpisodes = samples
            .filter { ($0.value ?? 100) < 90 }
            .sorted { ($0.value ?? 100) < ($1.value ?? 100) }
            .prefix(3)
            .map { $0 }
    }
}

public final class NocturnalTimeseriesClient: @unchecked Sendable {
    private let apiClient: APIClient

    public init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    public func fetchNightlySpO2(date: String) async throws -> NocturnalSpO2Summary {
        let response: NocturnalTimeseriesResponse = try await apiClient.get(
            "garmin/nightly/me/\(date)?metrics=spo2"
        )
        return NocturnalSpO2Summary(date: response.recordDate, samples: response.spo2Points)
    }
}
