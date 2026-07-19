import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalDietInferenceBenchmarkTests: XCTestCase {
    func testUnavailableModelReturnsReasonWithoutRunningInference() async throws {
        let runner = RunnerStub(
            coldDraft: fixtureDraft,
            warmDraft: fixtureDraft
        )
        let benchmark = makeBenchmark(
            systemLanguageModel: .init(
                available: false,
                reason: .appleIntelligenceNotEnabled
            ),
            runner: runner
        )

        let report = try await benchmark.run()

        XCTAssertEqual(report.status, .unavailable)
        XCTAssertEqual(report.unavailableReason, .appleIntelligenceNotEnabled)
        XCTAssertNil(report.caseResult)
        let invocationCount = await runner.invocationCount
        XCTAssertEqual(invocationCount, 0)
    }

    func testAvailableModelCapturesColdWarmLatencyMemoryAndThermal() async throws {
        let clock = SequenceClock([1_000_000_000, 2_250_000_000, 3_000_000_000, 3_400_000_000])
        let systemMetrics = SequenceSystemMetrics(
            footprints: [100_000_000, 120_000_000],
            thermalStates: [.nominal, .fair, .fair, .serious]
        )
        let memorySampler = FixedPeakMemorySampler([
            160_000_000,
            155_000_000,
        ])
        let runner = RunnerStub(
            coldDraft: fixtureDraft,
            warmDraft: fixtureDraft
        )
        let benchmark = makeBenchmark(
            runner: runner,
            clock: clock,
            systemMetrics: systemMetrics,
            memorySampler: memorySampler
        )

        let report = try await benchmark.run()
        let result = try XCTUnwrap(report.caseResult)

        XCTAssertEqual(report.status, .completed)
        XCTAssertNil(report.unavailableReason)
        XCTAssertEqual(result.coldLatencyMs, 1_250)
        XCTAssertEqual(result.warmLatencyMs, 400)
        XCTAssertEqual(result.peakMemoryDeltaMb, 60, accuracy: 0.0001)
        XCTAssertEqual(result.thermalStateBefore, .nominal)
        XCTAssertEqual(result.thermalStateAfter, .serious)
        XCTAssertEqual(result.predictedFoods, fixtureDraft.foods)
        let phases = await runner.phases
        XCTAssertEqual(phases, [.cold, .warm])
    }

    func testRunnerFailureIsPropagatedWithoutFallback() async throws {
        let runner = RunnerStub(
            coldDraft: fixtureDraft,
            warmDraft: fixtureDraft,
            error: RunnerError.inferenceFailed
        )
        let benchmark = makeBenchmark(runner: runner)

        do {
            _ = try await benchmark.run()
            XCTFail("Expected the model failure to propagate")
        } catch {
            XCTAssertEqual(error as? RunnerError, .inferenceFailed)
        }

        let invocationCount = await runner.invocationCount
        XCTAssertEqual(invocationCount, 1)
    }

    func testFootprintFailureIsPropagatedBeforeInference() async throws {
        let runner = RunnerStub(
            coldDraft: fixtureDraft,
            warmDraft: fixtureDraft
        )
        let benchmark = makeBenchmark(
            runner: runner,
            systemMetrics: FailingSystemMetrics()
        )

        do {
            _ = try await benchmark.run()
            XCTFail("Expected process-footprint failure to propagate")
        } catch {
            XCTAssertEqual(
                error as? LocalDietBenchmarkMetricsError,
                .processFootprintUnavailable(code: 5)
            )
        }

        let invocationCount = await runner.invocationCount
        XCTAssertEqual(invocationCount, 0)
    }

    func testCompletedReportRoundTripsThroughJSON() async throws {
        let report = try await makeBenchmark().run()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]

        let data = try encoder.encode(report)
        let decoded = try JSONDecoder().decode(
            LocalDietInferenceBenchmarkReport.self,
            from: data
        )

        XCTAssertEqual(decoded, report)
        XCTAssertTrue(String(decoding: data, as: UTF8.self).contains("\"caseId\":"))
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("\"caseID\":"))
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("calories"))
        XCTAssertFalse(String(decoding: data, as: UTF8.self).contains("userId"))
    }

    func testLiveBenchmarkRequiresExplicitEnvironmentFlag() {
        XCTAssertFalse(LocalDietLiveBenchmark.isExplicitlyEnabled(environment: [:]))
        XCTAssertFalse(
            LocalDietLiveBenchmark.isExplicitlyEnabled(
                environment: ["LOCAL_DIET_ENABLE_LIVE_BENCHMARK": "0"]
            )
        )
        XCTAssertTrue(
            LocalDietLiveBenchmark.isExplicitlyEnabled(
                environment: ["LOCAL_DIET_ENABLE_LIVE_BENCHMARK": "1"]
            )
        )
    }

    @MainActor
    func testLiveBenchmarkEmitsDeviceReportOnlyWhenExplicitlyEnabled() async throws {
        guard LocalDietLiveBenchmark.isExplicitlyEnabled() else {
            throw XCTSkip("Set LOCAL_DIET_ENABLE_LIVE_BENCHMARK=1 on a test device")
        }

        let optionalReport = try await LocalDietLiveBenchmark.runIfExplicitlyEnabled()
        let report = try XCTUnwrap(optionalReport)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(report)

        XCTAssertFalse(report.device.isSimulator)
        print("LOCAL_DIET_INFERENCE_BENCHMARK=\(String(decoding: data, as: UTF8.self))")
    }

    func testFixtureIsSyntheticAndLimitedToMealExtraction() {
        XCTAssertEqual(LocalDietInferenceBenchmark.fixtureID, "synthetic_zh_meal_v1")
        XCTAssertEqual(
            LocalDietInferenceBenchmark.syntheticMealText,
            "午餐吃了150克米饭、120克清蒸鲈鱼和一碗约200克西兰花。"
        )
        XCTAssertFalse(LocalDietInferenceBenchmark.syntheticPrompt.contains("热量"))
        XCTAssertFalse(LocalDietInferenceBenchmark.syntheticPrompt.contains("营养"))
        XCTAssertFalse(LocalDietInferenceBenchmark.syntheticPrompt.contains("用户"))
    }

    private var fixtureDraft: LocalDietDraft {
        .init(
            foods: [
                .init(name: "米饭", quantity: 150, unit: "克"),
                .init(name: "清蒸鲈鱼", quantity: 120, unit: "克"),
                .init(name: "西兰花", quantity: 200, unit: "克"),
            ]
        )
    }

    private func makeBenchmark(
        systemLanguageModel: LocalHealthCapabilityAvailability = .init(
            available: true,
            reason: nil
        ),
        runner: (any LocalDietInferenceRunning)? = nil,
        clock: (any LocalDietBenchmarkClock)? = nil,
        systemMetrics: (any LocalDietBenchmarkSystemMetrics)? = nil,
        memorySampler: (any LocalDietPeakMemorySampling)? = nil
    ) -> LocalDietInferenceBenchmark {
        let profile = LocalHealthCapabilityProfile(
            schemaVersion: 1,
            osVersion: "26.5",
            deviceClass: "phone",
            isSimulator: false,
            systemLanguageModel: systemLanguageModel,
            multimodalLanguageModel: .init(available: false, reason: .sdkNotSupported),
            vision: .init(
                textRecognition: true,
                imageClassification: true,
                barcodeDetection: true
            )
        )

        return LocalDietInferenceBenchmark(
            capabilities: profile,
            device: .init(
                hardwareIdentifier: "iPhone18,2",
                deviceClass: "phone",
                osVersion: "26.5",
                isSimulator: false,
                appBuild: "swift-spike"
            ),
            modelProfile: .init(
                engine: "apple_foundation_models",
                identifier: "system_language_model_default",
                version: "system",
                downloadBytes: 0
            ),
            runner: runner ?? RunnerStub(coldDraft: fixtureDraft, warmDraft: fixtureDraft),
            clock: clock ?? SequenceClock([0, 1_000_000, 2_000_000, 2_500_000]),
            systemMetrics: systemMetrics ?? SequenceSystemMetrics(
                footprints: [100_000_000, 100_000_000],
                thermalStates: [.nominal, .nominal, .nominal, .nominal]
            ),
            memorySampler: memorySampler ?? FixedPeakMemorySampler([
                100_000_000,
                100_000_000,
            ])
        )
    }
}

