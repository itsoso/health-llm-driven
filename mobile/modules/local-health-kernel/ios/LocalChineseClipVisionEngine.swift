import Foundation
#if canImport(CoreML)
import CoreML
#endif

#if canImport(CoreGraphics) && canImport(ImageIO) && canImport(Vision)
import CoreGraphics
import ImageIO
import Vision
#endif

public enum LocalFoodVisionError: Error, Equatable, Sendable {
    case invalidImage
    case invalidFileURL
    case modelMissing
    case corruptModel
    case labelBankMissing
    case corruptLabelBank
    case invalidPreprocessorOutput
    case invalidModelOutput
    case cancelled
    case memoryPressure
    case thermalStateSerious
}

public struct LocalFoodResolvedIdentity: Codable, Equatable, Sendable {
    public let canonicalFoodID: String
    public let displayName: String
    public let category: String
    public let evidence: LocalFoodEvidence

    public init(
        canonicalFoodID: String,
        displayName: String,
        category: String,
        evidence: LocalFoodEvidence
    ) {
        self.canonicalFoodID = canonicalFoodID
        self.displayName = displayName
        self.category = category
        self.evidence = evidence
    }
}

public struct LocalFoodVisionRequest: Equatable, Sendable {
    public let image: LocalFoodRGBAImage
    public let exactUserSelection: LocalFoodResolvedIdentity?
    public let barcodeMatch: LocalFoodResolvedIdentity?
    public let reviewedOCRMatch: LocalFoodResolvedIdentity?

    public init(
        image: LocalFoodRGBAImage,
        exactUserSelection: LocalFoodResolvedIdentity? = nil,
        barcodeMatch: LocalFoodResolvedIdentity? = nil,
        reviewedOCRMatch: LocalFoodResolvedIdentity? = nil
    ) {
        self.image = image
        self.exactUserSelection = exactUserSelection
        self.barcodeMatch = barcodeMatch
        self.reviewedOCRMatch = reviewedOCRMatch
    }
}

public struct LocalFoodVisionProvenance: Codable, Equatable, Sendable {
    public let modelArtifactSHA256: String
    public let labelBankVersion: String
    public let calibrationVersion: String
    public let precisionVariant: String

    public init(
        modelArtifactSHA256: String,
        labelBankVersion: String,
        calibrationVersion: String,
        precisionVariant: String
    ) {
        self.modelArtifactSHA256 = modelArtifactSHA256
        self.labelBankVersion = labelBankVersion
        self.calibrationVersion = calibrationVersion
        self.precisionVariant = precisionVariant
    }
}

public struct LocalFoodVisionResult: Codable, Equatable, Sendable {
    public let decision: LocalFoodRankingDecision
    public let candidates: [LocalFoodCandidate]
    public let topScore: Double?
    public let margin: Double?
    public let provenance: LocalFoodVisionProvenance

    public init(
        decision: LocalFoodRankingDecision,
        candidates: [LocalFoodCandidate],
        topScore: Double?,
        margin: Double?,
        provenance: LocalFoodVisionProvenance
    ) {
        self.decision = decision
        self.candidates = candidates
        self.topScore = topScore
        self.margin = margin
        self.provenance = provenance
    }
}

public struct LocalFoodLabelBank: Equatable, Sendable {
    public let labelSetVersion: String
    public let modelRevision: String
    public let labels: [LocalFoodLabelEmbedding]

    public init(
        labelSetVersion: String,
        modelRevision: String,
        labels: [LocalFoodLabelEmbedding]
    ) {
        self.labelSetVersion = labelSetVersion
        self.modelRevision = modelRevision
        self.labels = labels
    }
}

public protocol LocalFoodRegionProposing: Sendable {
    func proposeRegions(in image: LocalFoodRGBAImage) async throws -> [LocalFoodRegionProposal]
}

public protocol LocalFoodEmbeddingPredicting: Sendable {
    func predict(_ region: LocalFoodPreparedRegion) async throws -> [Double]
}

public protocol LocalFoodEmbeddingModelLoading: Sendable {
    func loadModel(from fileURL: URL) throws -> any LocalFoodEmbeddingPredicting
}

public protocol LocalFoodLabelBankLoading: Sendable {
    func loadLabelBank(from fileURL: URL) throws -> LocalFoodLabelBank
}

public protocol LocalFoodVisionRuntimeGuard: Sendable {
    func checkCanContinue() throws
}

