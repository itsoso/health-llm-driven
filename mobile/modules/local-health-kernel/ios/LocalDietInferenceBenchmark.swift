import Foundation

#if canImport(Darwin)
import Darwin
#endif

#if canImport(FoundationModels)
import FoundationModels
#endif

public struct LocalDietFoodDraft: Codable, Equatable, Sendable {
    public let name: String
    public let quantity: Double
    public let unit: String

    public init(name: String, quantity: Double, unit: String) {
        self.name = name
        self.quantity = quantity
        self.unit = unit
    }
}

public struct LocalDietDraft: Codable, Equatable, Sendable {
    public let foods: [LocalDietFoodDraft]

    public init(foods: [LocalDietFoodDraft]) {
        self.foods = foods
    }
}

public enum LocalDietInferencePhase: String, Codable, Equatable, Sendable {
    case cold
    case warm
}

public enum LocalDietThermalState: String, Codable, Equatable, Sendable {
    case nominal
    case fair
    case serious
    case critical
    case unknown
}

public enum LocalDietBenchmarkMetricsError: Error, Equatable, Sendable {
    case processFootprintUnavailable(code: Int32)
    case unsupportedPlatform
}

public struct LocalDietBenchmarkDevice: Codable, Equatable, Sendable {
    public let hardwareIdentifier: String
    public let deviceClass: String
    public let osVersion: String
    public let isSimulator: Bool
    public let appBuild: String

    public init(
        hardwareIdentifier: String,
        deviceClass: String,
        osVersion: String,
        isSimulator: Bool,
        appBuild: String
    ) {
        self.hardwareIdentifier = hardwareIdentifier
        self.deviceClass = deviceClass
        self.osVersion = osVersion
        self.isSimulator = isSimulator
        self.appBuild = appBuild
    }
}

public struct LocalDietBenchmarkModelProfile: Codable, Equatable, Sendable {
    public let engine: String
    public let identifier: String
    public let version: String
    public let downloadBytes: Int

    public init(
        engine: String,
        identifier: String,
        version: String,
        downloadBytes: Int
    ) {
        self.engine = engine
        self.identifier = identifier
        self.version = version
        self.downloadBytes = downloadBytes
    }
}

public struct LocalDietInferenceBenchmarkCaseResult: Codable, Equatable, Sendable {
    public let caseID: String
    public let inputModality: String
    public let fixtureRef: String
    public let predictedFoods: [LocalDietFoodDraft]
    public let coldLatencyMs: Double
    public let warmLatencyMs: Double
    public let peakMemoryDeltaMb: Double
    public let thermalStateBefore: LocalDietThermalState
    public let thermalStateAfter: LocalDietThermalState

    private enum CodingKeys: String, CodingKey {
        case caseID = "caseId"
        case inputModality
        case fixtureRef
        case predictedFoods
        case coldLatencyMs
        case warmLatencyMs
        case peakMemoryDeltaMb
        case thermalStateBefore
        case thermalStateAfter
    }

    public init(
        caseID: String,
        inputModality: String,
        fixtureRef: String,
        predictedFoods: [LocalDietFoodDraft],
        coldLatencyMs: Double,
        warmLatencyMs: Double,
        peakMemoryDeltaMb: Double,
        thermalStateBefore: LocalDietThermalState,
        thermalStateAfter: LocalDietThermalState
    ) {
        self.caseID = caseID
        self.inputModality = inputModality
        self.fixtureRef = fixtureRef
        self.predictedFoods = predictedFoods
        self.coldLatencyMs = coldLatencyMs
        self.warmLatencyMs = warmLatencyMs
        self.peakMemoryDeltaMb = peakMemoryDeltaMb
        self.thermalStateBefore = thermalStateBefore
        self.thermalStateAfter = thermalStateAfter
    }
}

public enum LocalDietInferenceBenchmarkStatus: String, Codable, Equatable, Sendable {
    case completed
    case unavailable
}

