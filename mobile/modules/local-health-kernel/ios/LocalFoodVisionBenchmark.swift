import Foundation

public protocol LocalFoodVisionBenchmarkInferring: Sendable {
    func infer(request: LocalFoodVisionRequest) async throws -> LocalFoodVisionResult
}

extension LocalChineseClipVisionEngine: LocalFoodVisionBenchmarkInferring {}

public enum LocalFoodVisionBenchmarkError: Error, Equatable, Sendable {
    case cancelled
    case invalidConfiguration
}

public enum LocalFoodVisionDatasetLicense: String, Codable, Equatable, Sendable {
    case licensedForEvaluation = "licensed_for_evaluation"
    case publicDomain = "public_domain"
    case synthetic
}

public struct LocalFoodVisionBenchmarkDataset: Codable, Equatable, Sendable {
    public let name: String
    public let version: String
    public let licenseStatus: LocalFoodVisionDatasetLicense
    public let containsPrivateUserData: Bool

    public init(
        name: String,
        version: String,
        licenseStatus: LocalFoodVisionDatasetLicense,
        containsPrivateUserData: Bool
    ) {
        self.name = name
        self.version = version
        self.licenseStatus = licenseStatus
        self.containsPrivateUserData = containsPrivateUserData
    }
}

public struct LocalFoodVisionBenchmarkModelProfile: Codable, Equatable, Sendable {
    public let engine: String
    public let identifier: String
    public let version: String
    public let downloadBytes: Int
    public let modelArtifactSha256: String
    public let labelBankVersion: String
    public let calibrationVersion: String
    public let calibrationManifestSha256: String
    public let minimumScore: Double
    public let minimumMargin: Double
    public let maximumCandidates: Int
    public let installedModelBytes: Int
    public let installedLabelBankBytes: Int
    public let precisionVariant: String

    public init(
        engine: String,
        identifier: String,
        version: String,
        downloadBytes: Int,
        modelArtifactSha256: String,
        labelBankVersion: String,
        calibrationVersion: String,
        calibrationManifestSha256: String,
        minimumScore: Double,
        minimumMargin: Double,
        maximumCandidates: Int,
        installedModelBytes: Int,
        installedLabelBankBytes: Int,
        precisionVariant: String
    ) {
        self.engine = engine
        self.identifier = identifier
        self.version = version
        self.downloadBytes = downloadBytes
        self.modelArtifactSha256 = modelArtifactSha256
        self.labelBankVersion = labelBankVersion
        self.calibrationVersion = calibrationVersion
        self.calibrationManifestSha256 = calibrationManifestSha256
        self.minimumScore = minimumScore
        self.minimumMargin = minimumMargin
        self.maximumCandidates = maximumCandidates
        self.installedModelBytes = installedModelBytes
        self.installedLabelBankBytes = installedLabelBankBytes
        self.precisionVariant = precisionVariant
    }
}

public struct LocalFoodVisionBenchmarkCase: Sendable {
    public let caseID: String
    public let fixtureRef: String
    public let request: LocalFoodVisionRequest
    public let expectedFoodIdentities: [String]
    public let allowedAliases: [String: [String]]
    public let nonFood: Bool

    public init(
        caseID: String,
        fixtureRef: String,
        request: LocalFoodVisionRequest,
        expectedFoodIdentities: [String],
        allowedAliases: [String: [String]],
        nonFood: Bool
    ) {
        self.caseID = caseID
        self.fixtureRef = fixtureRef
        self.request = request
        self.expectedFoodIdentities = expectedFoodIdentities
        self.allowedAliases = allowedAliases
        self.nonFood = nonFood
    }
}

public struct LocalFoodVisionBenchmarkCaseResult: Codable, Equatable, Sendable {
    public let caseID: String
    public let inputModality: String
    public let fixtureRef: String
    public let expectedFoodIdentities: [String]
    public let allowedAliases: [String: [String]]
    public let quantityAmbiguity: String
    public let nonFood: Bool
    public let predictedFoodIdentities: [String]
    public let validTypedDraft: Bool
    public let correctionCount: Int
    public let coldLatencyMs: Double
    public let warmLatencyMs: Double
    public let peakMemoryDeltaMb: Double
    public let thermalStateBefore: LocalDietThermalState
    public let thermalStateAfter: LocalDietThermalState
    public let crashed: Bool
    public let notes: String?

    private enum CodingKeys: String, CodingKey {
        case caseID = "caseId"
        case inputModality, fixtureRef, expectedFoodIdentities, allowedAliases
        case quantityAmbiguity, nonFood, predictedFoodIdentities, validTypedDraft
        case correctionCount, coldLatencyMs, warmLatencyMs, peakMemoryDeltaMb
        case thermalStateBefore, thermalStateAfter, crashed, notes
    }
}

public enum LocalFoodVisionGateVerdict: String, Codable, Equatable, Sendable {
    case pass
    case fail
    case blocked
}