public struct LocalFoodNoopRegionProposer: LocalFoodRegionProposing, Sendable {
    public init() {}

    public func proposeRegions(in image: LocalFoodRGBAImage) async throws -> [LocalFoodRegionProposal] {
        []
    }
}

public struct LocalFoodProcessRuntimeGuard: LocalFoodVisionRuntimeGuard, Sendable {
    public init() {}

    public func checkCanContinue() throws {
        switch ProcessInfo.processInfo.thermalState {
        case .serious, .critical:
            throw LocalFoodVisionError.thermalStateSerious
        default:
            return
        }
    }
}

public actor LocalChineseClipVisionEngine {
    private let modelURL: URL
    private let labelBankURL: URL
    private let provenance: LocalFoodVisionProvenance
    private let rankingPolicy: LocalFoodRankingPolicy
    private let proposer: any LocalFoodRegionProposing
    private let preprocessor: any LocalFoodVisionPreprocessing
    private let modelLoader: any LocalFoodEmbeddingModelLoading
    private let labelLoader: any LocalFoodLabelBankLoading
    private let runtimeGuard: any LocalFoodVisionRuntimeGuard
    private let ranker: LocalFoodCandidateRanker

    private var loadedPredictor: (any LocalFoodEmbeddingPredicting)?
    private var loadedLabelBank: LocalFoodLabelBank?

    public init(
        modelURL: URL,
        labelBankURL: URL,
        provenance: LocalFoodVisionProvenance,
        rankingPolicy: LocalFoodRankingPolicy,
        proposer: any LocalFoodRegionProposing,
        preprocessor: any LocalFoodVisionPreprocessing,
        modelLoader: any LocalFoodEmbeddingModelLoading,
        labelLoader: any LocalFoodLabelBankLoading,
        runtimeGuard: any LocalFoodVisionRuntimeGuard,
        ranker: LocalFoodCandidateRanker = LocalFoodCandidateRanker()
    ) {
        self.modelURL = modelURL
        self.labelBankURL = labelBankURL
        self.provenance = provenance
        self.rankingPolicy = rankingPolicy
        self.proposer = proposer
        self.preprocessor = preprocessor
        self.modelLoader = modelLoader
        self.labelLoader = labelLoader
        self.runtimeGuard = runtimeGuard
        self.ranker = ranker
    }

    public func infer(request: LocalFoodVisionRequest) async throws -> LocalFoodVisionResult {
        if let exact = request.exactUserSelection {
            return resolved(exact)
        }
        if let barcode = request.barcodeMatch {
            return resolved(barcode)
        }
        if let ocr = request.reviewedOCRMatch {
            return resolved(ocr)
        }

        try checkCanContinue()
        do {
            let proposals = try await proposer.proposeRegions(in: request.image)
            try checkCanContinue()
            let regions = try preprocessor.prepare(image: request.image, proposals: proposals)
            try validate(regions)
            let predictor = try predictor()
            let bank = try labelBank()

            var embeddings: [LocalFoodRegionEmbedding] = []
            embeddings.reserveCapacity(regions.count)
            for region in regions {
                try checkCanContinue()
                let vector = try await predictor.predict(region)
                guard !vector.isEmpty, vector.allSatisfy(\.isFinite) else {
                    throw LocalFoodVisionError.invalidModelOutput
                }
                embeddings.append(
                    LocalFoodRegionEmbedding(
                        evidence: region.evidence,
                        regionIndex: region.regionIndex,
                        vector: vector
                    )
                )
            }

            let ranking = try ranker.rank(
                regionEmbeddings: embeddings,
                labelBank: bank.labels,
                policy: rankingPolicy
            )
            return LocalFoodVisionResult(
                decision: ranking.decision,
                candidates: ranking.candidates,
                topScore: ranking.topScore,
                margin: ranking.margin,
                provenance: provenance
            )
        } catch is CancellationError {
            throw LocalFoodVisionError.cancelled
        }
    }

    private func resolved(_ identity: LocalFoodResolvedIdentity) -> LocalFoodVisionResult {
        LocalFoodVisionResult(
            decision: .candidate,
            candidates: [
                LocalFoodCandidate(
                    canonicalFoodID: identity.canonicalFoodID,
                    displayName: identity.displayName,
                    category: identity.category,
                    score: 1,
                    evidence: identity.evidence,
                    regionIndex: nil
                )
            ],
            topScore: 1,
            margin: nil,
            provenance: provenance
        )
    }

    private func checkCanContinue() throws {
        if Task.isCancelled {
            throw LocalFoodVisionError.cancelled
        }
        try runtimeGuard.checkCanContinue()
    }

    private func validate(_ regions: [LocalFoodPreparedRegion]) throws {
        let wholeCount = regions.filter { $0.evidence == .wholeImage }.count
        let salientCount = regions.filter { $0.evidence == .salientRegion }.count
        guard wholeCount == 1,
              salientCount <= 3,
              regions.count == wholeCount + salientCount,
              regions.allSatisfy({ $0.tensor.count == 3 * 224 * 224 }) else {
            throw LocalFoodVisionError.invalidPreprocessorOutput
        }
    }

    private func predictor() throws -> any LocalFoodEmbeddingPredicting {
        if let loadedPredictor { return loadedPredictor }
        guard modelURL.isFileURL else { throw LocalFoodVisionError.invalidFileURL }
        let value = try modelLoader.loadModel(from: modelURL)
        loadedPredictor = value
        return value
    }

    private func labelBank() throws -> LocalFoodLabelBank {
        if let loadedLabelBank { return loadedLabelBank }
        guard labelBankURL.isFileURL else { throw LocalFoodVisionError.invalidFileURL }
        let value = try labelLoader.loadLabelBank(from: labelBankURL)
        guard value.labelSetVersion == provenance.labelBankVersion else {
            throw LocalFoodVisionError.corruptLabelBank
        }
        loadedLabelBank = value
        return value
    }
}