public struct LocalDietInferenceBenchmarkReport: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let status: LocalDietInferenceBenchmarkStatus
    public let unavailableReason: LocalHealthCapabilityReason?
    public let device: LocalDietBenchmarkDevice
    public let capabilities: LocalHealthCapabilityProfile
    public let modelProfile: LocalDietBenchmarkModelProfile
    public let caseResult: LocalDietInferenceBenchmarkCaseResult?

    public init(
        schemaVersion: Int,
        status: LocalDietInferenceBenchmarkStatus,
        unavailableReason: LocalHealthCapabilityReason?,
        device: LocalDietBenchmarkDevice,
        capabilities: LocalHealthCapabilityProfile,
        modelProfile: LocalDietBenchmarkModelProfile,
        caseResult: LocalDietInferenceBenchmarkCaseResult?
    ) {
        self.schemaVersion = schemaVersion
        self.status = status
        self.unavailableReason = unavailableReason
        self.device = device
        self.capabilities = capabilities
        self.modelProfile = modelProfile
        self.caseResult = caseResult
    }
}

public protocol LocalDietInferenceRunning: Sendable {
    func infer(
        prompt: String,
        phase: LocalDietInferencePhase
    ) async throws -> LocalDietDraft
}

public protocol LocalDietBenchmarkClock: Sendable {
    func nowNanoseconds() -> UInt64
}

public protocol LocalDietBenchmarkSystemMetrics: Sendable {
    func footprintBytes() throws -> UInt64
    func thermalState() -> LocalDietThermalState
}

public protocol LocalDietPeakMemorySampling: Sendable {
    func measure<T: Sendable>(
        initialFootprintBytes: UInt64,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> (value: T, peakFootprintBytes: UInt64)
}

public struct LocalDietUptimeClock: LocalDietBenchmarkClock {
    public init() {}

    public func nowNanoseconds() -> UInt64 {
        DispatchTime.now().uptimeNanoseconds
    }
}

public struct LocalDietProcessSystemMetrics: LocalDietBenchmarkSystemMetrics {
    public init() {}

    public func footprintBytes() throws -> UInt64 {
        try LocalDietProcessFootprint.currentBytes()
    }

    public func thermalState() -> LocalDietThermalState {
        switch ProcessInfo.processInfo.thermalState {
        case .nominal:
            return .nominal
        case .fair:
            return .fair
        case .serious:
            return .serious
        case .critical:
            return .critical
        @unknown default:
            return .unknown
        }
    }
}

public struct LocalDietPollingPeakMemorySampler: LocalDietPeakMemorySampling {
    private let intervalNanoseconds: UInt64
    private let footprint: @Sendable () throws -> UInt64

    public init(intervalNanoseconds: UInt64 = 10_000_000) {
        self.intervalNanoseconds = intervalNanoseconds
        self.footprint = { try LocalDietProcessFootprint.currentBytes() }
    }

    public init(
        intervalNanoseconds: UInt64,
        footprint: @escaping @Sendable () throws -> UInt64
    ) {
        self.intervalNanoseconds = intervalNanoseconds
        self.footprint = footprint
    }

    public func measure<T: Sendable>(
        initialFootprintBytes: UInt64,
        operation: @escaping @Sendable () async throws -> T
    ) async throws -> (value: T, peakFootprintBytes: UInt64) {
        let intervalNanoseconds = intervalNanoseconds
        let footprint = footprint
        let monitor = Task.detached(priority: .utility) {
            var peak = initialFootprintBytes
            while !Task.isCancelled {
                peak = max(peak, try footprint())
                do {
                    try await Task.sleep(nanoseconds: intervalNanoseconds)
                } catch {
                    break
                }
            }
            return peak
        }

        do {
            let value = try await operation()
            monitor.cancel()
            let sampledPeak = try await monitor.value
            return (value, max(sampledPeak, try footprint()))
        } catch {
            monitor.cancel()
            _ = try? await monitor.value
            throw error
        }
    }
}

public struct LocalDietInferenceBenchmark: Sendable {
    public static let fixtureID = "synthetic_zh_meal_v1"
    public static let syntheticMealText = "午餐吃了150克米饭、120克清蒸鲈鱼和一碗约200克西兰花。"
    public static let syntheticPrompt = """
    从下面的合成餐食描述中提取食物名称、数量和单位。不要补充描述中没有的内容。
    描述：\(syntheticMealText)
    """

    private let capabilities: LocalHealthCapabilityProfile
    private let device: LocalDietBenchmarkDevice
    private let modelProfile: LocalDietBenchmarkModelProfile
    private let runner: any LocalDietInferenceRunning
    private let clock: any LocalDietBenchmarkClock
    private let systemMetrics: any LocalDietBenchmarkSystemMetrics
    private let memorySampler: any LocalDietPeakMemorySampling