public struct LocalFoodVisionBenchmarkSummary: Codable, Equatable, Sendable {
    public let caseCount: Int
    public let crashFreeCompletionRate: Double
    public let validTypedDraftRate: Double
    public let foodIdentityPrecision: Double
    public let missingItemRate: Double
    public let nonFoodRejectionRate: Double
    public let medianCorrectionCount: Double
    public let p90CorrectionCount: Double
    public let textP95WarmLatencyMs: Double?
    public let visionP95WarmLatencyMs: Double?
    public let maxPeakMemoryDeltaMb: Double
    public let worstThermalState: LocalDietThermalState
    public let gateVerdict: LocalFoodVisionGateVerdict
    public let oneSecondCompletionRate: Double
}

public struct LocalFoodVisionBenchmarkReport: Codable, Equatable, Sendable {
    public let contractVersion: String
    public let runID: String
    public let recordedAt: String
    public let dataset: LocalFoodVisionBenchmarkDataset
    public let device: LocalDietBenchmarkDevice
    public let capabilities: LocalHealthCapabilityProfile
    public let modelProfile: LocalFoodVisionBenchmarkModelProfile
    public let caseResults: [LocalFoodVisionBenchmarkCaseResult]
    public let summary: LocalFoodVisionBenchmarkSummary

    private enum CodingKeys: String, CodingKey {
        case contractVersion
        case runID = "runId"
        case recordedAt, dataset, device, capabilities, modelProfile, caseResults, summary
    }
}

public struct LocalFoodVisionBenchmark: Sendable {
    private let runID: String
    private let recordedAt: String
    private let dataset: LocalFoodVisionBenchmarkDataset
    private let device: LocalDietBenchmarkDevice
    private let capabilities: LocalHealthCapabilityProfile
    private let modelProfile: LocalFoodVisionBenchmarkModelProfile
    private let cases: [LocalFoodVisionBenchmarkCase]
    private let warmRunCount: Int
    private let engine: any LocalFoodVisionBenchmarkInferring
    private let clock: any LocalDietBenchmarkClock
    private let systemMetrics: any LocalDietBenchmarkSystemMetrics
    private let memorySampler: any LocalDietPeakMemorySampling

    public init(
        runID: String,
        recordedAt: String,
        dataset: LocalFoodVisionBenchmarkDataset,
        device: LocalDietBenchmarkDevice,
        capabilities: LocalHealthCapabilityProfile,
        modelProfile: LocalFoodVisionBenchmarkModelProfile,
        cases: [LocalFoodVisionBenchmarkCase],
        warmRunCount: Int,
        engine: any LocalFoodVisionBenchmarkInferring,
        clock: any LocalDietBenchmarkClock,
        systemMetrics: any LocalDietBenchmarkSystemMetrics,
        memorySampler: any LocalDietPeakMemorySampling
    ) {
        self.runID = runID
        self.recordedAt = recordedAt
        self.dataset = dataset
        self.device = device
        self.capabilities = capabilities
        self.modelProfile = modelProfile
        self.cases = cases
        self.warmRunCount = warmRunCount
        self.engine = engine
        self.clock = clock
        self.systemMetrics = systemMetrics
        self.memorySampler = memorySampler
    }

    public func run() async throws -> LocalFoodVisionBenchmarkReport {
        guard !runID.isEmpty, !cases.isEmpty, warmRunCount > 0,
              !dataset.containsPrivateUserData,
              modelProfile.engine == "custom_core_ml",
              modelProfile.calibrationManifestSha256.count == 64,
              modelProfile.minimumScore.isFinite,
              modelProfile.minimumMargin.isFinite,
              (-1...1).contains(modelProfile.minimumScore),
              (0...2).contains(modelProfile.minimumMargin),
              (1...3).contains(modelProfile.maximumCandidates) else {
            throw LocalFoodVisionBenchmarkError.invalidConfiguration
        }
        var results: [LocalFoodVisionBenchmarkCaseResult] = []
        for benchmarkCase in cases {
            results.append(try await run(benchmarkCase))
        }
        return LocalFoodVisionBenchmarkReport(
            contractVersion: "1.0.0",
            runID: runID,
            recordedAt: recordedAt,
            dataset: dataset,
            device: device,
            capabilities: capabilities,
            modelProfile: modelProfile,
            caseResults: results,
            summary: summarize(results)
        )
    }

