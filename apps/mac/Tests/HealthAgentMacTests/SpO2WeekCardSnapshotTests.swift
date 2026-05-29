import XCTest
import SwiftUI
import SnapshotTesting
@testable import HealthAgentMac
import HealthAgentMacCore

@MainActor
final class SpO2WeekCardSnapshotTests: XCTestCase {
    override func setUp() {
        super.setUp()
        // isRecording = true
    }

    @MainActor
    func testAllGreen_NoLongEpisodes() {
        let nights = makeNights(longEpisodeCounts: [0, 0, 0, 0, 0, 0, 0])
        assertCardSnapshot(nights: nights, named: "all-green")
    }

    @MainActor
    func testYellow_OneOrTwoNightsWithEpisodes() {
        let nights = makeNights(longEpisodeCounts: [0, 1, 0, 0, 0, 2, 0])
        assertCardSnapshot(nights: nights, named: "yellow-two-nights")
    }

    @MainActor
    func testRed_ThreeOrMoreNightsWithEpisodes() {
        let nights = makeNights(longEpisodeCounts: [3, 0, 2, 4, 1, 0, 5])
        assertCardSnapshot(nights: nights, named: "red-five-nights")
    }

    @MainActor
    func testWithMissingNights() {
        var nights = makeNights(longEpisodeCounts: [0, 1, 0, 0, 0, 0, 0])
        // Replace nights 2 and 5 with no-summary entries.
        nights[2] = NocturnalWeekNight(date: nights[2].date, summary: nil, errorMessage: "no sync")
        nights[5] = NocturnalWeekNight(date: nights[5].date, summary: nil)
        assertCardSnapshot(nights: nights, named: "missing-nights")
    }

    // MARK: - Pure presentation logic

    func testShouldShow_FalseUntilLoaded() {
        let nights = makeNights(longEpisodeCounts: [0, 0])
        XCTAssertFalse(SpO2WeekCard.shouldShow(nights: nights, loaded: false))
    }

    func testShouldShow_FalseIfNoNightsHaveSamples() {
        let empty = [
            NocturnalWeekNight(date: "2026-05-20", summary: nil),
            NocturnalWeekNight(date: "2026-05-21", summary: nil)
        ]
        XCTAssertFalse(SpO2WeekCard.shouldShow(nights: empty, loaded: true))
    }

    func testShouldShow_TrueWhenLoadedAndDataPresent() {
        let nights = makeNights(longEpisodeCounts: [0, 0])
        XCTAssertTrue(SpO2WeekCard.shouldShow(nights: nights, loaded: true))
    }

    func testNightsWithLongHypoxicEpisode_Counting() {
        let nights = makeNights(longEpisodeCounts: [0, 1, 0, 2, 0, 0, 3])
        XCTAssertEqual(SpO2WeekCard.nightsWithLongHypoxicEpisode(nights), 3)
    }

    func testDotColor_TransitionsAtCountBoundaries() {
        XCTAssertEqual(SpO2WeekCard.dotColor(for: nightWithLongEpisodeCount(0)), .green)
        XCTAssertEqual(SpO2WeekCard.dotColor(for: nightWithLongEpisodeCount(1)), .yellow)
        XCTAssertEqual(SpO2WeekCard.dotColor(for: nightWithLongEpisodeCount(2)), .red)
        XCTAssertEqual(SpO2WeekCard.dotColor(for: nightWithLongEpisodeCount(5)), .red)
    }

    func testDotColor_GreyWhenNoSummary() {
        let night = NocturnalWeekNight(date: "2026-05-20", summary: nil)
        XCTAssertEqual(SpO2WeekCard.dotColor(for: night), Color.gray.opacity(0.3))
    }

    func testShortLabel_ExtractsMonthDay() {
        XCTAssertEqual(SpO2WeekCard.shortLabel("2026-05-21"), "05/21")
        // Non-3-part input returns the raw string unchanged.
        XCTAssertEqual(SpO2WeekCard.shortLabel("2026/05/21"), "2026/05/21")
        XCTAssertEqual(SpO2WeekCard.shortLabel(""), "")
    }

    // MARK: - Helpers

    private func makeNights(longEpisodeCounts: [Int]) -> [NocturnalWeekNight] {
        return longEpisodeCounts.enumerated().map { offset, count in
            let dateStr = String(format: "2026-05-%02d", 20 + offset)
            return nightWithLongEpisodeCount(count, date: dateStr)
        }
    }

    private func nightWithLongEpisodeCount(_ count: Int, date: String = "2026-05-20") -> NocturnalWeekNight {
        // Construct a NocturnalSpO2Summary that yields the desired longHypoxicEpisodeCount.
        // The summary's init computes longHypoxicEpisodeCount from samples by walking sub-90% runs
        // with epoch span ≥ 300_000 ms. We synthesize `count` distinct 6-min segments separated by
        // recovery samples.
        var samples: [NocturnalTimeseriesPoint] = []
        let segmentMs: Int64 = 360_000  // 6 min
        let gapMs: Int64 = 120_000      // 2 min recovery between segments
        var t: Int64 = 1_000_000_000_000
        for _ in 0..<count {
            samples.append(NocturnalTimeseriesPoint(value: 88, epochMs: t))
            samples.append(NocturnalTimeseriesPoint(value: 87, epochMs: t + segmentMs))
            t += segmentMs + gapMs
            samples.append(NocturnalTimeseriesPoint(value: 96, epochMs: t))
            t += gapMs
        }
        if count == 0 {
            samples.append(NocturnalTimeseriesPoint(value: 97, epochMs: t))
            samples.append(NocturnalTimeseriesPoint(value: 96, epochMs: t + segmentMs))
        }
        let summary = NocturnalSpO2Summary(date: date, samples: samples)
        return NocturnalWeekNight(date: date, summary: summary)
    }

    @MainActor
    private func assertCardSnapshot(
        nights: [NocturnalWeekNight],
        named name: String,
        filePath: StaticString = #filePath,
        testName: String = #function,
        line: UInt = #line
    ) {
        let view = SpO2WeekCard(
            nights: nights,
            appLanguageRaw: "en",
            onAskAgent: { _, _ in }
        )
        .frame(width: 520)
        .padding(20)
        .background(Color.white)
        .environment(\.colorScheme, .light)
        .dynamicTypeSize(.medium)

        let host = NSHostingView(rootView: view)
        host.frame = CGRect(origin: .zero, size: host.fittingSize)

        assertSnapshot(
            of: host,
            as: .image(precision: 0.99),
            named: name,
            file: filePath,
            testName: testName,
            line: line
        )
    }
}
