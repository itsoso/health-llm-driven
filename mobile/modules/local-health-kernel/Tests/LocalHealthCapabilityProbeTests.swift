import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalHealthCapabilityProbeTests: XCTestCase {
    func testPreIOS26KeepsVisionButExplainsWhySystemModelIsUnavailable() throws {
        let profile = LocalHealthCapabilityProbe.profile(
            for: .init(
                osVersion: "25.5",
                osMajorVersion: 25,
                deviceClass: "phone",
                isSimulator: false,
                foundationModelsFrameworkAvailable: true,
                systemLanguageModelState: .available,
                visionFrameworkAvailable: true
            )
        )

        XCTAssertEqual(profile.schemaVersion, 1)
        XCTAssertEqual(profile.osVersion, "25.5")
        XCTAssertEqual(profile.deviceClass, "phone")
        XCTAssertFalse(profile.systemLanguageModel.available)
        XCTAssertEqual(profile.systemLanguageModel.reason, .osUnsupported)
        XCTAssertFalse(profile.multimodalLanguageModel.available)
        XCTAssertEqual(profile.multimodalLanguageModel.reason, .sdkNotSupported)
        XCTAssertTrue(profile.vision.textRecognition)
        XCTAssertTrue(profile.vision.imageClassification)
        XCTAssertTrue(profile.vision.barcodeDetection)
    }

    func testIOS26ReportsAvailableSystemLanguageModel() throws {
        let profile = LocalHealthCapabilityProbe.profile(
            for: runtime(systemLanguageModelState: .available)
        )

        XCTAssertTrue(profile.systemLanguageModel.available)
        XCTAssertNil(profile.systemLanguageModel.reason)
    }

    func testEveryKnownSystemModelFailureHasAnExplicitReason() throws {
        let cases: [(LocalHealthSystemLanguageModelState, LocalHealthCapabilityReason)] = [
            (.deviceNotEligible, .deviceNotEligible),
            (.appleIntelligenceNotEnabled, .appleIntelligenceNotEnabled),
            (.modelNotReady, .modelNotReady),
            (.unknownUnavailable, .unknownUnavailable),
        ]

        for (state, expectedReason) in cases {
            let profile = LocalHealthCapabilityProbe.profile(
                for: runtime(systemLanguageModelState: state)
            )

            XCTAssertFalse(profile.systemLanguageModel.available)
            XCTAssertEqual(profile.systemLanguageModel.reason, expectedReason)
        }
    }

    func testMissingFrameworkIsReportedWithoutReadingModelState() throws {
        let profile = LocalHealthCapabilityProbe.profile(
            for: runtime(
                foundationModelsFrameworkAvailable: false,
                systemLanguageModelState: nil
            )
        )

        XCTAssertFalse(profile.systemLanguageModel.available)
        XCTAssertEqual(profile.systemLanguageModel.reason, .frameworkUnavailable)
    }

    func testVisionFrameworkAbsenceDisablesEveryVisionCapability() throws {
        let profile = LocalHealthCapabilityProbe.profile(
            for: runtime(visionFrameworkAvailable: false)
        )

        XCTAssertEqual(
            profile.vision,
            .init(
                textRecognition: false,
                imageClassification: false,
                barcodeDetection: false
            )
        )
    }

    func testProfileRoundTripsThroughJSONForTheNativeBridge() throws {
        let profile = LocalHealthCapabilityProbe.profile(
            for: runtime(systemLanguageModelState: .appleIntelligenceNotEnabled)
        )

        let encoded = try JSONEncoder().encode(profile)
        let decoded = try JSONDecoder().decode(LocalHealthCapabilityProfile.self, from: encoded)

        XCTAssertEqual(decoded, profile)
    }

    @MainActor
    func testCurrentProfileAlwaysReturnsAnExplicitDeviceSnapshot() throws {
        let profile = LocalHealthCapabilityProbe.currentProfile()
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let encoded = try encoder.encode(profile)

        XCTAssertFalse(profile.osVersion.isEmpty)
        XCTAssertFalse(profile.deviceClass.isEmpty)
        XCTAssertEqual(profile.multimodalLanguageModel.reason, .sdkNotSupported)
        print("LOCAL_HEALTH_CAPABILITY_PROFILE=\(String(decoding: encoded, as: UTF8.self))")
    }

    private func runtime(
        foundationModelsFrameworkAvailable: Bool = true,
        systemLanguageModelState: LocalHealthSystemLanguageModelState? = .available,
        visionFrameworkAvailable: Bool = true
    ) -> LocalHealthRuntimeCapabilities {
        .init(
            osVersion: "26.5",
            osMajorVersion: 26,
            deviceClass: "phone",
            isSimulator: false,
            foundationModelsFrameworkAvailable: foundationModelsFrameworkAvailable,
            systemLanguageModelState: systemLanguageModelState,
            visionFrameworkAvailable: visionFrameworkAvailable
        )
    }
}