    private func run(
        _ benchmarkCase: LocalFoodVisionBenchmarkCase
    ) async throws -> LocalFoodVisionBenchmarkCaseResult {
        let thermalBefore = systemMetrics.thermalState()
        var latencies: [Double] = []
        var peakDeltaBytes: UInt64 = 0
        var latestResult: LocalFoodVisionResult?
        var failureNote: String?

        for _ in 0...warmRunCount {
            do {
                let measured = try await measure(request: benchmarkCase.request)
                latencies.append(measured.latencyMs)
                peakDeltaBytes = max(peakDeltaBytes, measured.peakDeltaBytes)
                latestResult = measured.result
            } catch {
                if isCancellation(error) {
                    throw LocalFoodVisionBenchmarkError.cancelled
                }
                failureNote = "inference_error:\(String(reflecting: type(of: error)))"
                break
            }
        }
        let thermalAfter = systemMetrics.thermalState()
        let crashed = failureNote != nil
        let predicted = latestResult?.candidates.map(\.canonicalFoodID) ?? []
        let expected = Set(benchmarkCase.expectedFoodIdentities)
        let predictedSet = Set(predicted)
        let corrections = expected.symmetricDifference(predictedSet).count
        return LocalFoodVisionBenchmarkCaseResult(
            caseID: benchmarkCase.caseID,
            inputModality: "photo",
            fixtureRef: benchmarkCase.fixtureRef,
            expectedFoodIdentities: benchmarkCase.expectedFoodIdentities,
            allowedAliases: benchmarkCase.allowedAliases,
            quantityAmbiguity: "unknown",
            nonFood: benchmarkCase.nonFood,
            predictedFoodIdentities: predicted,
            validTypedDraft: !crashed && latestResult?.decision != .unknown,
            correctionCount: corrections,
            coldLatencyMs: latencies.first ?? 0,
            warmLatencyMs: percentile(Array(latencies.dropFirst()), probability: 0.95) ?? 0,
            peakMemoryDeltaMb: Double(peakDeltaBytes) / 1_000_000,
            thermalStateBefore: thermalBefore,
            thermalStateAfter: thermalAfter,
            crashed: crashed,
            notes: failureNote
        )
    }

    private func measure(
        request: LocalFoodVisionRequest
    ) async throws -> (result: LocalFoodVisionResult, latencyMs: Double, peakDeltaBytes: UInt64) {
        let initial = try systemMetrics.footprintBytes()
        let start = clock.nowNanoseconds()
        do {
            let measured = try await memorySampler.measure(initialFootprintBytes: initial) {
                try await engine.infer(request: request)
            }
            let end = clock.nowNanoseconds()
            return (
                measured.value,
                Double(end - start) / 1_000_000,
                measured.peakFootprintBytes > initial
                    ? measured.peakFootprintBytes - initial
                    : 0
            )
        } catch {
            _ = clock.nowNanoseconds()
            throw error
        }
    }

    private func summarize(
        _ results: [LocalFoodVisionBenchmarkCaseResult]
    ) -> LocalFoodVisionBenchmarkSummary {
        let count = Double(results.count)
        let completed = results.filter { !$0.crashed }
        let valid = results.filter(\.validTypedDraft)
        let predicted = results.flatMap { Set($0.predictedFoodIdentities) }
        let truePositiveCount = results.reduce(0) { total, result in
            total + Set(result.predictedFoodIdentities)
                .intersection(Set(result.expectedFoodIdentities)).count
        }
        let expectedCount = results.reduce(0) { $0 + Set($1.expectedFoodIdentities).count }
        let missingCount = results.reduce(0) { total, result in
            total + Set(result.expectedFoodIdentities)
                .subtracting(Set(result.predictedFoodIdentities)).count
        }
        let nonFood = results.filter(\.nonFood)
        let rejectedNonFood = nonFood.filter { $0.predictedFoodIdentities.isEmpty && !$0.crashed }
        let corrections = results.map { Double($0.correctionCount) }
        let oneSecond = results.filter {
            !$0.crashed && max($0.coldLatencyMs, $0.warmLatencyMs) <= 1_000
        }
        return LocalFoodVisionBenchmarkSummary(
            caseCount: results.count,
            crashFreeCompletionRate: Double(completed.count) / count,
            validTypedDraftRate: Double(valid.count) / count,
            foodIdentityPrecision: predicted.isEmpty ? 1 : Double(truePositiveCount) / Double(predicted.count),
            missingItemRate: expectedCount == 0 ? 0 : Double(missingCount) / Double(expectedCount),
            nonFoodRejectionRate: nonFood.isEmpty ? 1 : Double(rejectedNonFood.count) / Double(nonFood.count),
            medianCorrectionCount: percentile(corrections, probability: 0.5) ?? 0,
            p90CorrectionCount: percentile(corrections, probability: 0.9) ?? 0,
            textP95WarmLatencyMs: nil,
            visionP95WarmLatencyMs: percentile(results.map(\.warmLatencyMs), probability: 0.95),
            maxPeakMemoryDeltaMb: results.map(\.peakMemoryDeltaMb).max() ?? 0,
            worstThermalState: results
                .flatMap { [$0.thermalStateBefore, $0.thermalStateAfter] }
                .max(by: { thermalRank($0) < thermalRank($1) }) ?? .unknown,
            gateVerdict: .blocked,
            oneSecondCompletionRate: Double(oneSecond.count) / count
        )
    }

    private func percentile(_ values: [Double], probability: Double) -> Double? {
        guard !values.isEmpty else { return nil }
        let sorted = values.sorted()
        let index = Int(ceil(probability * Double(sorted.count))) - 1
        return sorted[max(0, min(sorted.count - 1, index))]
    }

    private func isCancellation(_ error: Error) -> Bool {
        error is CancellationError || (error as? LocalFoodVisionError) == .cancelled
    }

    private func thermalRank(_ state: LocalDietThermalState) -> Int {
        switch state {
        case .nominal: return 0
        case .fair: return 1
        case .serious: return 2
        case .critical: return 3
        case .unknown: return 4
        }
    }
}