private enum RunnerError: Error, Equatable {
    case inferenceFailed
}

private actor RunnerStub: LocalDietInferenceRunning {
    private let coldDraft: LocalDietDraft
    private let warmDraft: LocalDietDraft
    private let error: RunnerError?
    private(set) var phases: [LocalDietInferencePhase] = []

    init(
        coldDraft: LocalDietDraft,
        warmDraft: LocalDietDraft,
        error: RunnerError? = nil
    ) {
        self.coldDraft = coldDraft
        self.warmDraft = warmDraft
        self.error = error
    }

    var invocationCount: Int {
        phases.count
    }

    func infer(
        prompt: String,
        phase: LocalDietInferencePhase
    ) async throws -> LocalDietDraft {
        phases.append(phase)
        if let error {
            throw error
        }
        return phase == .cold ? coldDraft : warmDraft
    }
}

private final class SequenceClock: LocalDietBenchmarkClock, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [UInt64]

    init(_ values: [UInt64]) {
        self.values = values
    }

    func nowNanoseconds() -> UInt64 {
        lock.withLock {
            precondition(!values.isEmpty, "Clock fixture exhausted")
            return values.removeFirst()
        }
    }
}

private final class SequenceSystemMetrics: LocalDietBenchmarkSystemMetrics, @unchecked Sendable {
    private let lock = NSLock()
    private var footprints: [UInt64]
    private var thermalStates: [LocalDietThermalState]

    init(
        footprints: [UInt64],
        thermalStates: [LocalDietThermalState]
    ) {
        self.footprints = footprints
        self.thermalStates = thermalStates
    }

    func footprintBytes() -> UInt64 {
        lock.withLock {
            precondition(!footprints.isEmpty, "Footprint fixture exhausted")
            return footprints.removeFirst()
        }
    }

    func thermalState() -> LocalDietThermalState {
        lock.withLock {
            precondition(!thermalStates.isEmpty, "Thermal fixture exhausted")
            return thermalStates.removeFirst()
        }
    }
}

private final class FixedPeakMemorySampler: LocalDietPeakMemorySampling, @unchecked Sendable {
    private let lock = NSLock()
    private var peaks: [UInt64]

    init(_ peaks: [UInt64]) {
        self.peaks = peaks
    }

    func measure<T: Sendable>(
        initialFootprintBytes: UInt64,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> (value: T, peakFootprintBytes: UInt64) {
        let peak = lock.withLock {
            precondition(!peaks.isEmpty, "Peak-memory fixture exhausted")
            return peaks.removeFirst()
        }
        return (try await operation(), peak)
    }
}

private struct FailingSystemMetrics: LocalDietBenchmarkSystemMetrics {
    func footprintBytes() throws -> UInt64 {
        throw LocalDietBenchmarkMetricsError.processFootprintUnavailable(code: 5)
    }

    func thermalState() -> LocalDietThermalState {
        .unknown
    }
}
