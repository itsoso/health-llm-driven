import XCTest
@testable import HealthAgentMacCore

final class GenomicFindingPresentationTests: XCTestCase {
    func testGroupsRepeatedFindingsWithSameTitleDescriptionAndRisk() {
        let findings = [
            GenomicFindingSummary(
                id: 1,
                rsid: "rs121908763",
                category: "disease_risk",
                geneName: "CFTR",
                variantName: "CFTR 相关疾病筛查位点",
                genotype: "GG",
                resultLabel: "requires_confirmation",
                riskLevel: "high",
                evidenceLevel: "screening",
                description: "CFTR 变异与囊性纤维化、支气管扩张等 CFTR 相关疾病有关；DTC 结果必须复核",
                variantNature: "neutral"
            ),
            GenomicFindingSummary(
                id: 2,
                rsid: "rs149790377",
                category: "disease_risk",
                geneName: "CFTR",
                variantName: "CFTR 相关疾病筛查位点",
                genotype: "AA",
                resultLabel: "requires_confirmation",
                riskLevel: "high",
                evidenceLevel: "screening",
                description: "CFTR 变异与囊性纤维化、支气管扩张等 CFTR 相关疾病有关；DTC 结果必须复核",
                variantNature: "neutral"
            )
        ]

        let groups = GenomicFindingPresentation.groups(from: findings)

        XCTAssertEqual(groups.count, 1)
        XCTAssertEqual(groups.first?.title, "CFTR · CFTR 相关疾病筛查位点")
        XCTAssertEqual(groups.first?.variantCount, 2)
        XCTAssertEqual(groups.first?.rsidSummary, "rs121908763, rs149790377")
        XCTAssertEqual(groups.first?.primary.id, 1)
    }
}
