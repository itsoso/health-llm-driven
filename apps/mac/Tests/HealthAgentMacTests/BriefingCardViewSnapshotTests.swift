import XCTest
import SwiftUI
import SnapshotTesting
@testable import HealthAgentMac
import HealthAgentMacCore

@MainActor
final class BriefingCardViewSnapshotTests: XCTestCase {
    override func setUp() {
        super.setUp()
        // Set to true once locally to refresh baselines, then back to false.
        // isRecording = true
    }

    @MainActor
    func testEmptyBriefing_NoSections() {
        let briefing = DailyBriefing(
            date: "2026-05-28",
            greeting: "早上好。",
            sections: []
        )
        assertCardSnapshot(briefing: briefing, named: "empty")
    }

    @MainActor
    func testMixedStatusBriefing() {
        let briefing = DailyBriefing(
            date: "2026-05-28",
            greeting: "早上好。今天的简报如下。",
            sections: [
                BriefingSection(title: "Sleep", status: "good", items: [
                    "Slept 7h42m — well above your weekly median."
                ]),
                BriefingSection(title: "Recovery", status: "warning", items: [
                    "HRV down 14% vs your 14-day baseline.",
                    "Body battery started at 38 — consider an easier day."
                ]),
                BriefingSection(title: "Glucose", status: "poor", items: [
                    "Time-in-range fell to 58% (target ≥70%).",
                    "Two post-meal spikes >180 mg/dL."
                ]),
                BriefingSection(title: "Notes", status: "info", items: [
                    "AQI 142 — open windows after evening rush."
                ])
            ]
        )
        assertCardSnapshot(briefing: briefing, named: "mixed-status")
    }

    @MainActor
    func testNoGreetingNoDate() {
        let briefing = DailyBriefing(
            date: nil,
            greeting: nil,
            sections: [
                BriefingSection(title: "Sleep", status: "good", items: ["Slept 7h42m."])
            ]
        )
        assertCardSnapshot(briefing: briefing, named: "no-greeting-no-date")
    }

    // MARK: - Pure presentation logic

    func testStatusColorMappings() {
        XCTAssertEqual(BriefingCardView.statusColor(.good), .green)
        XCTAssertEqual(BriefingCardView.statusColor(.warning), .orange)
        XCTAssertEqual(BriefingCardView.statusColor(.poor), .red)
        XCTAssertEqual(BriefingCardView.statusColor(.info), .secondary)
    }

    func testStatusIconMappings() {
        XCTAssertEqual(BriefingCardView.statusIcon(.good), "checkmark.circle.fill")
        XCTAssertEqual(BriefingCardView.statusIcon(.warning), "exclamationmark.triangle.fill")
        XCTAssertEqual(BriefingCardView.statusIcon(.poor), "xmark.octagon.fill")
        XCTAssertEqual(BriefingCardView.statusIcon(.info), "info.circle.fill")
    }

    func testPromptText_JoinsItemsWithBullets() {
        let section = BriefingSection(title: "Recovery", status: "warning", items: [
            "HRV down 14%.",
            "Body battery 38."
        ])
        let prompt = BriefingCardView.promptText(for: section)
        XCTAssertTrue(prompt.contains("Recovery"))
        XCTAssertTrue(prompt.contains("• HRV down 14%."))
        XCTAssertTrue(prompt.contains("• Body battery 38."))
        XCTAssertTrue(prompt.contains("行动建议"))
    }

    func testContextItem_PayloadEncodesStatusAndItems() {
        let section = BriefingSection(title: "Sleep", status: "good", items: [
            "Slept 7h42m.",
            "Deep sleep 1h12m.",
            "REM 1h38m."
        ])
        let item = BriefingCardView.contextItem(for: section)
        XCTAssertEqual(item.sourceID, "briefing-Sleep")
        XCTAssertEqual(item.sourceKind, "briefing")
        XCTAssertEqual(item.title, "Sleep")
        XCTAssertEqual(item.payload["status"], "good")
        XCTAssertEqual(item.payload["item_0"], "Slept 7h42m.")
        XCTAssertEqual(item.payload["item_1"], "Deep sleep 1h12m.")
        XCTAssertEqual(item.payload["item_2"], "REM 1h38m.")
        XCTAssertTrue(item.summary.contains("Slept 7h42m."))
    }

    func testContextItem_TruncatesPayloadToFiveItems() {
        let items = (0..<8).map { "Item \($0)" }
        let section = BriefingSection(title: "Long", status: nil, items: items)
        let payload = BriefingCardView.contextItem(for: section).payload
        XCTAssertNotNil(payload["item_4"])
        XCTAssertNil(payload["item_5"])
    }

    func testContextItem_SummaryFallsBackToTitleWhenEmpty() {
        let section = BriefingSection(title: "Empty", status: nil, items: [])
        XCTAssertEqual(BriefingCardView.contextItem(for: section).summary, "Empty")
    }

    // MARK: - Helpers

    @MainActor
    private func assertCardSnapshot(
        briefing: DailyBriefing,
        named name: String,
        filePath: StaticString = #filePath,
        testName: String = #function,
        line: UInt = #line
    ) {
        let view = BriefingCardView(
            briefing: briefing,
            appLanguageRaw: "en",
            onAskAgent: { _, _ in },
            onAddContext: { (_: AgentContextItem) in },
            onScheduleReminder: { _ in }
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
