import XCTest
import SwiftUI
import SnapshotTesting
@testable import HealthAgentMac
import HealthAgentMacCore

@MainActor
final class PriorityActionHeroViewSnapshotTests: XCTestCase {
    override func setUp() {
        super.setUp()
        // isRecording = true
    }

    @MainActor
    func testEmpty_NothingOnDeck() {
        assertSnapshot(actions: [], named: "empty")
    }

    @MainActor
    func testSingleAction_RedTone() {
        let row = DesktopDashboardRow(
            id: "hr-spike",
            title: "Resting heart rate elevated",
            subtitle: "RHR has trended up 8 bpm over the last 5 nights.",
            value: "Now: 72 bpm · baseline 64 bpm",
            tone: "red",
            systemImage: "heart.fill",
            progress: nil
        )
        assertSnapshot(actions: [row], named: "single-red")
    }

    @MainActor
    func testMultipleActions_ShowsSwitch() {
        let actions = [
            DesktopDashboardRow(
                id: "hydrate",
                title: "Drink water",
                subtitle: "You're 600 ml below your daily target.",
                value: nil,
                tone: "cyan",
                systemImage: "drop.fill",
                progress: nil
            ),
            DesktopDashboardRow(
                id: "stand",
                title: "Stand up — 90 min seated streak",
                subtitle: nil,
                value: "3 min walk",
                tone: "green",
                systemImage: "figure.walk",
                progress: nil
            )
        ]
        assertSnapshot(actions: actions, named: "multi-shows-switch")
    }

    @MainActor
    private func assertSnapshot(
        actions: [DesktopDashboardRow],
        named name: String,
        filePath: StaticString = #filePath,
        testName: String = #function,
        line: UInt = #line
    ) {
        let view = PriorityActionHeroView(
            actions: actions,
            appLanguageRaw: "en",
            onStart: { _ in },
            onWhy: { _ in }
        )
        .frame(width: 620)
        .padding(20)
        .background(Color.white)
        .environment(\.colorScheme, .light)
        .dynamicTypeSize(.medium)

        let host = NSHostingView(rootView: view)
        host.frame = CGRect(origin: .zero, size: host.fittingSize)

        SnapshotTesting.assertSnapshot(
            of: host,
            as: .image(precision: 0.99),
            named: name,
            file: filePath,
            testName: testName,
            line: line
        )
    }
}
