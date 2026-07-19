import Foundation

public enum LocalFoodEvidence: String, Codable, Equatable, Sendable {
    case userSelection = "user_selection"
    case wholeImage = "whole_image"
    case salientRegion = "salient_region"
    case opticalCharacterRecognition = "optical_character_recognition"
    case barcode
}

public enum LocalFoodLabelKind: String, Codable, Equatable, Sendable {
    case food
    case nonFood = "non_food"
}

public struct LocalFoodLabelEmbedding: Codable, Equatable, Sendable {
    public let canonicalFoodID: String
    public let displayName: String
    public let category: String
    public let kind: LocalFoodLabelKind
    public let vector: [Double]

    public init(
        canonicalFoodID: String,
        displayName: String,
        category: String,
        kind: LocalFoodLabelKind,
        vector: [Double]
    ) {
        self.canonicalFoodID = canonicalFoodID
        self.displayName = displayName
        self.category = category
        self.kind = kind
        self.vector = vector
    }
}

public struct LocalFoodRegionEmbedding: Codable, Equatable, Sendable {
    public let evidence: LocalFoodEvidence
    public let regionIndex: Int?
    public let vector: [Double]

    public init(evidence: LocalFoodEvidence, regionIndex: Int?, vector: [Double]) {
        self.evidence = evidence
        self.regionIndex = regionIndex
        self.vector = vector
    }
}

public struct LocalFoodRankingPolicy: Codable, Equatable, Sendable {
    public let minimumScore: Double
    public let minimumMargin: Double
    public let maximumCandidates: Int

    public init(minimumScore: Double, minimumMargin: Double, maximumCandidates: Int) {
        self.minimumScore = minimumScore
        self.minimumMargin = minimumMargin
        self.maximumCandidates = maximumCandidates
    }
}

public struct LocalFoodCandidate: Codable, Equatable, Sendable {
    public let canonicalFoodID: String
    public let displayName: String
    public let category: String
    public let score: Double
    public let evidence: LocalFoodEvidence
    public let regionIndex: Int?

    public init(
        canonicalFoodID: String,
        displayName: String,
        category: String,
        score: Double,
        evidence: LocalFoodEvidence,
        regionIndex: Int?
    ) {
        self.canonicalFoodID = canonicalFoodID
        self.displayName = displayName
        self.category = category
        self.score = score
        self.evidence = evidence
        self.regionIndex = regionIndex
    }
}

public enum LocalFoodRankingDecision: String, Codable, Equatable, Sendable {
    case candidate
    case unknown
    case nonFood = "non_food"
}

public struct LocalFoodRankingResult: Codable, Equatable, Sendable {
    public let decision: LocalFoodRankingDecision
    public let candidates: [LocalFoodCandidate]
    public let topScore: Double?
    public let margin: Double?

    public init(
        decision: LocalFoodRankingDecision,
        candidates: [LocalFoodCandidate],
        topScore: Double?,
        margin: Double?
    ) {
        self.decision = decision
        self.candidates = candidates
        self.topScore = topScore
        self.margin = margin
    }
}

public enum LocalFoodRankingError: Error, Equatable, Sendable {
    case emptyInput
    case invalidPolicy
    case nonFiniteVector
    case zeroLengthVector
    case dimensionMismatch
}
