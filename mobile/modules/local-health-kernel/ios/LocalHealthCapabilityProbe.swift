import Foundation

#if canImport(FoundationModels)
import FoundationModels
#endif

#if canImport(Vision)
import Vision
#endif

#if canImport(UIKit)
import UIKit
#endif

public enum LocalHealthCapabilityReason: String, Codable, Equatable, Sendable {
    case osUnsupported = "os_unsupported"
    case frameworkUnavailable = "framework_unavailable"
    case deviceNotEligible = "device_not_eligible"
    case appleIntelligenceNotEnabled = "apple_intelligence_not_enabled"
    case modelNotReady = "model_not_ready"
    case unknownUnavailable = "unknown_unavailable"
    case sdkNotSupported = "sdk_not_supported"
}

public enum LocalHealthSystemLanguageModelState: Equatable, Sendable {
    case available
    case deviceNotEligible
    case appleIntelligenceNotEnabled
    case modelNotReady
    case unknownUnavailable
}

public struct LocalHealthRuntimeCapabilities: Equatable, Sendable {
    public let osVersion: String
    public let osMajorVersion: Int
    public let deviceClass: String
    public let isSimulator: Bool
    public let foundationModelsFrameworkAvailable: Bool
    public let systemLanguageModelState: LocalHealthSystemLanguageModelState?
    public let visionFrameworkAvailable: Bool

    public init(
        osVersion: String,
        osMajorVersion: Int,
        deviceClass: String,
        isSimulator: Bool,
        foundationModelsFrameworkAvailable: Bool,
        systemLanguageModelState: LocalHealthSystemLanguageModelState?,
        visionFrameworkAvailable: Bool
    ) {
        self.osVersion = osVersion
        self.osMajorVersion = osMajorVersion
        self.deviceClass = deviceClass
        self.isSimulator = isSimulator
        self.foundationModelsFrameworkAvailable = foundationModelsFrameworkAvailable
        self.systemLanguageModelState = systemLanguageModelState
        self.visionFrameworkAvailable = visionFrameworkAvailable
    }
}

public struct LocalHealthCapabilityAvailability: Codable, Equatable, Sendable {
    public let available: Bool
    public let reason: LocalHealthCapabilityReason?

    public init(available: Bool, reason: LocalHealthCapabilityReason?) {
        self.available = available
        self.reason = reason
    }
}

public struct LocalHealthVisionCapabilities: Codable, Equatable, Sendable {
    public let textRecognition: Bool
    public let imageClassification: Bool
    public let barcodeDetection: Bool

    public init(
        textRecognition: Bool,
        imageClassification: Bool,
        barcodeDetection: Bool
    ) {
        self.textRecognition = textRecognition
        self.imageClassification = imageClassification
        self.barcodeDetection = barcodeDetection
    }
}

public struct LocalHealthCapabilityProfile: Codable, Equatable, Sendable {
    public let schemaVersion: Int
    public let osVersion: String
    public let deviceClass: String
    public let isSimulator: Bool
    public let systemLanguageModel: LocalHealthCapabilityAvailability
    public let multimodalLanguageModel: LocalHealthCapabilityAvailability
    public let vision: LocalHealthVisionCapabilities

    public init(
        schemaVersion: Int,
        osVersion: String,
        deviceClass: String,
        isSimulator: Bool,
        systemLanguageModel: LocalHealthCapabilityAvailability,
        multimodalLanguageModel: LocalHealthCapabilityAvailability,
        vision: LocalHealthVisionCapabilities
    ) {
        self.schemaVersion = schemaVersion
        self.osVersion = osVersion
        self.deviceClass = deviceClass
        self.isSimulator = isSimulator
        self.systemLanguageModel = systemLanguageModel
        self.multimodalLanguageModel = multimodalLanguageModel
        self.vision = vision
    }
}

