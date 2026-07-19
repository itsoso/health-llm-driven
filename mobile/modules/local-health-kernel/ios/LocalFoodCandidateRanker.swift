import Foundation

public struct LocalFoodCandidateRanker: Sendable {
    public init() {}

    public func rank(
        regionEmbeddings: [LocalFoodRegionEmbedding],
        labelBank: [LocalFoodLabelEmbedding],
        policy: LocalFoodRankingPolicy
    ) throws -> LocalFoodRankingResult {
        try validate(policy)
        guard !regionEmbeddings.isEmpty, !labelBank.isEmpty else {
            throw LocalFoodRankingError.emptyInput
        }

        let regions = try regionEmbeddings.map { region in
            (region: region, vector: try normalized(region.vector))
        }
        let labels = try labelBank.map { label in
            (label: label, vector: try normalized(label.vector))
        }

        let dimension = regions[0].vector.count
        guard regions.allSatisfy({ $0.vector.count == dimension }),
              labels.allSatisfy({ $0.vector.count == dimension }) else {
            throw LocalFoodRankingError.dimensionMismatch
        }

        var bestByID: [String: ScoredLabel] = [:]
        for region in regions {
            for label in labels {
                let match = ScoredLabel(
                    label: label.label,
                    score: dot(region.vector, label.vector),
                    evidence: region.region.evidence,
                    regionIndex: region.region.regionIndex
                )
                if let current = bestByID[label.label.canonicalFoodID] {
                    if match.isPreferred(over: current) {
                        bestByID[label.label.canonicalFoodID] = match
                    }
                } else {
                    bestByID[label.label.canonicalFoodID] = match
                }
            }
        }

        let ranked = bestByID.values.sorted(by: ScoredLabel.ranksBefore)
        let rankedFoods = ranked.filter { $0.label.kind == .food }
        let topFood = rankedFoods.first
        let topNonFood = ranked.first { $0.label.kind == .nonFood }

        if let topNonFood,
           topNonFood.score >= policy.minimumScore,
           topNonFood.score >= (topFood?.score ?? -Double.infinity) {
            return LocalFoodRankingResult(
                decision: .nonFood,
                candidates: [],
                topScore: topNonFood.score,
                margin: nil
            )
        }

        guard let topFood, topFood.score >= policy.minimumScore else {
            return LocalFoodRankingResult(
                decision: .unknown,
                candidates: [],
                topScore: topFood?.score,
                margin: nil
            )
        }

        let margin = rankedFoods.count > 1
            ? topFood.score - rankedFoods[1].score
            : nil
        if let margin, margin < policy.minimumMargin {
            return LocalFoodRankingResult(
                decision: .unknown,
                candidates: [],
                topScore: topFood.score,
                margin: margin
            )
        }

        let candidates = rankedFoods
            .filter { $0.score >= policy.minimumScore }
            .prefix(policy.maximumCandidates)
            .map(\.candidate)
        return LocalFoodRankingResult(
            decision: candidates.isEmpty ? .unknown : .candidate,
            candidates: candidates,
            topScore: topFood.score,
            margin: margin
        )
    }

    private func validate(_ policy: LocalFoodRankingPolicy) throws {
        guard policy.minimumScore.isFinite,
              policy.minimumMargin.isFinite,
              (-1...1).contains(policy.minimumScore),
              (0...2).contains(policy.minimumMargin),
              (1...3).contains(policy.maximumCandidates) else {
            throw LocalFoodRankingError.invalidPolicy
        }
    }

    private func normalized(_ vector: [Double]) throws -> [Double] {
        guard !vector.isEmpty else {
            throw LocalFoodRankingError.zeroLengthVector
        }
        guard vector.allSatisfy(\.isFinite) else {
            throw LocalFoodRankingError.nonFiniteVector
        }
        let squaredMagnitude = vector.reduce(0) { $0 + $1 * $1 }
        guard squaredMagnitude.isFinite else {
            throw LocalFoodRankingError.nonFiniteVector
        }
        guard squaredMagnitude > 0 else {
            throw LocalFoodRankingError.zeroLengthVector
        }
        let magnitude = sqrt(squaredMagnitude)
        return vector.map { $0 / magnitude }
    }

    private func dot(_ lhs: [Double], _ rhs: [Double]) -> Double {
        zip(lhs, rhs).reduce(0) { result, pair in
            result + pair.0 * pair.1
        }
    }
}

private struct ScoredLabel {
    let label: LocalFoodLabelEmbedding
    let score: Double
    let evidence: LocalFoodEvidence
    let regionIndex: Int?

    var candidate: LocalFoodCandidate {
        LocalFoodCandidate(
            canonicalFoodID: label.canonicalFoodID,
            displayName: label.displayName,
            category: label.category,
            score: score,
            evidence: evidence,
            regionIndex: regionIndex
        )
    }

    static func ranksBefore(_ lhs: ScoredLabel, _ rhs: ScoredLabel) -> Bool {
        if lhs.score != rhs.score {
            return lhs.score > rhs.score
        }
        return lhs.label.canonicalFoodID < rhs.label.canonicalFoodID
    }

    func isPreferred(over other: ScoredLabel) -> Bool {
        if score != other.score {
            return score > other.score
        }
        if evidence != other.evidence {
            return evidence == .wholeImage
        }
        return (regionIndex ?? -1) < (other.regionIndex ?? -1)
    }
}
