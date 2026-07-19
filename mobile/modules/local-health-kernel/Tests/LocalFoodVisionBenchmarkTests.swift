import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalFoodVisionBenchmarkTests: XCTestCase {
    func testCapturesColdRepeatedWarmMemoryThermalAndAggregates() async throws {
        let benchmark = makeBenchmark(
            engine: VisionEngineStub(results: [candidateResult, candidateResult, candidateResult]),
            clock: VisionSequenceClock([
                0, 200_000_000,
                300_000_000, 400_000_000,
                500_000_000, 800_000_000,
            ]),
            metrics: VisionSequenceMetrics(
                footprints: [100_000_000, 100_000_000, 100_000_000],
                thermal: [.nominal, .fair]
            ),
            memory: VisionPeakSampler([150_000_000, 140_000_000, 160_000_000])
        )

        let report = try await benchmark.run()
        let result = try XCTUnwrap(report.caseResults.first)

        XCTAssertEqual(result.coldLatencyMs, 200)
        XCTAssertEqual(result.warmLatencyMs, 300)
        XCTAssertEqual(result.peakMemoryDeltaMb, 60, accuracy: 0.0001)
        XCTAssertEqual(result.thermalStateBefore, .nominal)
        XCTAssertEqual(result.thermalStateAfter, .fair)
        XCTAssertEqual(result.predictedFoodIdentities, ["rice"])
        XCTAssertFalse(result.crashed)
        XCTAssertEqual(report.summary.visionP95WarmLatencyMs, 300)
        XCTAssertEqual(report.summary.oneSecondCompletionRate, 1)
        XCTAssertEqual(report.summary.crashFreeCompletionRate, 1)
        XCTAssertEqual(report.summary.fp16ToCompressedIdentityPrecisionDelta, 0.01)
    }

    func testInferenceFailureIsCapturedWithoutACloudFallback() async throws {
        let benchmark = makeBenchmark(
            engine: VisionEngineStub(error: VisionBenchmarkFixtureError.inferenceFailed),
            clock: VisionSequenceClock([0, 10_000_000]),
            metrics: VisionSequenceMetrics(
                footprints: [100_000_000],
                thermal: [.nominal, .nominal]
            ),
            memory: VisionPeakSampler([110_000_000])
        )

        let report = try await benchmark.run()

        XCTAssertTrue(try XCTUnwrap(report.caseResults.first).crashed)
        XCTAssertEqual(report.summary.crashFreeCompletionRate, 0)
        XCTAssertEqual(report.summary.oneSecondCompletionRate, 0)
        XCTAssertEqual(report.summary.gateVerdict, .blocked)
    }

    func testCancellationStopsTheRunInsteadOfWritingPartialEvidence() async throws {
        let benchmark = makeBenchmark(
            engine: VisionEngineStub(error: LocalFoodVisionError.cancelled),
            clock: VisionSequenceClock([0, 10_000_000]),
            metrics: VisionSequenceMetrics(
                footprints: [100_000_000],
                thermal: [.nominal, .nominal]
            ),
            memory: VisionPeakSampler([110_000_000])
        )

        do {
            _ = try await benchmark.run()
            XCTFail("Expected cancellation")
        } catch {
            XCTAssertEqual(error as? LocalFoodVisionBenchmarkError, .cancelled)
        }
    }

    func testReportRoundTripsWithExactContractKeysAndNoSensitivePayload() async throws {
        let report = try await makeBenchmark().run()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(report)
        let decoded = try JSONDecoder().decode(LocalFoodVisionBenchmarkReport.self, from: data)
        let json = String(decoding: data, as: UTF8.self)

        XCTAssertEqual(decoded, report)
        XCTAssertTrue(json.contains("\"contractVersion\":"))
        XCTAssertTrue(json.contains("\"caseId\":"))
        XCTAssertTrue(json.contains("\"oneSecondCompletionRate\":"))
        XCTAssertTrue(json.contains("\"modelArtifactSha256\":"))
        for forbidden in ["rgba8", "tensor", "embedding", "photoPath", "userId", "HealthKit"] {
            XCTAssertFalse(json.contains(forbidden))
        }
    }

    private func makeBenchmark(
        engine: (any LocalFoodVisionBenchmarkInferring)? = nil,
        clock: any LocalDietBenchmarkClock = VisionSequenceClock([
            0, 100_000_000,
            200_000_000, 300_000_000,
            400_000_000, 500_000_000,
        ]),
        metrics: any LocalDietBenchmarkSystemMetrics = VisionSequenceMetrics(
            footprints: [100_000_000, 100_000_000, 100_000_000],
            thermal: [.nominal, .nominal]
        ),
        memory: any LocalDietPeakMemorySampling = VisionPeakSampler([
            120_000_000, 120_000_000, 120_000_000,
        ])
    ) -> LocalFoodVisionBenchmark {
        LocalFoodVisionBenchmark(
            runID: "opaque-run-001",
            recordedAt: "2026-07-18T20:00:00Z",
            dataset: .init(
                name: "authorized-food-eval",
                version: "v1",
                licenseStatus: .licensedForEvaluation,
                containsPrivateUserData: false
            ),
            device: .init(
                hardwareIdentifier: "iPhone18,2",
                deviceClass: "phone",
                osVersion: "iOS 26.6",
                isSimulator: false,
                appBuild: "g2-spike"
            ),
            capabilities: capabilityProfile,
            modelProfile: .init(
                engine: "custom_core_ml",
                identifier: "OFA-Sys/chinese-clip-rn50-image-tower",
                version: "717ba215769231e53b9b7c6b9d329b9cc5944418",
                downloadBytes: 39_626_225,
                modelArtifactSha256: String(repeating: "a", count: 64),
                labelBankVersion: "cn-food-labels-v2",
                calibrationVersion: "cn-clip-calibration-v2",
                installedModelBytes: 39_296_441,
                installedLabelBankBytes: 329_784,
                precisionVariant: "int8-linear-per-channel-65536"
            ),
            cases: [
                .init(
                    caseID: "opaque-case-001",
                    fixtureRef: "fixture-001",
                    request: imageRequest,
                    expectedFoodIdentities: ["rice"],
                    allowedAliases: [:],
                    nonFood: false
                )
            ],
            warmRunCount: 2,
            fp16ToCompressedIdentityPrecisionDelta: 0.01,
            engine: engine ?? VisionEngineStub(
                results: [candidateResult, candidateResult, candidateResult]
            ),
            clock: clock,
            systemMetrics: metrics,
            memorySampler: memory
        )
    }

    private var candidateResult: LocalFoodVisionResult {
        .init(
            decision: .candidate,
            candidates: [
                .init(
                    canonicalFoodID: "rice",
                    displayName: "米饭",
                    category: "food",
                    score: 0.9,
                    evidence: .wholeImage,
                    regionIndex: nil
                )
            ],
            topScore: 0.9,
            margin: 0.1,
            provenance: .init(
                modelArtifactSHA256: String(repeating: "a", count: 64),
                labelBankVersion: "cn-food-labels-v2",
                calibrationVersion: "cn-clip-calibration-v2",
                precisionVariant: "int8-linear-per-channel-65536"
            )
        )
    }

    private var imageRequest: LocalFoodVisionRequest {
        .init(
            image: .init(
                width: 1,
                height: 1,
                orientation: .up,
                rgba8: Data([128, 128, 128, 255])
            )
        )
    }

    private var capabilityProfile: LocalHealthCapabilityProfile {
        .init(
            schemaVersion: 1,
            osVersion: "iOS 26.6",
            deviceClass: "phone",
            isSimulator: false,
            systemLanguageModel: .init(available: false, reason: .deviceNotEligible),
            multimodalLanguageModel: .init(available: false, reason: .sdkNotSupported),
            vision: .init(
                textRecognition: true,
                imageClassification: true,
                barcodeDetection: true
            )
        )
    }
}

