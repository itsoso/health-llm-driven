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

public struct NocturnalSleepStage: Decodable, Sendable, Equatable {
    public let startMs: Int64?
    public let endMs: Int64?
    public let level: String?

    enum CodingKeys: String, CodingKey {
        case startMs = "start_ms"
        case endMs = "end_ms"
        case level
    }

    public var durationMinutes: Double? {
        guard let s = startMs, let e = endMs, e > s else { return nil }
        return Double(e - s) / 60000.0
    }
}

public struct NocturnalTimeseriesResponse: Decodable, Sendable, Equatable {
    public let recordDate: String
    public let metrics: [String: [NocturnalTimeseriesPoint]]
    public let counts: [String: Int]
    public let sleepStages: [NocturnalSleepStage]

    enum CodingKeys: String, CodingKey {
        case recordDate = "record_date"
        case metrics
        case counts
        case sleepStages = "sleep_stages"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.recordDate = try container.decode(String.self, forKey: .recordDate)
        self.metrics = try container.decodeIfPresent([String: [NocturnalTimeseriesPoint]].self, forKey: .metrics) ?? [:]
        self.counts = try container.decodeIfPresent([String: Int].self, forKey: .counts) ?? [:]
        self.sleepStages = try container.decodeIfPresent([NocturnalSleepStage].self, forKey: .sleepStages) ?? []
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
    /// Count of contiguous sub-90% segments lasting at least 5 minutes, computed from sample timestamps.
    public let longHypoxicEpisodeCount: Int

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
        self.longHypoxicEpisodeCount = NocturnalSpO2Summary.computeLongHypoxicEpisodes(samples: samples, minDurationSeconds: 300)
    }

    /// Walk the sample series in epoch order, counting maximal runs of sub-90% samples whose
    /// span (end - start) is at least `minDurationSeconds`. Samples without an `epochMs` are skipped.
    static func computeLongHypoxicEpisodes(samples: [NocturnalTimeseriesPoint], minDurationSeconds: Int) -> Int {
        let ordered = samples
            .compactMap { sample -> (epoch: Int64, value: Double)? in
                guard let v = sample.value, let e = sample.epochMs else { return nil }
                return (e, v)
            }
            .sorted { $0.epoch < $1.epoch }
        guard !ordered.isEmpty else { return 0 }

        var count = 0
        var segmentStart: Int64? = nil
        var segmentEnd: Int64? = nil
        let thresholdMs: Int64 = Int64(minDurationSeconds) * 1000

        for sample in ordered {
            if sample.value < 90 {
                if segmentStart == nil { segmentStart = sample.epoch }
                segmentEnd = sample.epoch
            } else {
                if let start = segmentStart, let end = segmentEnd, end - start >= thresholdMs {
                    count += 1
                }
                segmentStart = nil
                segmentEnd = nil
            }
        }
        if let start = segmentStart, let end = segmentEnd, end - start >= thresholdMs {
            count += 1
        }
        return count
    }
}

public struct NocturnalMetricSummary: Sendable, Equatable {
    public let samples: [NocturnalTimeseriesPoint]
    public let minValue: Double?
    public let maxValue: Double?
    public let avgValue: Double?

    public init(samples: [NocturnalTimeseriesPoint]) {
        self.samples = samples
        let values = samples.compactMap { $0.value }
        if values.isEmpty {
            self.minValue = nil
            self.maxValue = nil
            self.avgValue = nil
        } else {
            self.minValue = values.min()
            self.maxValue = values.max()
            self.avgValue = values.reduce(0, +) / Double(values.count)
        }
    }
}

public struct NocturnalNightSnapshot: Sendable, Equatable {
    public let date: String
    public let spo2: NocturnalSpO2Summary
    public let heartRate: NocturnalMetricSummary
    public let respiration: NocturnalMetricSummary
    public let hrv: NocturnalMetricSummary
    public let stress: NocturnalMetricSummary
    public let sleepStages: [NocturnalSleepStage]
    public let counts: [String: Int]

    public init(response: NocturnalTimeseriesResponse) {
        self.date = response.recordDate
        self.spo2 = NocturnalSpO2Summary(date: response.recordDate, samples: response.metrics["spo2"] ?? [])
        self.heartRate = NocturnalMetricSummary(samples: response.metrics["hr"] ?? [])
        self.respiration = NocturnalMetricSummary(samples: response.metrics["respiration"] ?? [])
        self.hrv = NocturnalMetricSummary(samples: response.metrics["hrv"] ?? [])
        self.stress = NocturnalMetricSummary(samples: response.metrics["stress"] ?? [])
        self.sleepStages = response.sleepStages
        self.counts = response.counts
    }
}

public struct NocturnalWeekNight: Sendable, Equatable, Identifiable {
    public let date: String
    public let summary: NocturnalSpO2Summary?
    public let errorMessage: String?

    public var id: String { date }

    public init(date: String, summary: NocturnalSpO2Summary?, errorMessage: String? = nil) {
        self.date = date
        self.summary = summary
        self.errorMessage = errorMessage
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

    public func fetchNightly(date: String) async throws -> NocturnalNightSnapshot {
        let response: NocturnalTimeseriesResponse = try await apiClient.get(
            "garmin/nightly/me/\(date)?metrics=spo2,hr,respiration,hrv,stress,sleep_stage"
        )
        return NocturnalNightSnapshot(response: response)
    }

    /// Fetch SpO2 summaries for the trailing `days` nights ending at `endDate` (inclusive).
    /// Errors on individual nights are folded into `NocturnalWeekNight.errorMessage` so the strip
    /// can still render the nights that succeeded.
    public func fetchSpO2WeekSummary(endDate: Date = Date(), days: Int = 7) async -> [NocturnalWeekNight] {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.timeZone = TimeZone.current
        formatter.dateFormat = "yyyy-MM-dd"

        var dates: [String] = []
        let calendar = Calendar.current
        for offset in (0..<days).reversed() {
            if let d = calendar.date(byAdding: .day, value: -offset, to: endDate) {
                dates.append(formatter.string(from: d))
            }
        }

        return await withTaskGroup(of: NocturnalWeekNight.self, returning: [NocturnalWeekNight].self) { group in
            for date in dates {
                group.addTask { [self] in
                    do {
                        let summary = try await self.fetchNightlySpO2(date: date)
                        return NocturnalWeekNight(date: date, summary: summary)
                    } catch {
                        return NocturnalWeekNight(date: date, summary: nil, errorMessage: String(describing: error))
                    }
                }
            }
            var results: [NocturnalWeekNight] = []
            for await night in group {
                results.append(night)
            }
            return results.sorted { $0.date < $1.date }
        }
    }
}