public enum LocalHealthCapabilityProbe {
    public static func profile(
        for runtime: LocalHealthRuntimeCapabilities
    ) -> LocalHealthCapabilityProfile {
        let systemLanguageModel = systemLanguageModelAvailability(for: runtime)
        let visionAvailable = runtime.visionFrameworkAvailable

        return LocalHealthCapabilityProfile(
            schemaVersion: 1,
            osVersion: runtime.osVersion,
            deviceClass: runtime.deviceClass,
            isSimulator: runtime.isSimulator,
            systemLanguageModel: systemLanguageModel,
            // Xcode 26.5 exposes text generation only. Keep this false until the
            // shipped SDK provides a compile-time multimodal Foundation Models API.
            multimodalLanguageModel: .init(
                available: false,
                reason: .sdkNotSupported
            ),
            vision: .init(
                textRecognition: visionAvailable,
                imageClassification: visionAvailable,
                barcodeDetection: visionAvailable
            )
        )
    }

    @MainActor
    public static func currentProfile() -> LocalHealthCapabilityProfile {
        profile(for: currentRuntimeCapabilities())
    }

    private static func systemLanguageModelAvailability(
        for runtime: LocalHealthRuntimeCapabilities
    ) -> LocalHealthCapabilityAvailability {
        guard runtime.osMajorVersion >= 26 else {
            return .init(available: false, reason: .osUnsupported)
        }

        guard runtime.foundationModelsFrameworkAvailable else {
            return .init(available: false, reason: .frameworkUnavailable)
        }

        switch runtime.systemLanguageModelState {
        case .available:
            return .init(available: true, reason: nil)
        case .deviceNotEligible:
            return .init(available: false, reason: .deviceNotEligible)
        case .appleIntelligenceNotEnabled:
            return .init(available: false, reason: .appleIntelligenceNotEnabled)
        case .modelNotReady:
            return .init(available: false, reason: .modelNotReady)
        case .unknownUnavailable, .none:
            return .init(available: false, reason: .unknownUnavailable)
        }
    }

    @MainActor
    private static func currentRuntimeCapabilities() -> LocalHealthRuntimeCapabilities {
        let version = ProcessInfo.processInfo.operatingSystemVersion

        return LocalHealthRuntimeCapabilities(
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            osMajorVersion: version.majorVersion,
            deviceClass: currentDeviceClass(),
            isSimulator: currentEnvironmentIsSimulator(),
            foundationModelsFrameworkAvailable: foundationModelsFrameworkIsAvailable(),
            systemLanguageModelState: currentSystemLanguageModelState(),
            visionFrameworkAvailable: visionFrameworkIsAvailable()
        )
    }

    private static func foundationModelsFrameworkIsAvailable() -> Bool {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, macOS 26.0, *) {
            return true
        }
        #endif
        return false
    }

    private static func currentSystemLanguageModelState() -> LocalHealthSystemLanguageModelState? {
        #if canImport(FoundationModels)
        if #available(iOS 26.0, macOS 26.0, *) {
            switch SystemLanguageModel.default.availability {
            case .available:
                return .available
            case .unavailable(let reason):
                switch reason {
                case .deviceNotEligible:
                    return .deviceNotEligible
                case .appleIntelligenceNotEnabled:
                    return .appleIntelligenceNotEnabled
                case .modelNotReady:
                    return .modelNotReady
                @unknown default:
                    return .unknownUnavailable
                }
            }
        }
        #endif
        return nil
    }

    private static func visionFrameworkIsAvailable() -> Bool {
        #if canImport(Vision)
        return true
        #else
        return false
        #endif
    }

    @MainActor
    private static func currentDeviceClass() -> String {
        #if canImport(UIKit)
        switch UIDevice.current.userInterfaceIdiom {
        case .unspecified:
            return "unknown"
        case .phone:
            return "phone"
        case .pad:
            return "tablet"
        case .tv:
            return "television"
        case .carPlay:
            return "car_play"
        case .vision:
            return "spatial"
        case .mac:
            return "mac"
        @unknown default:
            return "unknown"
        }
        #elseif os(macOS)
        return "mac"
        #else
        return "unknown"
        #endif
    }

    private static func currentEnvironmentIsSimulator() -> Bool {
        #if targetEnvironment(simulator)
        return true
        #else
        return false
        #endif
    }
}