private enum VisionBenchmarkFixtureError: Error {
    case inferenceFailed
}

private actor VisionEngineStub: LocalFoodVisionBenchmarkInferring {
    private var results: [LocalFoodVisionResult]
    private let error: Error?

    init(results: [LocalFoodVisionResult] = [], error: Error? = nil) {
        self.results = results
        self.error = error
    }

    func infer(request: LocalFoodVisionRequest) async throws -> LocalFoodVisionResult {
        if let error { throw error }
        precondition(!results.isEmpty, "Vision result fixture exhausted")
        return results.removeFirst()
    }
}

private final class VisionSequenceClock: LocalDietBenchmarkClock, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [UInt64]

    init(_ values: [UInt64]) { self.values = values }

    func nowNanoseconds() -> UInt64 {
        lock.withLock {
            precondition(!values.isEmpty, "Clock fixture exhausted")
            return values.removeFirst()
        }
    }
}

private final class VisionSequenceMetrics: LocalDietBenchmarkSystemMetrics, @unchecked Sendable {
    private let lock = NSLock()
    private var footprints: [UInt64]
    private var thermal: [LocalDietThermalState]

    init(footprints: [UInt64], thermal: [LocalDietThermalState]) {
        self.footprints = footprints
        self.thermal = thermal
    }

    func footprintBytes() -> UInt64 {
        lock.withLock { footprints.removeFirst() }
    }

    func thermalState() -> LocalDietThermalState {
        lock.withLock { thermal.removeFirst() }
    }
}

private final class VisionPeakSampler: LocalDietPeakMemorySampling, @unchecked Sendable {
    private let lock = NSLock()
    private var peaks: [UInt64]

    init(_ peaks: [UInt64]) { self.peaks = peaks }

    func measure<T: Sendable>(
        initialFootprintBytes: UInt64,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> (value: T, peakFootprintBytes: UInt64) {
        let peak = lock.withLock { peaks.removeFirst() }
        return (try await operation(), peak)
    }
}
