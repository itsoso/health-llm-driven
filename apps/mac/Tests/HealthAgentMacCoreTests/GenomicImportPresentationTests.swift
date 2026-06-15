import XCTest
@testable import HealthAgentMacCore

final class GenomicImportPresentationTests: XCTestCase {
    func testQueuedAndProcessingAreActiveStates() {
        let queued = GenomicImportSummary(
            status: "queued",
            sourceType: "pdf",
            rawRecordCount: nil,
            knownTotal: nil,
            matchedCount: 0,
            duplicateCount: nil,
            unknownCount: nil,
            unmappedCount: nil,
            missingCount: nil,
            coveragePct: nil,
            finishedAt: nil,
            rawFileHash: nil
        )
        let processing = GenomicImportSummary(
            status: "processing",
            sourceType: "pdf",
            rawRecordCount: nil,
            knownTotal: nil,
            matchedCount: 3,
            duplicateCount: nil,
            unknownCount: nil,
            unmappedCount: nil,
            missingCount: nil,
            coveragePct: nil,
            finishedAt: nil,
            rawFileHash: nil
        )

        XCTAssertEqual(GenomicImportPresentation.phase(for: queued), .pending)
        XCTAssertEqual(GenomicImportPresentation.statusLabel(for: queued), "Queued")
        XCTAssertFalse(GenomicImportPresentation.isTerminal(queued))
        XCTAssertEqual(GenomicImportPresentation.phase(for: processing), .running)
        XCTAssertEqual(GenomicImportPresentation.detailText(for: processing), "3 matched markers; coverage is still being finalized.")
    }

    func testDoneCoverageSummaryAvoidsRawMarkerLists() {
        let summary = GenomicImportSummary(
            status: "done",
            sourceType: "txt",
            rawRecordCount: 18191,
            knownTotal: 1210,
            matchedCount: 12,
            duplicateCount: 3,
            unknownCount: 11,
            unmappedCount: 18176,
            missingCount: 1198,
            coveragePct: 1.0,
            finishedAt: "2026-05-15T10:00:00",
            rawFileHash: "abc"
        )

        XCTAssertEqual(GenomicImportPresentation.phase(for: summary), .complete)
        XCTAssertEqual(GenomicImportPresentation.statusLabel(for: summary), "Done")
        XCTAssertEqual(
            GenomicImportPresentation.detailText(for: summary),
            "12 of 1210 known health markers matched; 1198 missing; 18176 raw rows unmapped."
        )
        XCTAssertTrue(GenomicImportPresentation.isTerminal(summary))
    }
}
