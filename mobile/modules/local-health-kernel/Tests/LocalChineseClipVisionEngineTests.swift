import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalChineseClipVisionEngineTests: XCTestCase {
    func testPreprocessorCorrectsOrientationAndRejectsTinyOrOverlappingRegions() throws {
        let image = LocalFoodRGBAImage(
            width: 2,
            height: 1,
            orientation: .right,
            rgba8: Data([
                255, 0, 0, 255,
                0, 0, 255, 255,
            ])
        )
        let regions = try LocalFoodVisionPreprocessor().prepare(
            image: image,
            proposals: [
                .init(x: 0, y: 0, width: 1, height: 0.5, confidence: 0.9),
                .init(x: 0, y: 0, width: 1, height: 0.5, confidence: 0.8),
                .init(x: 0, y: 0, width: 0.01, height: 0.01, confidence: 1),
                .init(x: 0, y: 0.5, width: 1, height: 0.5, confidence: 0.7),
            ]
        )

        XCTAssertEqual(regions.count, 3)
        XCTAssertEqual(regions.map(\.evidence), [.wholeImage, .salientRegion, .salientRegion])
        XCTAssertEqual(regions.map(\.regionIndex), [nil, 0, 1])
        XCTAssertTrue(regions.allSatisfy { $0.tensor.count == 3 * 224 * 224 })

        let red = normalized(red: 255, green: 0, blue: 0)
        let blue = normalized(red: 0, green: 0, blue: 255)
        XCTAssertEqual(regions[0].tensor[0], red.0, accuracy: 0.0001)
        XCTAssertEqual(regions[0].tensor[223 * 224], blue.0, accuracy: 0.0001)
        XCTAssertEqual(regions[0].tensor[224 * 224], red.1, accuracy: 0.0001)
        XCTAssertEqual(regions[0].tensor[2 * 224 * 224], red.2, accuracy: 0.0001)
    }

    func testRunsExactlyOneWholeImageAndAtMostThreeRegions() async throws {
        let recorder = PredictionRecorder()
        let engine = makeEngine(
            proposals: (0..<6).map {
                .init(
                    x: Double($0) * 0.1,
                    y: 0,
                    width: 0.1,
                    height: 1,
                    confidence: 1 - Double($0) * 0.01
                )
            },
            recorder: recorder
        )

        let result = try await engine.infer(request: request())
        let predictionSnapshot = await recorder.snapshot()

        XCTAssertEqual(result.decision, .candidate)
        XCTAssertEqual(predictionSnapshot.count, 4)
        XCTAssertEqual(predictionSnapshot.evidence, [
            .wholeImage, .salientRegion, .salientRegion, .salientRegion,
        ])
    }

    func testExactSelectionThenBarcodeThenReviewedOCRPrecedeVisualModel() async throws {
        let recorder = PredictionRecorder()
        let engine = makeEngine(recorder: recorder)
        let exact = identity("exact", evidence: .userSelection)
        let barcode = identity("barcode", evidence: .barcode)
        let ocr = identity("ocr", evidence: .opticalCharacterRecognition)

        let exactResult = try await engine.infer(
            request: request(exact: exact, barcode: barcode, ocr: ocr)
        )
        let barcodeResult = try await engine.infer(
            request: request(barcode: barcode, ocr: ocr)
        )
        let ocrResult = try await engine.infer(request: request(ocr: ocr))
        let predictionSnapshot = await recorder.snapshot()

        XCTAssertEqual(exactResult.candidates.first?.canonicalFoodID, "exact")
        XCTAssertEqual(barcodeResult.candidates.first?.canonicalFoodID, "barcode")
        XCTAssertEqual(ocrResult.candidates.first?.canonicalFoodID, "ocr")
        XCTAssertEqual(predictionSnapshot.count, 0)
    }

    func testLowConfidenceReturnsUnknownAndIncludesFrozenProvenance() async throws {
        let result = try await makeEngine(
            embedding: [0, 1],
            policy: .init(minimumScore: 0.8, minimumMargin: 0.05, maximumCandidates: 3)
        ).infer(request: request())

        XCTAssertEqual(result.decision, .unknown)
        XCTAssertTrue(result.candidates.isEmpty)
        XCTAssertEqual(result.provenance.modelArtifactSHA256, String(repeating: "a", count: 64))
        XCTAssertEqual(result.provenance.labelBankVersion, "cn-food-labels-v1")
        XCTAssertEqual(result.provenance.calibrationVersion, "cn-clip-calibration-v1")
        XCTAssertEqual(result.provenance.precisionVariant, "int8-linear-per-channel-65536")
    }

    func testMissingAndCorruptModelErrorsAreNotSilentlyDowngraded() async throws {
        for expected in [LocalFoodVisionError.modelMissing, .corruptModel] {
            let engine = makeEngine(loaderError: expected)
            do {
                _ = try await engine.infer(request: request())
                XCTFail("Expected \(expected)")
            } catch {
                XCTAssertEqual(error as? LocalFoodVisionError, expected)
            }
        }
    }

    func testCancellationMemoryPressureAndThermalStopBeforePrediction() async throws {
        for expected in [
            LocalFoodVisionError.cancelled,
            .memoryPressure,
            .thermalStateSerious,
        ] {
            let recorder = PredictionRecorder()
            let engine = makeEngine(stopError: expected, recorder: recorder)
            do {
                _ = try await engine.infer(request: request())
                XCTFail("Expected \(expected)")
            } catch {
                let predictionSnapshot = await recorder.snapshot()
                XCTAssertEqual(error as? LocalFoodVisionError, expected)
                XCTAssertEqual(predictionSnapshot.count, 0)
            }
        }
    }

    func testOutputHasIdentityAndEvidenceButNoPixelsNutritionOrPortion() async throws {
        let result = try await makeEngine().infer(request: request())
        let json = String(decoding: try JSONEncoder().encode(result), as: UTF8.self).lowercased()

        XCTAssertTrue(json.contains("canonicalfoodid"))
        XCTAssertTrue(json.contains("whole_image"))
        XCTAssertTrue(json.contains("modelartifactsha256"))
        for forbidden in ["rgba", "tensor", "embedding", "calorie", "nutrition", "portion", "gram"] {
            XCTAssertFalse(json.contains(forbidden), "Unexpected output field: \(forbidden)")
        }
    }

    func testProductionLabelLoaderParsesPinnedBinaryFormatAndFailsOnCorruption() throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let validURL = directory.appendingPathComponent("labels.bin")
        try labelBankData().write(to: validURL, options: .atomic)

        let bank = try LocalChineseClipLabelBankLoader().loadLabelBank(from: validURL)

        XCTAssertEqual(bank.labelSetVersion, "cn-food-labels-v1")
        XCTAssertEqual(bank.labels.map(\.canonicalFoodID), ["rice"])
        XCTAssertEqual(bank.labels[0].vector[0], 1, accuracy: 0.000001)
        XCTAssertEqual(bank.labels[0].vector[1], 0, accuracy: 0.000001)

        let corruptURL = directory.appendingPathComponent("corrupt.bin")
        try Data("not-a-label-bank".utf8).write(to: corruptURL, options: .atomic)
        XCTAssertThrowsError(
            try LocalChineseClipLabelBankLoader().loadLabelBank(from: corruptURL)
        ) { error in
            XCTAssertEqual(error as? LocalFoodVisionError, .corruptLabelBank)
        }
    }

    private func makeEngine(
        proposals: [LocalFoodRegionProposal] = [],
        embedding: [Double] = [1, 0],
        policy: LocalFoodRankingPolicy = .init(
            minimumScore: 0.5,
            minimumMargin: 0,
            maximumCandidates: 3
        ),
        loaderError: LocalFoodVisionError? = nil,
        stopError: LocalFoodVisionError? = nil,
        recorder: PredictionRecorder = PredictionRecorder()
    ) -> LocalChineseClipVisionEngine {
        LocalChineseClipVisionEngine(
            modelURL: URL(fileURLWithPath: "/tmp/ChineseClipRN50Image.mlmodelc"),
            labelBankURL: URL(fileURLWithPath: "/tmp/chinese-clip-label-bank-v1.bin"),
            provenance: .init(
                modelArtifactSHA256: String(repeating: "a", count: 64),
                labelBankVersion: "cn-food-labels-v1",
                calibrationVersion: "cn-clip-calibration-v1",
                precisionVariant: "int8-linear-per-channel-65536"
            ),
            rankingPolicy: policy,
            proposer: FakeProposer(proposals: proposals),
            preprocessor: LocalFoodVisionPreprocessor(),
            modelLoader: FakeModelLoader(
                predictor: FakePredictor(embedding: embedding, recorder: recorder),
                error: loaderError
            ),
            labelLoader: FakeLabelLoader(),
            runtimeGuard: FakeRuntimeGuard(error: stopError)
        )
    }

    private func request(
        exact: LocalFoodResolvedIdentity? = nil,
        barcode: LocalFoodResolvedIdentity? = nil,
        ocr: LocalFoodResolvedIdentity? = nil
    ) -> LocalFoodVisionRequest {
        LocalFoodVisionRequest(
            image: .init(
                width: 2,
                height: 2,
                orientation: .up,
                rgba8: Data(repeating: 128, count: 16)
            ),
            exactUserSelection: exact,
            barcodeMatch: barcode,
            reviewedOCRMatch: ocr
        )
    }

    private func identity(
        _ id: String,
        evidence: LocalFoodEvidence
    ) -> LocalFoodResolvedIdentity {
        .init(canonicalFoodID: id, displayName: id, category: "food", evidence: evidence)
    }

    private func normalized(
        red: UInt8,
        green: UInt8,
        blue: UInt8
    ) -> (Float, Float, Float) {
        (
            (Float(red) / 255 - 0.48145466) / 0.26862954,
            (Float(green) / 255 - 0.4578275) / 0.26130258,
            (Float(blue) / 255 - 0.40821073) / 0.27577711
        )
    }

    private func labelBankData() throws -> Data {
        let header: [String: Any] = [
            "schemaVersion": 1,
            "embeddingDimension": 2,
            "embeddingEncoding": "float32-little-endian",
            "labelSetVersion": "cn-food-labels-v1",
            "modelRevision": String(repeating: "b", count: 40),
            "normalized": true,
            "labels": [[
                "canonicalFoodId": "rice",
                "name": "米饭",
                "category": "food",
            ]],
        ]
        let headerData = try JSONSerialization.data(withJSONObject: header, options: [.sortedKeys])
        var data = Data([0x43, 0x43, 0x4c, 0x42, 0x56, 0x31, 0x00, 0x00])
        var headerLength = UInt32(headerData.count).littleEndian
        withUnsafeBytes(of: &headerLength) { data.append(contentsOf: $0) }
        data.append(headerData)
        for value: Float in [1, 0] {
            var bits = value.bitPattern.littleEndian
            withUnsafeBytes(of: &bits) { data.append(contentsOf: $0) }
        }
        return data
    }
}

