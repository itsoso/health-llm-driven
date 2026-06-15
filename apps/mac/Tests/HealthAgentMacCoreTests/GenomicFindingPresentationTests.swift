import XCTest
@testable import HealthAgentMacCore

final class GenomicFindingPresentationTests: XCTestCase {
    func testPharmacogenomicFindingsUseMedicationConfirmationBoundary() {
        let finding = GenomicFindingSummary(
            id: 9,
            rsid: "rs1061235",
            category: "drug_sensitivity",
            geneName: "HLA-A*31:01",
            variantName: "卡马西平皮肤不良反应",
            genotype: "AA",
            resultLabel: "positive",
            riskLevel: "high",
            evidenceLevel: "screening",
            clinicalStatus: "pharmacogenomic_screening",
            description: "提示用药前需要医生确认的筛查信号。",
            variantNature: "risk"
        )

        XCTAssertEqual(GenomicFindingPresentation.badgeLabel(for: finding), "用药确认")
        XCTAssertEqual(
            GenomicFindingPresentation.boundaryText(for: finding),
            "PGx result is a medication risk flag; confirm with a clinician or pharmacist before starting, stopping, or changing medication."
        )
    }

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