public struct LocalChineseClipLabelBankLoader: LocalFoodLabelBankLoading, Sendable {
    private static let magic = Data([0x43, 0x43, 0x4c, 0x42, 0x56, 0x31, 0x00, 0x00])

    public init() {}

    public func loadLabelBank(from fileURL: URL) throws -> LocalFoodLabelBank {
        guard fileURL.isFileURL else { throw LocalFoodVisionError.invalidFileURL }
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            throw LocalFoodVisionError.labelBankMissing
        }
        let data: Data
        do {
            data = try Data(contentsOf: fileURL, options: .mappedIfSafe)
        } catch {
            throw LocalFoodVisionError.corruptLabelBank
        }
        return try parse(data)
    }

    private func parse(_ data: Data) throws -> LocalFoodLabelBank {
        guard data.count >= 12, data.prefix(8) == Self.magic else {
            throw LocalFoodVisionError.corruptLabelBank
        }
        let headerLength = data.withUnsafeBytes { bytes in
            UInt32(littleEndian: bytes.loadUnaligned(fromByteOffset: 8, as: UInt32.self))
        }
        let headerLengthValue = Int(headerLength)
        guard 12 + headerLengthValue <= data.count else {
            throw LocalFoodVisionError.corruptLabelBank
        }
        let headerEnd = 12 + headerLengthValue
        let header: Header
        do {
            header = try JSONDecoder().decode(Header.self, from: data[12..<headerEnd])
        } catch {
            throw LocalFoodVisionError.corruptLabelBank
        }
        guard header.schemaVersion == 1,
              header.embeddingEncoding == "float32-little-endian",
              header.normalized,
              header.embeddingDimension > 0,
              !header.labels.isEmpty,
              header.labels.count <= Int.max / header.embeddingDimension / 4,
              data.count - headerEnd == header.labels.count * header.embeddingDimension * 4 else {
            throw LocalFoodVisionError.corruptLabelBank
        }

        let labels = header.labels.enumerated().map { index, raw in
            let vectorOffset = headerEnd + index * header.embeddingDimension * 4
            let vector = (0..<header.embeddingDimension).map { component in
                data.withUnsafeBytes { bytes -> Double in
                    let bits = UInt32(littleEndian: bytes.loadUnaligned(
                        fromByteOffset: vectorOffset + component * 4,
                        as: UInt32.self
                    ))
                    return Double(Float(bitPattern: bits))
                }
            }
            return LocalFoodLabelEmbedding(
                canonicalFoodID: raw.canonicalFoodId,
                displayName: raw.name,
                category: raw.category,
                kind: raw.category == "non_food" ? .nonFood : .food,
                vector: vector
            )
        }
        guard labels.allSatisfy({ label in
            !label.vector.isEmpty && label.vector.allSatisfy(\.isFinite)
        }) else {
            throw LocalFoodVisionError.corruptLabelBank
        }
        return LocalFoodLabelBank(
            labelSetVersion: header.labelSetVersion,
            modelRevision: header.modelRevision,
            labels: labels
        )
    }

    private struct Header: Decodable {
        let schemaVersion: Int
        let embeddingDimension: Int
        let embeddingEncoding: String
        let labelSetVersion: String
        let modelRevision: String
        let normalized: Bool
        let labels: [HeaderLabel]
    }

    private struct HeaderLabel: Decodable {
        let canonicalFoodId: String
        let name: String
        let category: String
    }
}