    public init(
        capabilities: LocalHealthCapabilityProfile,
        device: LocalDietBenchmarkDevice,
        modelProfile: LocalDietBenchmarkModelProfile,
        runner: any LocalDietInferenceRunning,
        clock: any LocalDietBenchmarkClock,
        systemMetrics: any LocalDietBenchmarkSystemMetrics,
        memorySampler: any LocalDietPeakMemorySampling
    ) {
        self.capabilities = capabilities
        self.device = device
        self.modelProfile = modelProfile
        self.runner = runner
        self.clock = clock
        self.systemMetrics = systemMetrics
        self.memorySampler = memorySampler
    }

    public func run() async throws -> LocalDietInferenceBenchmarkReport {
        guard capabilities.systemLanguageModel.available else {
            return LocalDietInferenceBenchmarkReport(
                schemaVersion: 1,
                status: .unavailable,
                unavailableReason: capabilities.systemLanguageModel.reason ?? .unknownUnavailable,
                device: device,
                capabilities: capabilities,
                modelProfile: modelProfile,
                caseResult: nil
            )
        }

        let cold = try await measuredRun(phase: .cold)
        let warm = try await measuredRun(phase: .warm)

        return LocalDietInferenceBenchmarkReport(
            schemaVersion: 1,
            status: .completed,
            unavailableReason: nil,
            device: device,
            capabilities: capabilities,
            modelProfile: modelProfile,
            caseResult: .init(
                caseID: Self.fixtureID,
                inputModality: "text",
                fixtureRef: "inline://\(Self.fixtureID)",
                predictedFoods: warm.draft.foods,
                coldLatencyMs: cold.latencyMs,
                warmLatencyMs: warm.latencyMs,
                peakMemoryDeltaMb: max(cold.peakMemoryDeltaMb, warm.peakMemoryDeltaMb),
                thermalStateBefore: cold.thermalBefore,
                thermalStateAfter: warm.thermalAfter
            )
        )
    }

    private func measuredRun(
        phase: LocalDietInferencePhase
    ) async throws -> MeasuredRun {
        let initialFootprint = try systemMetrics.footprintBytes()
        let thermalBefore = systemMetrics.thermalState()
        let startedAt = clock.nowNanoseconds()
        let measurement = try await memorySampler.measure(
            initialFootprintBytes: initialFootprint
        ) { [runner] in
            try await runner.infer(
                prompt: Self.syntheticPrompt,
                phase: phase
            )
        }
        let finishedAt = clock.nowNanoseconds()
        let thermalAfter = systemMetrics.thermalState()

        let elapsedNanoseconds = finishedAt >= startedAt
            ? finishedAt - startedAt
            : 0
        let peakDeltaBytes = measurement.peakFootprintBytes >= initialFootprint
            ? measurement.peakFootprintBytes - initialFootprint
            : 0

        return MeasuredRun(
            draft: measurement.value,
            latencyMs: Double(elapsedNanoseconds) / 1_000_000,
            peakMemoryDeltaMb: Double(peakDeltaBytes) / 1_000_000,
            thermalBefore: thermalBefore,
            thermalAfter: thermalAfter
        )
    }

    private struct MeasuredRun: Sendable {
        let draft: LocalDietDraft
        let latencyMs: Double
        let peakMemoryDeltaMb: Double
        let thermalBefore: LocalDietThermalState
        let thermalAfter: LocalDietThermalState
    }
}

public enum LocalDietLiveBenchmark {
    public static let enableEnvironmentKey = "LOCAL_DIET_ENABLE_LIVE_BENCHMARK"