private struct FakeProposer: LocalFoodRegionProposing {
    let proposals: [LocalFoodRegionProposal]

    func proposeRegions(in image: LocalFoodRGBAImage) async throws -> [LocalFoodRegionProposal] {
        proposals
    }
}

private struct FakeModelLoader: LocalFoodEmbeddingModelLoading {
    let predictor: FakePredictor
    let error: LocalFoodVisionError?

    func loadModel(from fileURL: URL) throws -> any LocalFoodEmbeddingPredicting {
        if let error { throw error }
        return predictor
    }
}

private struct FakePredictor: LocalFoodEmbeddingPredicting {
    let embedding: [Double]
    let recorder: PredictionRecorder

    func predict(_ region: LocalFoodPreparedRegion) async throws -> [Double] {
        await recorder.record(region.evidence)
        return embedding
    }
}

private struct FakeLabelLoader: LocalFoodLabelBankLoading {
    func loadLabelBank(from fileURL: URL) throws -> LocalFoodLabelBank {
        LocalFoodLabelBank(
            labelSetVersion: "cn-food-labels-v1",
            modelRevision: String(repeating: "b", count: 40),
            labels: [
                .init(
                    canonicalFoodID: "rice",
                    displayName: "米饭",
                    category: "food",
                    kind: .food,
                    vector: [1, 0]
                )
            ]
        )
    }
}

private struct FakeRuntimeGuard: LocalFoodVisionRuntimeGuard {
    let error: LocalFoodVisionError?

    func checkCanContinue() throws {
        if let error { throw error }
    }
}

private actor PredictionRecorder {
    private(set) var evidence: [LocalFoodEvidence] = []

    func record(_ value: LocalFoodEvidence) {
        evidence.append(value)
    }

    func snapshot() -> (count: Int, evidence: [LocalFoodEvidence]) {
        (evidence.count, evidence)
    }
}
