import Foundation
import XCTest
@testable import LocalHealthCapabilityProbe

final class LocalFoodCandidateRankerTests: XCTestCase {
    func testRanksNormalizedCosineAndDeduplicatesAcrossRegions() throws {
        let ranker = LocalFoodCandidateRanker()
        let result = try ranker.rank(
            regionEmbeddings: [
                .init(evidence: .wholeImage, regionIndex: nil, vector: [10, 0, 0]),
                .init(evidence: .salientRegion, regionIndex: 0, vector: [8, 2, 0]),
            ],
            labelBank: [
                food("rice", name: "米饭", vector: [2, 0, 0]),
                food("fish", name: "清蒸鱼", vector: [0.8, 0.6, 0]),
            ],
            policy: .init(minimumScore: 0.5, minimumMargin: 0.01, maximumCandidates: 3)
        )

        XCTAssertEqual(result.decision, .candidate)
        XCTAssertEqual(result.candidates.map(\.canonicalFoodID), ["rice", "fish"])
        XCTAssertEqual(result.candidates[0].score, 1, accuracy: 0.000001)
        XCTAssertEqual(result.candidates[0].evidence, .wholeImage)
        XCTAssertNil(result.candidates[0].regionIndex)
        XCTAssertEqual(result.candidates[1].evidence, .salientRegion)
        XCTAssertEqual(result.candidates[1].regionIndex, 0)
    }

    func testStableTieOrderingUsesCanonicalFoodID() throws {
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: [
                food("food.z", name: "乙", vector: [1, 0]),
                food("food.a", name: "甲", vector: [1, 0]),
            ],
            policy: .init(minimumScore: 0.5, minimumMargin: 0, maximumCandidates: 3)
        )

        XCTAssertEqual(result.candidates.map(\.canonicalFoodID), ["food.a", "food.z"])
    }

    func testMinimumScoreReturnsUnknownInsteadOfForcingFirstLabel() throws {
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: [food("rice", name: "米饭", vector: [0, 1])],
            policy: .init(minimumScore: 0.7, minimumMargin: 0.1, maximumCandidates: 3)
        )

        XCTAssertEqual(result.decision, .unknown)
        XCTAssertTrue(result.candidates.isEmpty)
    }

    func testMinimumTopOneMarginReturnsUnknown() throws {
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: [
                food("rice", name: "米饭", vector: [1, 0]),
                food("congee", name: "白粥", vector: [0.999, 0.001]),
            ],
            policy: .init(minimumScore: 0.5, minimumMargin: 0.05, maximumCandidates: 3)
        )

        XCTAssertEqual(result.decision, .unknown)
        XCTAssertTrue(result.candidates.isEmpty)
        XCTAssertLessThan(try XCTUnwrap(result.margin), 0.05)
    }

    func testNonFoodWinningLabelRejectsFoodCandidates() throws {
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: [
                food("rice", name: "米饭", vector: [0.8, 0.2]),
                .init(
                    canonicalFoodID: "negative.screen",
                    displayName: "屏幕截图",
                    category: "non_food",
                    kind: .nonFood,
                    vector: [1, 0]
                ),
            ],
            policy: .init(minimumScore: 0.5, minimumMargin: 0.05, maximumCandidates: 3)
        )

        XCTAssertEqual(result.decision, .nonFood)
        XCTAssertTrue(result.candidates.isEmpty)
    }

    func testCandidateCountIsHardCappedAtThree() throws {
        let labels = (0..<6).map { index in
            food("food.\(index)", name: "食物\(index)", vector: [1, Double(index) * 0.01])
        }
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: labels,
            policy: .init(minimumScore: 0.5, minimumMargin: 0, maximumCandidates: 3)
        )

        XCTAssertEqual(result.candidates.count, 3)
    }

    func testInvalidVectorsAndDimensionsFailExplicitly() throws {
        let ranker = LocalFoodCandidateRanker()
        let policy = LocalFoodRankingPolicy(
            minimumScore: 0.5,
            minimumMargin: 0.05,
            maximumCandidates: 3
        )

        XCTAssertThrowsError(
            try ranker.rank(
                regionEmbeddings: [
                    .init(evidence: .wholeImage, regionIndex: nil, vector: [.nan, 0])
                ],
                labelBank: [food("rice", name: "米饭", vector: [1, 0])],
                policy: policy
            )
        ) { error in
            XCTAssertEqual(error as? LocalFoodRankingError, .nonFiniteVector)
        }
        XCTAssertThrowsError(
            try ranker.rank(
                regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [0, 0])],
                labelBank: [food("rice", name: "米饭", vector: [1, 0])],
                policy: policy
            )
        ) { error in
            XCTAssertEqual(error as? LocalFoodRankingError, .zeroLengthVector)
        }
        XCTAssertThrowsError(
            try ranker.rank(
                regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
                labelBank: [food("rice", name: "米饭", vector: [1, 0, 0])],
                policy: policy
            )
        ) { error in
            XCTAssertEqual(error as? LocalFoodRankingError, .dimensionMismatch)
        }
    }

    func testEncodedCandidateContainsIdentityAndProvenanceButNoNutritionOrPortion() throws {
        let result = try LocalFoodCandidateRanker().rank(
            regionEmbeddings: [.init(evidence: .wholeImage, regionIndex: nil, vector: [1, 0])],
            labelBank: [food("rice", name: "米饭", vector: [1, 0])],
            policy: .init(minimumScore: 0.5, minimumMargin: 0.05, maximumCandidates: 3)
        )

        let data = try JSONEncoder().encode(result)
        let json = String(decoding: data, as: UTF8.self).lowercased()

        XCTAssertTrue(json.contains("canonicalfoodid"))
        XCTAssertTrue(json.contains("whole_image"))
        XCTAssertFalse(json.contains("calorie"))
        XCTAssertFalse(json.contains("nutrition"))
        XCTAssertFalse(json.contains("portion"))
        XCTAssertFalse(json.contains("gram"))
    }

    private func food(
        _ id: String,
        name: String,
        vector: [Double]
    ) -> LocalFoodLabelEmbedding {
        .init(
            canonicalFoodID: id,
            displayName: name,
            category: "food",
            kind: .food,
            vector: vector
        )
    }
}