    public static func isExplicitlyEnabled(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Bool {
        environment[enableEnvironmentKey] == "1"
    }

    @MainActor
    public static func runIfExplicitlyEnabled(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) async throws -> LocalDietInferenceBenchmarkReport? {
        guard isExplicitlyEnabled(environment: environment) else {
            return nil
        }

        let capabilities = LocalHealthCapabilityProbe.currentProfile()
        let device = LocalDietBenchmarkDevice(
            hardwareIdentifier: currentHardwareIdentifier(),
            deviceClass: capabilities.deviceClass,
            osVersion: capabilities.osVersion,
            isSimulator: capabilities.isSimulator,
            appBuild: "swift-spike"
        )
        let modelProfile = LocalDietBenchmarkModelProfile(
            engine: "apple_foundation_models",
            identifier: "system_language_model_default",
            version: capabilities.osVersion,
            downloadBytes: 0
        )

        #if canImport(FoundationModels)
        if #available(iOS 26.0, macOS 26.0, *) {
            return try await LocalDietInferenceBenchmark(
                capabilities: capabilities,
                device: device,
                modelProfile: modelProfile,
                runner: AppleFoundationDietInferenceRunner(),
                clock: LocalDietUptimeClock(),
                systemMetrics: LocalDietProcessSystemMetrics(),
                memorySampler: LocalDietPollingPeakMemorySampler()
            ).run()
        }
        #endif

        return try await LocalDietInferenceBenchmark(
            capabilities: capabilities,
            device: device,
            modelProfile: modelProfile,
            runner: UnavailableDietInferenceRunner(),
            clock: LocalDietUptimeClock(),
            systemMetrics: LocalDietProcessSystemMetrics(),
            memorySampler: LocalDietPollingPeakMemorySampler()
        ).run()
    }

    private static func currentHardwareIdentifier() -> String {
        #if canImport(Darwin)
        var systemInfo = utsname()
        guard uname(&systemInfo) == 0 else {
            return "unknown"
        }
        return withUnsafePointer(to: &systemInfo.machine) {
            $0.withMemoryRebound(to: CChar.self, capacity: 1) {
                String(cString: $0)
            }
        }
        #else
        return "unknown"
        #endif
    }
}

private enum LocalDietProcessFootprint {
    static func currentBytes() throws -> UInt64 {
        #if canImport(Darwin)
        var info = task_vm_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<task_vm_info_data_t>.size / MemoryLayout<natural_t>.size
        )
        let result = withUnsafeMutablePointer(to: &info) {
            $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                task_info(
                    mach_task_self_,
                    task_flavor_t(TASK_VM_INFO),
                    $0,
                    &count
                )
            }
        }
        guard result == KERN_SUCCESS else {
            throw LocalDietBenchmarkMetricsError.processFootprintUnavailable(
                code: result
            )
        }
        return UInt64(info.phys_footprint)
        #else
        throw LocalDietBenchmarkMetricsError.unsupportedPlatform
        #endif
    }
}

private struct UnavailableDietInferenceRunner: LocalDietInferenceRunning {
    enum Error: Swift.Error {
        case unexpectedlyInvoked
    }

    func infer(
        prompt: String,
        phase: LocalDietInferencePhase
    ) async throws -> LocalDietDraft {
        throw Error.unexpectedlyInvoked
    }
}

#if canImport(FoundationModels)
@available(iOS 26.0, macOS 26.0, *)
@Generable(description: "一餐中明确出现的食物与数量")
private struct AppleFoundationDietDraft {
    @Guide(description: "一至八项食物", .minimumCount(1), .maximumCount(8))
    var foods: [AppleFoundationDietFood]
}

@available(iOS 26.0, macOS 26.0, *)
@Generable(description: "一项食物及原描述中的数量")
private struct AppleFoundationDietFood {
    @Guide(description: "简短食物名称")
    var name: String

    @Guide(description: "大于零的数量", .minimum(0.01), .maximum(5_000))
    var quantity: Double

    @Guide(
        description: "原描述中的单位",
        .anyOf(["克", "毫升", "个", "份", "碗", "杯"])
    )
    var unit: String
}

@available(iOS 26.0, macOS 26.0, *)
private actor AppleFoundationDietInferenceRunner: LocalDietInferenceRunning {
    private var warmSession: LanguageModelSession?

    func infer(
        prompt: String,
        phase: LocalDietInferencePhase
    ) async throws -> LocalDietDraft {
        let session: LanguageModelSession
        switch phase {
        case .cold:
            session = makeSession()
            warmSession = session
        case .warm:
            session = warmSession ?? makeSession()
        }

        let response = try await session.respond(
            to: prompt,
            generating: AppleFoundationDietDraft.self
        )
        return LocalDietDraft(
            foods: response.content.foods.map {
                LocalDietFoodDraft(
                    name: $0.name,
                    quantity: $0.quantity,
                    unit: $0.unit
                )
            }
        )
    }

    private func makeSession() -> LanguageModelSession {
        LanguageModelSession(
            instructions: """
            每次只处理最新一条合成餐食描述。只提取明确出现的食物名称、数量和单位；不猜测缺失项，不计算任何健康或能量数据。
            """
        )
    }
}
#endif