#if canImport(CoreML)
public struct LocalChineseClipCoreMLModelLoader: LocalFoodEmbeddingModelLoading, Sendable {
    public init() {}

    public func loadModel(from fileURL: URL) throws -> any LocalFoodEmbeddingPredicting {
        guard fileURL.isFileURL else { throw LocalFoodVisionError.invalidFileURL }
        guard FileManager.default.fileExists(atPath: fileURL.path) else {
            throw LocalFoodVisionError.modelMissing
        }
        let configuration = MLModelConfiguration()
        configuration.computeUnits = .all
        do {
            return LocalChineseClipCoreMLPredictor(
                model: try MLModel(contentsOf: fileURL, configuration: configuration)
            )
        } catch {
            throw LocalFoodVisionError.corruptModel
        }
    }
}

private final class LocalChineseClipCoreMLPredictor: LocalFoodEmbeddingPredicting, @unchecked Sendable {
    private let model: MLModel

    init(model: MLModel) {
        self.model = model
    }

    func predict(_ region: LocalFoodPreparedRegion) async throws -> [Double] {
        guard region.tensor.count == 3 * 224 * 224 else {
            throw LocalFoodVisionError.invalidPreprocessorOutput
        }
        let input = try MLMultiArray(shape: [1, 3, 224, 224], dataType: .float32)
        guard input.count == region.tensor.count,
              input.strides.map(\.intValue) == [3 * 224 * 224, 224 * 224, 224, 1] else {
            throw LocalFoodVisionError.invalidPreprocessorOutput
        }
        region.tensor.withUnsafeBytes { bytes in
            guard let baseAddress = bytes.baseAddress else { return }
            input.dataPointer.copyMemory(from: baseAddress, byteCount: bytes.count)
        }
        let provider = try MLDictionaryFeatureProvider(dictionary: ["image": input])
        let output = try model.prediction(from: provider)
        guard let features = output.featureValue(for: "image_features")?.multiArrayValue else {
            throw LocalFoodVisionError.invalidModelOutput
        }
        return (0..<features.count).map { features[$0].doubleValue }
    }
}
#endif

#if canImport(CoreGraphics) && canImport(ImageIO) && canImport(Vision)
public struct LocalFoodVisionSaliencyProposer: LocalFoodRegionProposing, Sendable {
    public init() {}

    public func proposeRegions(in image: LocalFoodRGBAImage) async throws -> [LocalFoodRegionProposal] {
        guard let provider = CGDataProvider(data: image.rgba8 as CFData),
              let cgImage = CGImage(
                width: image.width,
                height: image.height,
                bitsPerComponent: 8,
                bitsPerPixel: 32,
                bytesPerRow: image.width * 4,
                space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.last.rawValue),
                provider: provider,
                decode: nil,
                shouldInterpolate: true,
                intent: .defaultIntent
              ) else {
            throw LocalFoodVisionError.invalidImage
        }
        let request = VNGenerateAttentionBasedSaliencyImageRequest()
        let handler = VNImageRequestHandler(
            cgImage: cgImage,
            orientation: image.orientation.cgImageOrientation,
            options: [:]
        )
        try handler.perform([request])
        guard let observation = request.results?.first else { return [] }
        return (observation.salientObjects ?? []).map { object in
            let box = object.boundingBox
            return LocalFoodRegionProposal(
                x: box.minX,
                y: 1 - box.maxY,
                width: box.width,
                height: box.height,
                confidence: Double(object.confidence)
            )
        }
    }
}

private extension LocalFoodImageOrientation {
    var cgImageOrientation: CGImagePropertyOrientation {
        CGImagePropertyOrientation(rawValue: UInt32(rawValue)) ?? .up
    }
}
#endif
