import XCTest
@testable import HealthAgentMacCore

final class AgendaPresentationTests: XCTestCase {
    func testTrainingDecisionPresentationIsReadOnlyGate() {
        let item = AgendaItem(
            type: "training",
            title: "今日训练:降一级",
            status: "info",
            timeWindow: "morning",
            priority: 80,
            canDefaultComplete: nil,
            detail: "恢复就绪度 62/100",
            responsible: nil,
            nextDue: nil,
            light: "yellow",
            zone: "light",
            readinessScore: 62,
            confidence: "medium",
            source: AgendaSource(objectType: "training_decision", objectID: 1)
        )

        let presentation = AgendaItemPresentation(item: item)

        XCTAssertEqual(presentation.statusLabel, "Training yellow")
        XCTAssertEqual(presentation.tone, .yellow)
        XCTAssertEqual(presentation.metaLine, "Readiness 62 · medium")
        XCTAssertFalse(presentation.canComplete)
    }

    func testAgendaSummaryCountsActionableAndInfoItems() {
        let today = AgendaToday(
            agendaDate: "2026-06-15",
            count: 3,
            items: [
                AgendaItem(type: "hydration", title: "Water", status: "pending", priority: 50, source: AgendaSource(objectType: "health_protocol", objectID: 2)),
                AgendaItem(type: "checkup", title: "LDL", status: "overdue", priority: 95, source: AgendaSource(objectType: "health_problem", objectID: 3)),
                AgendaItem(type: "data_quality", title: "HRV mismatch", status: "info", priority: 70, source: AgendaSource(objectType: "data_quality", objectID: 4)),
            ]
        )

        let summary = AgendaSummary(today: today)

        XCTAssertEqual(summary.total, 3)
        XCTAssertEqual(summary.actionable, 1)
        XCTAssertEqual(summary.overdue, 1)
        XCTAssertEqual(summary.info, 1)
    }
}
