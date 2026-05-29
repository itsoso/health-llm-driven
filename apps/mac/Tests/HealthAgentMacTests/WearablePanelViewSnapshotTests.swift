import XCTest
import SwiftUI
import SnapshotTesting
@testable import HealthAgentMac
import HealthAgentMacCore

@MainActor
final class WearablePanelViewSnapshotTests: XCTestCase {
    override func setUp() {
        super.setUp()
        // isRecording = true
    }

    @MainActor
    func testEmpty() {
        assertCardSnapshot(metrics: [], named: "empty")
    }

    @MainActor
    func testThreeMetrics_MixedTones() {
        let metrics = [
            DesktopDashboardMetric(
                id: "rhr",
                titleKey: "wearable.rhr.title",
                value: "62",
                detail: "wearable.rhr.detail",
                tone: "green",
                systemImage: "heart.fill"
            ),
            DesktopDashboardMetric(
                id: "hrv",
                titleKey: "wearable.hrv.title",
                value: "38",
                detail: "wearable.hrv.detail",
                tone: "orange",
                systemImage: "waveform.path.ecg"
            ),
            DesktopDashboardMetric(
                id: "battery",
                titleKey: "wearable.battery.title",
                value: "42",
                detail: "wearable.battery.detail",
                tone: "cyan",
                systemImage: "bolt.batteryblock.fill"
            )
        ]
        assertCardSnapshot(metrics: metrics, named: "three-mixed")
    }

    @MainActor
    private func assertCardSnapshot(
        metrics: [DesktopDashboardMetric],
        named name: String,
        filePath: StaticString = #filePath,
        testName: String = #function,
        line: UInt = #line
    ) {
        let view = WearablePanelView(
            metrics: metrics,
            appLanguageRaw: "en",
            localizedTitle: { Self.titleFor($0) },
            localizedDetail: { Self.detailFor($0) },
            onTap: { _ in }
        )
        .frame(width: 360)
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

    // Deterministic stand-in for TodayView's localizedMetricTitle/Detail closures.
    private static func titleFor(_ key: String) -> String {
        switch key {
        case "wearable.rhr.title": "Resting HR"
        case "wearable.hrv.title": "HRV"
        case "wearable.battery.title": "Body Battery"
        default: key
        }
    }

    private static func detailFor(_ key: String) -> String {
        switch key {
        case "wearable.rhr.detail": "bpm · vs 60 base"
        case "wearable.hrv.detail": "ms · −12 vs avg"
        case "wearable.battery.detail": "/100 · started 84"
        default: key
        }
    }
}
